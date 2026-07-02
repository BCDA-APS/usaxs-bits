"""
PTC10 service/utility experiment plans.

Plans for controlled temperature-step experiments using the PTC10 furnace.
Additional plans will be added to this file as needed.

Load by:
    %run -im usaxs.user.ptc10_servis

Debug mode (no instrument operations, PTC10 thermal cycle still runs):
    ptc10_debug.put(True)   # enable debug
    ptc10_debug.put(False)  # restore normal operation

Plans in this file:
    ptc10_stepScan(scan_title, max_temp)
        -- step heating from 40 °C to max_temp in 10 °C steps at 20 °C/min;
           preUSAXStune + USAXS/SAXS/WAXS at each step.

    ptc10_holdScan(scan_title, target_temp, hold_min)
        -- baseline at 40 °C, ramp at 50 °C/min to target_temp, hold for
           hold_min minutes collecting USAXS/SAXS/WAXS continuously,
           then cool to 25 °C at 200 °C/min.

CHANGE LOG:
    * JIL, 2026-07-01 : Initial file with ptc10_stepScan
    * JIL, 2026-07-01 : Added ptc10_holdScan
"""

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

import time

import numpy as np
from bluesky import plan_stubs as bps
from apsbits.core.instrument_init import oregistry
from ophyd import Signal

from usaxs.plans.plans_user_facing import saxsExp
from usaxs.plans.plans_user_facing import waxsExp
from usaxs.plans.plans_usaxs import USAXSscan
from usaxs.plans.plans_tune import preUSAXStune
from usaxs.plans.command_list import after_command_list, sync_order_numbers
from usaxs.plans.command_list import before_command_list
from usaxs.utils.obsidian import appendToMdFile, recordFunctionRun

# PTC10 temperature controller from the ophyd device registry.
ptc10 = oregistry["ptc10"]

# Convenient time-unit constants.
SECOND = 1
MINUTE = 60 * SECOND
HOUR = 60 * MINUTE

# Debug / dry-run flag.  Read once at plan start as isDebugMode.
# At the IPython prompt:
#   ptc10_debug.put(True)   → debug mode  (no instrument operations)
#   ptc10_debug.put(False)  → normal mode (real data collection)
ptc10_debug = Signal(name="ptc10_debug", value=False)


# ==============================================================================
# Heater control utilities
# ==============================================================================

def setheaterOff():
    """Power down the PTC10 heater and stop the PID control loop."""
    yield from bps.mv(
        ptc10.enable, "Off",
        ptc10.pid.pidmode, "Off",
    )


def setheaterOn():
    """
    Power up the PTC10 heater and start the PID control loop.

    Always call AFTER setting ptc10.ramp and ptc10.temperature.setpoint.
    """
    yield from bps.mv(
        ptc10.enable, "On",
        ptc10.pid.pidmode, "On",
    )


# ==============================================================================
# Plan 1: Step heating with preUSAXStune + USAXS/SAXS/WAXS at each step
# ==============================================================================

