"""
Bluesky plan template for PTC10 temperature controller with USAXS/SAXS/WAXS data collection.

PURPOSE:
    This file is the canonical template for writing PTC10 experiment plans.
    Do NOT run experiments from this file directly — copy it to a new file or
    derive your own plan function following this structure.

LOADING:
    In IPython / bluesky session:
        %run -im usaxs.user.ptc10_planG

DEBUG / DRY-RUN MODE:
    To test plan logic without moving the USAXS instrument:
        ptc10_debug.put(True)   # in IPython before calling RE(...)
    In debug mode:
      - before_command_list() and after_command_list() are skipped (no instrument operations)
      - collectAllThree() prints the sample name and sleeps 20 s instead of collecting data
      - PTC10 temperature ramps and holds still run normally — the full thermal cycle is
        exercised so timing and temperature logic can be validated safely
    To return to real data collection:
        ptc10_debug.put(False)

PTC10 CONTROLLER INTERFACE (key differences from Linkam):
    ptc10.position              : current temperature readback in °C
    ptc10.temperature.setpoint  : write target temperature in °C (does NOT block)
    ptc10.temperature.inposition: True once setpoint has been reached and stabilised
    ptc10.ramp                  : ramp rate setpoint in °C/SECOND
                                  IMPORTANT: user values are in °C/min — divide by 60
                                  Example: 50 °C/min → ptc10.ramp = 50/60 ≈ 0.833 °C/s
    ptc10.enable                : "On"/"Off" — power to the heater element
    ptc10.pid.pidmode           : "On"/"Off" — PID loop control

    Unlike Linkam, PTC10 does NOT have a built-in wait=True/False set_target helper.
    To set temperature and wait for arrival, use the sequence:
        yield from bps.mv(ptc10.ramp, rate_C_per_min / 60.0)
        yield from bps.mv(ptc10.temperature.setpoint, temp_C)
        yield from setheaterOn()
        while not ptc10.temperature.inposition:
            yield from bps.sleep(N)        # or collect data here

    setheaterOn() and setheaterOff() must be called explicitly. PTC10 does not
    automatically start or stop heating when the setpoint changes.

SAMPLE NAMING CONVENTION:
    Format: {scan_title}_{temperature:.0f}C_{elapsed_minutes:.0f}min
    - Temperature is read from ptc10.position at the moment getSampleName() is called.
    - Elapsed time is relative to the last t0 = time.time() assignment.
    - Reset t0 at meaningful milestones (plan start, temperature arrival, hold start)
      to make the time component informative rather than a raw cumulative counter.

MULTI-POSITION (SampleList) PATTERN:
    For experiments measuring multiple spots on one sample (or multiple samples in the
    furnace simultaneously), define a SampleList at the top of your plan file:
        SampleList = [
            [pos_X, pos_Y, thickness, "SampleNamePos1"],
            [pos_X, pos_Y, thickness, "SampleNamePos2"],
            ...
        ]
    Then iterate:
        for pos_X, pos_Y, thickness, scan_title in SampleList:
            yield from collectAllThree(pos_X, pos_Y, thickness, scan_title, isDebugMode)
    See ptc10_plan_template.py for a full working example of this pattern.

CHANGE LOG:
    * JIL, 2025-06-07 : initial PTC10 plan template
    * JIL, 2026-02-25 : AI-assisted documentation and debug mode fix
"""

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

import time

from bluesky import plan_stubs as bps
from apsbits.core.instrument_init import oregistry
from ophyd import Signal

from usaxs.plans.plans_user_facing import saxsExp
from usaxs.plans.plans_user_facing import waxsExp
from usaxs.plans.plans_usaxs import USAXSscan
from usaxs.plans.command_list import after_command_list, sync_order_numbers
from usaxs.plans.command_list import before_command_list
from usaxs.utils.obsidian import appendToMdFile

# Retrieve the PTC10 device from the ophyd device registry.
ptc10 = oregistry["ptc10"]

# Debug / dry-run flag.  Set at the IPython prompt before calling RE():
#   ptc10_debug.put(True)   → debug mode on  (skips instrument operations)
#   ptc10_debug.put(False)  → normal mode on (real data collection)
# The value is read once at plan start (isDebugMode) and used consistently.
ptc10_debug = Signal(name="ptc10_debug", value=False)


