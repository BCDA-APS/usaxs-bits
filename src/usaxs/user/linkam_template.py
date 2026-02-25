"""
Bluesky plan template for Linkam TC-1 temperature stage control with USAXS/SAXS/WAXS data collection.

PURPOSE:
    This file is the canonical template for writing Linkam experiment plans. Do NOT run
    experiments from this file directly — copy it to a new file or define your own plan
    function that follows this structure.

LOADING:
    In IPython / bluesky session:
        %run -im usaxs.user.linkam_template

DEBUG / DRY-RUN MODE:
    To test plan logic without moving the USAXS instrument:
        linkam_debug.put(True)   # in IPython before calling RE(...)
    In debug mode:
      - before_command_list() and after_command_list() are skipped (no instrument operations)
      - collectAllThree() prints the sample name and sleeps 20 s instead of collecting data
      - Linkam temperature control still runs normally — the thermal profile is fully exercised
    To return to real data collection:
        linkam_debug.put(False)

TYPICAL EXPERIMENT WORKFLOW (implemented in myLinkamPlan_template below):
    1. Heat to ~40 °C (near room temperature), collect USAXS/SAXS/WAXS baseline.
    2. Ramp to target temperature (temp1) at rate1 — optionally collect data during ramp.
    3. Hold at temp1 for delay1min minutes, collecting USAXS/SAXS/WAXS repeatedly.
    4. Ramp to final temperature (temp2) at rate2 — optionally collect data during ramp.
    5. Collect final USAXS/SAXS/WAXS dataset at temp2.

SAMPLE NAMING CONVENTION:
    Format: {scan_title}_{temperature:.0f}C_{elapsed_minutes:.0f}min
    - Temperature and elapsed time are captured at the moment setSampleName() is called,
      so each scan in a sequence gets an accurate label even as conditions change.
    - Elapsed time is measured from t0. Resetting t0 = time.time() at a specific moment
      (e.g., when target temperature is first reached) makes the time component meaningful
      as "minutes into hold" rather than "minutes since plan start".

INSTRUMENT OPERATIONS:
    - before_command_list()  : REQUIRED at plan start. Runs standard startup checklist,
                               records experiment start in Obsidian notebook.
    - after_command_list()   : REQUIRED at plan end. Runs standard teardown checklist,
                               records experiment end in Obsidian notebook.
    - sync_order_numbers()   : Synchronises scan-number counters before a USAXS→SAXS→WAXS
                               sequence so that the three scans share a scan group number.
    Both before/after_command_list must be skipped in debug mode to avoid moving the instrument.

CHANGE LOG:
    * PRJ, 2022-01-22 : updated for new Linkam support
    * JIL, 2021-11-12 : modified to use updated before_command_list(), verify operations
    * JIL, 2022-11-05 : 20ID test
    * JIL, 2024-12-03 : 12ID check and fix. Needs testing
    * JIL, 2025-05-28 : fixes for BITS
    * JIL, 2025-07-14 : operations
    * JIL, 2025-12-11 : AI-assisted cleanup, converted to template file

LIMITATIONS:
    Uses new Linkam support only for tc1 with linux ioc.
"""

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

import time

from bluesky import plan_stubs as bps
from apsbits.core.instrument_init import oregistry

from usaxs.plans.plans_user_facing import saxsExp
from usaxs.plans.plans_user_facing import waxsExp
from usaxs.plans.plans_usaxs import USAXSscan
from usaxs.plans.command_list import after_command_list
from usaxs.plans.command_list import before_command_list
from ophyd import Signal
from usaxs.plans.command_list import sync_order_numbers
from usaxs.utils.obsidian import appendToMdFile, recordFunctionRun

# Retrieve the Linkam TC-1 device from the ophyd device registry.
# This is the only supported controller for Linux IOC setups.
linkam_tc1 = oregistry["linkam_tc1"]

# Convenient time-unit constants for building delay expressions.
# Use these instead of raw seconds to make plan code self-documenting.
# Example:  yield from bps.sleep(5 * MINUTE)
SECOND = 1
MINUTE = 60 * SECOND
HOUR = 60 * MINUTE
DAY = 24 * HOUR
WEEK = 7 * DAY