def ptc10_stepScan(scan_title, max_temp, md={}):
    """
    Step heating plan: preUSAXStune + USAXS/SAXS/WAXS at every 10 °C step.

    Sequence:
        1. Instrument startup (before_command_list).
        2. Collect baseline USAXS/SAXS/WAXS at the starting temperature (40 °C).
        3. For each 10 °C step from 50 °C up to max_temp:
               a. Ramp to step temperature at 20 °C/min; wait silently.
               b. Run preUSAXStune to realign USAXS optics.
               c. Collect USAXS/SAXS/WAXS.
        4. Set heater setpoint to 25 °C at 200 °C/min (controlled cool-down).
           The heater stays on so the PTC10 actively cools to 25 °C.
           Call setheaterOff() manually when the furnace has cooled sufficiently.
        5. Instrument teardown (after_command_list).

    Sample position is fixed: sx=0, sy=0, thickness=1 mm.

    Parameters
    ----------
    scan_title : str
        Sample name — base label for all scans.
        Temperature (°C) and elapsed time (min) are appended automatically.
    max_temp : float
        Maximum temperature in °C.  Must be > 40 °C.
        Steps are generated as 40, 50, 60, …, max_temp.

    Load:
        %run -im usaxs.user.ptc10_servis

    Debug mode (PTC10 thermal cycle still runs, no scans taken):
        ptc10_debug.put(True)
        RE(ptc10_stepScan("MySample", 200))

    Normal run:
        ptc10_debug.put(False)
        RE(ptc10_stepScan("MySample", 200))
    """

    # Fixed sample position (no user input required).
    pos_X = 0.0
    pos_Y = 0.0
    thickness = 1.0

    # Heating profile constants.
    START_TEMP = 40       # °C — first measurement temperature
    STEP_SIZE = 10        # °C — temperature increment between steps
    HEAT_RATE = 20        # °C/min — ramp rate for each step
    FINAL_TEMP = 25       # °C — cool-down setpoint at plan end
    FINAL_RATE = 200      # °C/min — cool-down ramp rate

    # Build the list of step temperatures: [40, 50, 60, …, max_temp].
    temperature_steps = list(
        np.arange(START_TEMP, max_temp + 0.5 * STEP_SIZE, STEP_SIZE)
    )

    # -------------------------------------------------------------------------
    # Inner helpers (follow template conventions exactly)
    # -------------------------------------------------------------------------

    def getSampleName():
        """Return '{scan_title}_{T:.0f}C_{elapsed:.0f}min'."""
        return (
            f"{scan_title}"
            f"_{ptc10.position:.0f}C"
            f"_{(time.time() - t0) / 60:.0f}min"
        )

    def collectAllThree(debug=False):
        """Run sync → USAXS → SAXS → WAXS for the fixed sample position."""
        sampleMod = getSampleName()
        logger.debug("collectAllThree: %s", sampleMod)
        if debug:
            print(f"[DEBUG] collectAllThree: {sampleMod}")
            yield from bps.sleep(20)
        else:
            yield from sync_order_numbers()
            sampleMod = getSampleName()
            md["title"] = sampleMod
            logger.info("USAXSscan: %s", sampleMod)
            yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = getSampleName()
            md["title"] = sampleMod
            logger.info("saxsExp: %s", sampleMod)
            yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = getSampleName()
            md["title"] = sampleMod
            logger.info("waxsExp: %s", sampleMod)
            yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    # -------------------------------------------------------------------------
    # Execution sequence
    # -------------------------------------------------------------------------

    isDebugMode = ptc10_debug.get()
    recordFunctionRun()
    logger.info(
        "Starting ptc10_stepScan | sample=%s | max_temp=%s C | steps=%s | debug=%s",
        scan_title, max_temp, temperature_steps, isDebugMode,
    )

    # --- Block 1: Startup ----------------------------------------------------
    if not isDebugMode:
        logger.info("Running before_command_list()")
        yield from before_command_list()
    else:
        logger.info("[DEBUG] Skipping before_command_list()")

    appendToMdFile(
        f"Starting ptc10_stepScan: sample={scan_title}, "
        f"max_temp={max_temp} °C, steps={temperature_steps}"
    )

    # t0 marks experiment start — elapsed time in filenames counts from here.
    t0 = time.time()

    # --- Block 2: Ramp to starting temperature (40 °C) ----------------------
    logger.info("Ramping to starting temperature %s C at %s C/min", START_TEMP, HEAT_RATE)
    appendToMdFile(f"Ramping to starting temperature {START_TEMP} C at {HEAT_RATE} C/min")
    yield from bps.mv(ptc10.ramp, HEAT_RATE / 60.0)                 # °C/s
    yield from bps.mv(ptc10.temperature.setpoint, START_TEMP)
    yield from setheaterOn()

    while not ptc10.temperature.inposition:
        logger.debug("Ramping to %s C, current T=%.1f C", START_TEMP, ptc10.position)
        yield from bps.sleep(5)

    logger.info("Arrived at %s C. Collecting baseline dataset.", START_TEMP)
    appendToMdFile(f"Arrived at {START_TEMP} C. Collecting baseline dataset.")

    # Baseline collect at 40 °C (no tune needed at start — before_command_list handles it).
    yield from collectAllThree(isDebugMode)

    # --- Block 3: Step heating loop ------------------------------------------
    # Skip the first step (START_TEMP = 40 °C, already collected above).
    for step_temp in temperature_steps[1:]:

        # Ramp to the next step temperature.
        logger.info(
            "Ramping to %s C at %s C/min", step_temp, HEAT_RATE
        )
        appendToMdFile(f"Ramping to {step_temp:.0f} C at {HEAT_RATE} C/min")
        yield from bps.mv(ptc10.ramp, HEAT_RATE / 60.0)
        yield from bps.mv(ptc10.temperature.setpoint, step_temp)
        # Heater is already on from the previous step.

        while not ptc10.temperature.inposition:
            logger.debug(
                "Ramping to %s C, current T=%.1f C", step_temp, ptc10.position
            )
            yield from bps.sleep(5)

        logger.info("Arrived at %s C. Running preUSAXStune.", step_temp)
        appendToMdFile(f"Arrived at {step_temp:.0f} C. Running preUSAXStune.")

        # Tune USAXS optics at this temperature before collecting data.
        if not isDebugMode:
            yield from preUSAXStune()
        else:
            logger.info("[DEBUG] Skipping preUSAXStune at %s C", step_temp)
            yield from bps.sleep(5)

        logger.info("Collecting USAXS/SAXS/WAXS at %s C.", step_temp)
        appendToMdFile(f"Collecting USAXS/SAXS/WAXS at {step_temp:.0f} C.")
        yield from collectAllThree(isDebugMode)

    # --- Block 4: Set cool-down parameters and instrument teardown -----------
    logger.info(
        "Step scan complete. Setting heater to %s C at %s C/min for cool-down.",
        FINAL_TEMP, FINAL_RATE,
    )
    appendToMdFile(
        f"Step scan complete. Setting heater to {FINAL_TEMP} C "
        f"at {FINAL_RATE} C/min. Call setheaterOff() when furnace is cool."
    )
    yield from bps.mv(ptc10.ramp, FINAL_RATE / 60.0)                # °C/s
    yield from bps.mv(ptc10.temperature.setpoint, FINAL_TEMP)
    # Heater remains ON so the PTC10 actively controls the cool-down to 25 °C.
    # Call  setheaterOff()  manually once the furnace has reached a safe temperature.

    logger.info("Plan complete: %s", scan_title)
    appendToMdFile(f"ptc10_stepScan complete: {scan_title}")

    if not isDebugMode:
        logger.info("Running after_command_list()")
        yield from after_command_list()
    else:
        logger.info("[DEBUG] Skipping after_command_list()")