# ==============================================================================
# Heater control utilities
# These are thin wrappers around the PTC10 PV interface. Call them as plan
# generators (yield from setheaterOn()) — they are not regular functions.
# Always call setheaterOn() AFTER setting the ramp rate and setpoint, and
# always call setheaterOff() at the end of the plan before after_command_list().
# ==============================================================================

def setheaterOff():
    """
    Power down the PTC10 heater and stop the PID control loop.

    Call this at the end of every plan that activates the heater, or whenever
    the furnace must be made safe (e.g. before opening the enclosure).
    Both 'enable' and 'pidmode' must be set to "Off" together; setting only one
    would leave the hardware in an inconsistent state.
    """
    yield from bps.mv(
        ptc10.enable, "Off",      # cut power to the heating element
        ptc10.pid.pidmode, "Off", # stop the PID loop as well
    )


def setheaterOn():
    """
    Power up the PTC10 heater and start the PID control loop.

    Always call this AFTER setting the ramp rate (ptc10.ramp) and target
    temperature (ptc10.temperature.setpoint) so that heating begins with the
    correct parameters already loaded into the controller.
    Both 'enable' and 'pidmode' must be set to "On" together.
    """
    yield from bps.mv(
        ptc10.enable, "On",      # apply power to the heating element
        ptc10.pid.pidmode, "On", # start the PID loop
    )