# Software flag that controls debug / dry-run mode for all plans in this file.
# Default value is False (real data collection). Change at the IPython prompt:
#   linkam_debug.put(True)   — enable debug mode (skips instrument operations)
#   linkam_debug.put(False)  — restore real data collection
# The value is read once at plan start (isDebugMode) and used throughout.
linkam_debug = Signal(name="linkam_debug", value=False)


# ==============================================================================
# DO NOT MODIFY THIS TEMPLATE FUNCTION.
# Copy it to a new file or function, then edit the copy for your experiment.
# ==============================================================================
def myLinkamPlan_template(
    pos_X, pos_Y, thickness, scan_title, temp1, rate1, delay1min, temp2, rate2, md={}
):
    """
    Sample measurement workflow using a Linkam TC-1 controller.

    Sequence:
        1. Ramp to 40 °C (near room temperature), collect USAXS/SAXS/WAXS baseline.
        2. Ramp to *temp1* at *rate1* °C/min with wait=True
           (no data collection during this ramp).
        3. Hold at *temp1* for *delay1min* minutes, collecting USAXS/SAXS/WAXS repeatedly.
        4. Ramp to *temp2* at *rate2* °C/min with wait=False
           (collect data while ramping to temp2).
        5. Collect a final USAXS/SAXS/WAXS set on arrival at *temp2*.

    Parameters
    ----------
    pos_X, pos_Y : float
        Sample stage X/Y position in mm.
    thickness : float
        Sample thickness in mm (used for transmission correction).
    scan_title : str
        Base name for all scans. Temperature and elapsed time will be appended.
    temp1 : float
        First target temperature in °C (the "hold" temperature).
    rate1 : float
        Ramp rate to temp1 in °C/min.
    delay1min : float
        Hold time at temp1 in minutes.
    temp2 : float
        Second target temperature in °C (usually the cool-down endpoint, e.g. 40 °C).
    rate2 : float
        Ramp rate to temp2 in °C/min.
    md : dict, optional
        Extra metadata passed to scan functions.

    To reload after editing:
        %run -im usaxs.user.linkam_template

    To run:
        RE(myLinkamPlan_template(0, 0, 1, "sample", 200, 100, 20, 40, 100))
    """

    # ------------------------------------------------------------------
    # Inner helper functions — shared by all execution blocks below.
    # Do not move or rename these; the execution blocks depend on them.
    # ------------------------------------------------------------------

    def setSampleName():
        """
        Build a sample name that encodes the current Linkam temperature and
        elapsed time since the last t0 reset.

        Format: {scan_title}_{temperature:.0f}C_{elapsed_minutes:.0f}min

        Called immediately before every scan so that file names reflect the
        actual conditions at data-collection time.  Reset t0 = time.time()
        at meaningful milestones (e.g., temperature reached) so the elapsed
        time shown in the name is informative rather than cumulative.
        """
        return (
            f"{scan_title}"
            f"_{linkam.temperature.position:.0f}C"
            f"_{(time.time() - t0)/60:.0f}min"
        )

    def collectAllThree(debug=False):
        """
        Run a USAXS → SAXS → WAXS sequence with timestamped sample naming.

        Each of the three scans calls setSampleName() independently so that
        the file name captures the temperature and elapsed time at the moment
        that particular scan starts.  sync_order_numbers() is called first to
        align the three scan-counter values into one logical group.

        Parameters
        ----------
        debug : bool
            When True (debug mode active), prints the sample name and sleeps
            20 s instead of moving the instrument.  Set via linkam_debug signal.
        """
        sampleMod = setSampleName()
        if debug:
            # Debug mode: simulate a scan without touching the instrument.
            # Sleep matches a rough lower bound for a real USAXS/SAXS/WAXS cycle.
            print(sampleMod)
            yield from bps.sleep(20)
        else:
            # Synchronise scan-order counters so USAXS/SAXS/WAXS share a group ID.
            yield from sync_order_numbers()
            md["title"] = sampleMod
            yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
            # Refresh sample name after USAXS (which can take ~1.5 min) so that
            # SAXS and WAXS file names reflect the updated temperature/time.
            sampleMod = setSampleName()
            md["title"] = sampleMod
            yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = setSampleName()
            md["title"] = sampleMod
            yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    def change_rate_and_temperature(rate, t, wait=False):
        """
        Set Linkam ramp rate and move to a new target temperature.

        Parameters
        ----------
        rate : float
            Ramp rate in °C/min.
        t : float
            Target temperature in °C.
        wait : bool
            True  → plan blocks until the setpoint is reached (no data during ramp).
            False → plan returns immediately; use a ``while not linkam.temperature.inposition``
                    loop around collectAllThree() to collect data during the ramp.
        """
        yield from bps.mv(linkam.ramprate.setpoint, rate)
        yield from linkam.set_target(t, wait=wait)

    # ------------------------------------------------------------------
    # Execution sequence
    # ------------------------------------------------------------------
    # Resolve the Linkam device alias used throughout this plan.
    linkam = linkam_tc1

    # Read debug flag once at plan start so behaviour is consistent throughout.
    isDebugMode = linkam_debug.get()

    # --- Block 1: Startup ------------------------------------------------
    # before_command_list() runs the standard instrument startup checklist and
    # writes a "plan started" entry to the Obsidian notebook.
    # MUST be skipped in debug mode to avoid triggering instrument operations.
    if not isDebugMode:
        yield from before_command_list()

    # --- Block 2: Room-temperature baseline data -------------------------
    # Heat (or cool) to 40 °C at a brisk 150 °C/min; wait until stable.
    # 40 °C is chosen as a safe near-room-temperature reference point that is
    # above condensation risk but low enough to count as "room temperature".
    yield from change_rate_and_temperature(150, 40, wait=True)
    # Start the elapsed-time clock after arriving at 40 °C.
    t0 = time.time()
    yield from collectAllThree(isDebugMode)

    # --- Block 3: Ramp to temp1, then hold and collect ------------------
    logger.info("Ramping temperature to %s C", temp1)
    appendToMdFile(f"Ramping temperature to {temp1} C")
    # wait=True: plan blocks here until temp1 is reached; no data during ramp.
    # To collect data during this ramp, change to wait=False and add:
    #   while not linkam.temperature.inposition:
    #       yield from collectAllThree(isDebugMode)
    yield from change_rate_and_temperature(rate1, temp1, wait=True)
    # Reset t0 so that elapsed time in file names counts from temperature arrival.
    t0 = time.time()

    logger.info("Reached %s C, collecting data for %s minutes", temp1, delay1min)
    appendToMdFile(f"Reached {temp1} C, collecting data for {delay1min} minutes")
    hold_until = time.time() + delay1min * MINUTE
    while time.time() < hold_until:
        yield from collectAllThree(isDebugMode)

    logger.info("Hold complete after %s minutes, ramping to %s C", delay1min, temp2)
    appendToMdFile(f"Hold complete after {delay1min} minutes, ramping to {temp2} C")

    # --- Block 4: Ramp to temp2 while collecting data -------------------
    # wait=False: plan returns immediately so we can collect during the ramp.
    yield from change_rate_and_temperature(rate2, temp2, wait=False)
    while not linkam.temperature.inposition:
        yield from collectAllThree(isDebugMode)

    logger.info("Reached %s C", temp2)
    appendToMdFile(f"Reached {temp2} C")
    # Final data set at the terminal temperature.
    yield from collectAllThree(isDebugMode)

    logger.info("Plan finished")
    appendToMdFile("Plan finished")

    # --- Block 5: Teardown -----------------------------------------------
    # after_command_list() runs standard post-scan scripts and writes a
    # "plan finished" entry to the Obsidian notebook.
    # MUST be skipped in debug mode (mirrors the before_command_list guard above).
    if not isDebugMode:
        yield from after_command_list()