# ==============================================================================
# Plan 2: Baseline at 40 °C → ramp to target → isothermal hold → cool
# ==============================================================================

def ptc10_holdScan(scan_title, target_temp, hold_min, md={}):
    """
    Baseline at 40 °C, heat to target_temp, hold collecting data, then cool.

    Sequence:
        1. Instrument startup (before_command_list).
        2. Ramp to 40 °C at 50 °C/min; collect baseline USAXS/SAXS/WAXS.
        3. Ramp to target_temp at 50 °C/min; wait silently.
        4. Hold at target_temp for hold_min minutes, collecting USAXS/SAXS/WAXS
           continuously (as many full sets as time allows).
        5. Set heater setpoint to 25 °C at 200 °C/min (controlled cool-down).
           Heater stays ON so the PTC10 actively cools to 25 °C.
           Call setheaterOff() manually when the furnace has cooled.
        6. Instrument teardown (after_command_list).

    Sample position is fixed: sx=0, sy=0, thickness=1 mm.

    Parameters
    ----------
    scan_title : str
        Sample name — base label for all scans.
        Temperature (°C) and elapsed time (min) are appended automatically.
    target_temp : float
        Hold temperature in °C.
    hold_min : float
        Duration of the isothermal hold in minutes.

    Load:
        %run -im usaxs.user.ptc10_servis

    Debug mode (PTC10 heats normally, no scans):
        ptc10_debug.put(True)
        RE(ptc10_holdScan("MySample", 300, 60))

    Normal run:
        ptc10_debug.put(False)
        RE(ptc10_holdScan("MySample", 300, 60))
    """

    # Fixed sample position (no user input required).
    pos_X = 0.0
    pos_Y = 0.0
    thickness = 1.0

    # Heating profile constants.
    START_TEMP = 40       # °C — baseline measurement temperature
    HEAT_RATE = 50        # °C/min — ramp rate to target
    FINAL_TEMP = 25       # °C — cool-down setpoint at plan end
    FINAL_RATE = 200      # °C/min — cool-down ramp rate

    # -------------------------------------------------------------------------
    # Inner helpers
    # -------------------------------------------------------------------------

    def getSampleName():
        """Return '{scan_title}_{T:.0f}C_{elapsed:.0f}min'."""
        return (
            f"{scan_title}"
            f"_{ptc10.position:.0f}C"
            f"_{(time.time() - t0) / 60:.0f}min"
        )

    def collectAllThree(debug=False):
        """Run sync → USAXS → SAXS → WAXS for the fixed sample position."""
        sampleMod = getSampleName()
        logger.debug("collectAllThree: %s", sampleMod)
        if debug:
            print(f"[DEBUG] collectAllThree: {sampleMod}")
            yield from bps.sleep(20)
        else:
            yield from sync_order_numbers()
            sampleMod = getSampleName()
            md["title"] = sampleMod
            logger.info("USAXSscan: %s", sampleMod)
            yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = getSampleName()
            md["title"] = sampleMod
            logger.info("saxsExp: %s", sampleMod)
            yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = getSampleName()
            md["title"] = sampleMod
            logger.info("waxsExp: %s", sampleMod)
            yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    # -------------------------------------------------------------------------
    # Execution sequence
    # -------------------------------------------------------------------------

    isDebugMode = ptc10_debug.get()
    recordFunctionRun()
    logger.info(
        "Starting ptc10_holdScan | sample=%s | target=%s C | hold=%s min | debug=%s",
        scan_title, target_temp, hold_min, isDebugMode,
    )

    # --- Block 1: Startup ----------------------------------------------------
    if not isDebugMode:
        logger.info("Running before_command_list()")
        yield from before_command_list()
    else:
        logger.info("[DEBUG] Skipping before_command_list()")

    appendToMdFile(
        f"Starting ptc10_holdScan: sample={scan_title}, "
        f"target={target_temp} °C, hold={hold_min} min"
    )

    # t0 marks experiment start.
    t0 = time.time()

    # --- Block 2: Ramp to 40 °C and collect baseline -------------------------
    logger.info("Ramping to baseline temperature %s C at %s C/min", START_TEMP, HEAT_RATE)
    appendToMdFile(f"Ramping to baseline temperature {START_TEMP} C at {HEAT_RATE} C/min")
    yield from bps.mv(ptc10.ramp, HEAT_RATE / 60.0)                 # °C/s
    yield from bps.mv(ptc10.temperature.setpoint, START_TEMP)
    yield from setheaterOn()

    while not ptc10.temperature.inposition:
        logger.debug("Ramping to %s C, current T=%.1f C", START_TEMP, ptc10.position)
        yield from bps.sleep(5)

    logger.info("At %s C. Collecting baseline dataset.", START_TEMP)
    appendToMdFile(f"At {START_TEMP} C. Collecting baseline dataset.")
    yield from collectAllThree(isDebugMode)

    # --- Block 3: Ramp to target_temp ----------------------------------------
    logger.info("Ramping to %s C at %s C/min", target_temp, HEAT_RATE)
    appendToMdFile(f"Ramping to {target_temp} C at {HEAT_RATE} C/min")
    yield from bps.mv(ptc10.ramp, HEAT_RATE / 60.0)
    yield from bps.mv(ptc10.temperature.setpoint, target_temp)
    # Heater already on.

    while not ptc10.temperature.inposition:
        logger.debug("Ramping to %s C, current T=%.1f C", target_temp, ptc10.position)
        yield from bps.sleep(5)

    # Reset t0 so filenames count "hold time" from temperature arrival.
    t0 = time.time()
    logger.info("Arrived at %s C. Starting %.1f min hold.", target_temp, hold_min)
    appendToMdFile(f"Arrived at {target_temp} C. Starting {hold_min} min hold.")

    # --- Block 4: Isothermal hold — collect USAXS/SAXS/WAXS continuously -----
    hold_until = time.time() + hold_min * MINUTE
    while time.time() < hold_until:
        logger.debug(
            "Hold loop: %.1f min remaining", (hold_until - time.time()) / MINUTE
        )
        yield from collectAllThree(isDebugMode)

    logger.info("Hold complete (%s min).", hold_min)
    appendToMdFile(f"Hold complete ({hold_min} min). Setting cool-down to {FINAL_TEMP} C.")

    # --- Block 5: Set cool-down parameters -----------------------------------
    logger.info(
        "Setting heater to %s C at %s C/min for cool-down.", FINAL_TEMP, FINAL_RATE
    )
    yield from bps.mv(ptc10.ramp, FINAL_RATE / 60.0)                # °C/s
    yield from bps.mv(ptc10.temperature.setpoint, FINAL_TEMP)
    # Heater remains ON so the PTC10 actively controls the cool-down to 25 °C.
    # Call  setheaterOff()  manually once the furnace has reached a safe temperature.

    logger.info("Plan complete: %s", scan_title)
    appendToMdFile(f"ptc10_holdScan complete: {scan_title}")

    if not isDebugMode:
        logger.info("Running after_command_list()")
        yield from after_command_list()
    else:
        logger.info("[DEBUG] Skipping after_command_list()")