# ==============================================================================
# DO NOT MODIFY THIS TEMPLATE FUNCTION.
# Copy it to a new file or function, then edit the copy for your experiment.
# ==============================================================================
def myPTC10Plan(
    pos_X, pos_Y, thickness, scan_title, temp1, rate1, delay1min, md={}
):
    """
    Single-sample PTC10 experiment: baseline → heat → hold → cool to ambient.

    Sequence:
        1. Run startup scripts; collect USAXS/SAXS/WAXS baseline at ambient temperature.
        2. Ramp to temp1 at rate1 °C/min. Waits silently for arrival (no data during ramp).
        3. Hold at temp1 for delay1min minutes, collecting USAXS/SAXS/WAXS repeatedly.
        4. Switch heater off; collect USAXS/SAXS/WAXS continuously while cooling to 40 °C.
        5. Run teardown scripts.

    Parameters
    ----------
    pos_X, pos_Y : float
        Sample stage X/Y position in mm.
    thickness : float
        Sample thickness in mm (used for transmission correction).
    scan_title : str
        Base name for all scans. Temperature and elapsed time are appended automatically.
    temp1 : float
        Target (hold) temperature in °C.
    rate1 : float
        Ramp rate to temp1 in °C/min (converted to °C/s internally).
    delay1min : float
        Hold time at temp1 in minutes.
    md : dict, optional
        Extra metadata passed into scan functions.

    To reload after editing:
        %run -im usaxs.user.ptc10_planG

    To run:
        RE(myPTC10Plan(0, 0, 1.3, "MySample", 300, 50, 60))
    """

    # ------------------------------------------------------------------
    # Inner helper functions — do not move, rename, or reorder these.
    # ------------------------------------------------------------------

    def getSampleName():
        """
        Build a sample name encoding scan_title, current PTC10 temperature,
        and elapsed time since the last t0 reset.

        Format: {scan_title}_{temperature:.0f}C_{elapsed_minutes:.0f}min

        Call immediately before every scan so the label reflects actual conditions.
        Time is measured from the last  t0 = time.time()  assignment in the
        execution block below.
        """
        return f"{scan_title}_{ptc10.position:.0f}C_{(time.time() - t0) / 60:.0f}min"

    def collectAllThree(debug=False):
        """
        Run a USAXS → SAXS → WAXS data-collection sequence.

        getSampleName() is called immediately before each scan so that each
        file name captures the temperature and elapsed time at acquisition time.
        sync_order_numbers() is called first so all three scans share a scan-group ID.

        Parameters
        ----------
        debug : bool
            When True (debug mode active), prints the sample name and sleeps
            20 s instead of moving the instrument.  Pass isDebugMode here.
        """
        sampleMod = getSampleName()
        if debug:
            # Simulate a data-collection cycle without touching the instrument.
            print(f"[DEBUG] collectAllThree: {sampleMod}")
            yield from bps.sleep(20)
        else:
            yield from sync_order_numbers()
            md["title"] = sampleMod
            yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = getSampleName()
            md["title"] = sampleMod
            yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = getSampleName()
            md["title"] = sampleMod
            yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    # ------------------------------------------------------------------
    # Execution sequence
    # ------------------------------------------------------------------

    # Read the debug flag once so behaviour is consistent throughout the plan.
    isDebugMode = ptc10_debug.get()
    logger.info(
        "Starting myPTC10Plan | sample=%s | debug=%s", scan_title, isDebugMode
    )

    # --- Block 1: Startup ------------------------------------------------
    # before_command_list() initialises the instrument and opens the Obsidian
    # notebook entry. MUST be skipped in debug mode.
    if not isDebugMode:
        yield from before_command_list()
    else:
        logger.info("[DEBUG] Skipping before_command_list()")

    appendToMdFile(
        f"Starting PTC10 plan: sample={scan_title}, "
        f"target={temp1} °C @ {rate1} °C/min, hold={delay1min} min"
    )

    # --- Block 2: Baseline data at ambient temperature -------------------
    # t0 marks experiment start; elapsed time in file names counts from here.
    t0 = time.time()
    logger.info("Collecting baseline USAXS/SAXS/WAXS at ambient temperature")
    appendToMdFile(f"Collecting baseline data at ambient temperature")
    yield from collectAllThree(isDebugMode)

    # --- Block 3: Ramp to temp1 -----------------------------------------
    # Set ramp rate and target, then start heater.
    # Rate: user inputs °C/min, PTC10 controller expects °C/s → divide by 60.
    logger.info("Heating to %s C at %s C/min", temp1, rate1)
    appendToMdFile(f"Heating to {temp1} C at {rate1} C/min")
    yield from bps.mv(ptc10.ramp, rate1 / 60.0)          # set ramp rate (°C/s)
    yield from bps.mv(ptc10.temperature.setpoint, temp1)  # set target temperature
    yield from setheaterOn()                               # start heating

    # Wait silently until PTC10 reaches temp1. No data during this ramp.
    # To collect data during heating instead, replace the sleep loop with:
    #   while not ptc10.temperature.inposition:
    #       yield from collectAllThree(isDebugMode)
    while not ptc10.temperature.inposition:
        logger.debug("Ramping to %s C, current T = %.1f C", temp1, ptc10.position)
        yield from bps.sleep(5)

    logger.info("Reached %s C. Beginning hold phase.", temp1)
    appendToMdFile(f"Reached {temp1} C. Beginning {delay1min} min hold.")

    # Reset t0 so elapsed time in file names counts from temperature arrival.
    t0 = time.time()

    # --- Block 4: Isothermal hold ----------------------------------------
    # Collect USAXS/SAXS/WAXS repeatedly until delay1min minutes have elapsed.
    logger.info("Holding at %s C for %s min, collecting data", temp1, delay1min)
    hold_until = time.time() + delay1min * 60
    while time.time() < hold_until:
        logger.debug(
            "Hold loop: %.1f min remaining", (hold_until - time.time()) / 60
        )
        yield from collectAllThree(isDebugMode)

    logger.info("Hold complete (%s min). Switching heater off.", delay1min)
    appendToMdFile(f"Hold complete ({delay1min} min). Heater off, cooling.")
    yield from setheaterOff()

    # --- Block 5: Passive cooling with data collection -------------------
    # With the heater off, furnace cools naturally. Collect data until the
    # sample is back near room temperature (≤40 °C).
    # To cool without collecting data, replace the loop with bps.sleep() or
    # a bare while loop checking ptc10.position.
    logger.info("Collecting data during passive cooling to 40 C")
    while ptc10.position > 40:
        logger.debug("Cooling: current T = %.1f C", ptc10.position)
        yield from collectAllThree(isDebugMode)

    logger.info("Cooled to ≤40 C. Plan complete.")
    appendToMdFile("Cooled to 40 C. Plan complete.")

    # --- Block 6: Teardown -----------------------------------------------
    # after_command_list() closes shutters, returns instrument to safe state,
    # and writes the session-end entry to the Obsidian notebook.
    # MUST be skipped in debug mode (mirrors Block 1 guard above).
    if not isDebugMode:
        yield from after_command_list()
    else:
        logger.info("[DEBUG] Skipping after_command_list()")

    logger.info("myPTC10Plan finished for sample %s", scan_title)
