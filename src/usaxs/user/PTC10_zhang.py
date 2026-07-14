"""
PTC10 heat-ramp + hold + cool plan for user Zhang.

Single position (sx=0, sy=0, thickness=1.3 mm):
  1. Collect USAXS/SAXS/WAXS at 40 °C.
  2. Heat to 550 °C at 5 °C/min, collecting data during ramp.
  3. Hold at 550 °C for 2 hours, collecting data.
  4. Turn heater off; wait until temperature drops to 40 °C.
  5. Collect final USAXS/SAXS/WAXS at 40 °C.

Reload:
    %run -im usaxs.user.PTC10_zhang

Debug mode (no instrument motion):
    ptc10_debug.put(True)
    ptc10_debug.put(False)

Usage:
    RE(PTC10_zhang("MySample"))
"""

import logging
import time

from bluesky import plan_stubs as bps
from apsbits.core.instrument_init import oregistry
from ophyd import Signal

from usaxs.plans.plans_user_facing import saxsExp, waxsExp
from usaxs.plans.plans_usaxs import USAXSscan
from usaxs.plans.command_list import after_command_list, before_command_list, sync_order_numbers
from usaxs.utils.obsidian import appendToMdFile

logger = logging.getLogger(__name__)
logger.info(__file__)

ptc10 = oregistry["ptc10"]
ptc10_debug = Signal(name="ptc10_debug", value=False)

# Fixed sample position for Zhang
POS_X = 0.0        # sx  mm
POS_Y = 0.0        # sy  mm
THICKNESS = 1.3    # mm

HEAT_RATE_C_PER_MIN = 5.0   # °C/min to 550 °C
TEMP_START = 40.0            # °C — initial and final temperature
TEMP_TARGET = 550.0          # °C — hold temperature
HOLD_MINUTES = 120           # minutes to hold at 550 °C
COOL_TO = 40.0               # °C — wait for this temp after heater off

SECOND = 1
MINUTE = 60 * SECOND


def setheaterOff():
    """Power down the PTC10 heater and stop the PID control loop."""
    yield from bps.mv(
        ptc10.enable, "Off",
        ptc10.pid.pidmode, "Off",
    )


def setheaterOn():
    """Power up the PTC10 heater and start the PID control loop.

    Always call AFTER setting ptc10.ramp and ptc10.temperature.setpoint.
    """
    yield from bps.mv(
        ptc10.enable, "On",
        ptc10.pid.pidmode, "On",
    )


def PTC10_zhang(sample_name, md={}):
    """
    PTC10 heat-ramp + hold + cool plan for user Zhang.

    Fixed position: sx=0, sy=0, thickness=1.3 mm.

    Sequence:
        1. Startup (before_command_list).
        2. Collect USAXS/SAXS/WAXS at 40 °C.
        3. Heat to 550 °C at 5 °C/min, collecting data during ramp.
        4. Hold at 550 °C for 2 h, collecting data continuously.
        5. Turn heater off; wait (no data) until temperature drops to 40 °C.
        6. Collect final USAXS/SAXS/WAXS at 40 °C.
        7. Teardown (after_command_list).

    Sample name format:
        {sample_name}_{ptc10_temp:.0f}C_{elapsed:.0f}min

    Parameters
    ----------
    sample_name : str
        Base name prepended to every scan title.
    md : dict, optional
        Extra metadata attached to every scan.

    Examples
    --------
    RE(PTC10_zhang("LiMnO"))
    """

    # =========================================================================
    # INNER HELPERS
    # =========================================================================

    def getSampleName():
        """Build a scan name encoding PTC10 temperature and elapsed time."""
        ptc_temp = ptc10.position
        elapsed = (time.time() - t0) / MINUTE
        return f"{sample_name}_{ptc_temp:.0f}C_{elapsed:.0f}min"

    def collectOne(debug=False):
        """Run USAXS → SAXS → WAXS at the single Zhang position."""
        if debug:
            sampleMod = getSampleName()
            logger.info("[DEBUG] collectOne: %s", sampleMod)
            yield from bps.sleep(20)
        else:
            yield from sync_order_numbers()
            sampleMod = getSampleName()
            md["title"] = sampleMod
            logger.info("USAXSscan: %s", sampleMod)
            yield from USAXSscan(POS_X, POS_Y, THICKNESS, sampleMod, md={})
            sampleMod = getSampleName()
            md["title"] = sampleMod
            logger.info("saxsExp: %s", sampleMod)
            yield from saxsExp(POS_X, POS_Y, THICKNESS, sampleMod, md={})
            sampleMod = getSampleName()
            md["title"] = sampleMod
            logger.info("waxsExp: %s", sampleMod)
            yield from waxsExp(POS_X, POS_Y, THICKNESS, sampleMod, md={})

    # =========================================================================
    # EXECUTION SEQUENCE
    # =========================================================================

    isDebugMode = ptc10_debug.get()
    t0 = time.time()

    logger.info(
        "Starting PTC10_zhang | sample=%s | debug=%s",
        sample_name,
        isDebugMode,
    )

    # --- Block 1: Startup ---------------------------------------------------
    if not isDebugMode:
        logger.info("Running before_command_list()")
        yield from before_command_list()
    else:
        logger.info("[DEBUG] Skipping before_command_list()")
        yield from bps.sleep(5)

    appendToMdFile(
        f"## PTC10_zhang: {sample_name}\n"
        f"- Position: sx={POS_X}, sy={POS_Y}, thickness={THICKNESS} mm\n"
        f"- Heat to {TEMP_TARGET} °C at {HEAT_RATE_C_PER_MIN} °C/min\n"
        f"- Hold for {HOLD_MINUTES} min then cool to {COOL_TO} °C"
    )

    # --- Block 2: Heat to 40 °C and collect initial dataset ----------------
    ptc10.tolerance.put(2.0)
    logger.info("Block 2: heating to %.0f °C for initial dataset", TEMP_START)
    appendToMdFile(f"Heating to {TEMP_START} °C for initial dataset")
    yield from bps.mv(ptc10.ramp, HEAT_RATE_C_PER_MIN / 60.0)  # °C/min → °C/s
    yield from bps.mv(ptc10.temperature.setpoint, TEMP_START)
    yield from setheaterOn()

    while not ptc10.temperature.inposition:
        logger.info("Waiting for %.0f °C | PTC10=%.1f °C", TEMP_START, ptc10.position)
        yield from bps.sleep(5)

    logger.info("At %.0f °C — collecting initial dataset", TEMP_START)
    appendToMdFile(f"Initial dataset at {TEMP_START} °C")
    yield from collectOne(isDebugMode)

    # --- Block 3: Ramp to 550 °C while collecting --------------------------
    logger.info(
        "Block 3: heating to %.0f °C at %.0f °C/min",
        TEMP_TARGET, HEAT_RATE_C_PER_MIN,
    )
    appendToMdFile(
        f"Heating to {TEMP_TARGET} °C at {HEAT_RATE_C_PER_MIN} °C/min — "
        f"collecting data during ramp"
    )
    # Ramp rate and heater already set in Block 2 — just update the setpoint.
    yield from bps.mv(ptc10.temperature.setpoint, TEMP_TARGET)

    ramp_count = 0
    while not ptc10.temperature.inposition:
        ramp_count += 1
        logger.info(
            "Ramp dataset %d | PTC10=%.1f °C → %.0f °C",
            ramp_count, ptc10.position, TEMP_TARGET,
        )
        yield from collectOne(isDebugMode)

    logger.info("Reached %.0f °C after %d dataset(s)", TEMP_TARGET, ramp_count)
    appendToMdFile(
        f"Arrived at {TEMP_TARGET} °C — {ramp_count} dataset(s) collected during ramp"
    )

    # --- Block 4: Hold at 550 °C for 2 hours --------------------------------
    # Reset t0 so sample names show time elapsed since hold started, not plan start.
    t0 = time.time()
    hold_start = t0
    hold_end = hold_start + HOLD_MINUTES * MINUTE
    logger.info(
        "Block 4: holding at %.0f °C for %d min",
        TEMP_TARGET, HOLD_MINUTES,
    )
    appendToMdFile(
        f"Hold at {TEMP_TARGET} °C for {HOLD_MINUTES} min — collecting data"
    )

    hold_count = 0
    while time.time() < hold_end:
        hold_count += 1
        elapsed_hold = (time.time() - hold_start) / MINUTE
        logger.info(
            "Hold dataset %d | elapsed %.1f / %d min | PTC10=%.1f °C",
            hold_count, elapsed_hold, HOLD_MINUTES, ptc10.position,
        )
        yield from collectOne(isDebugMode)

    appendToMdFile(
        f"Hold complete: {hold_count} dataset(s) collected at {TEMP_TARGET} °C"
    )

    # --- Block 5: Heater off — wait for cool-down to 40 °C -----------------
    logger.info("Block 5: heater off, waiting to cool to %.0f °C", COOL_TO)
    appendToMdFile(f"Heater off — cooling to {COOL_TO} °C (no data collection)")
    yield from setheaterOff()

    while ptc10.position > COOL_TO + 5:  # 5 °C hysteresis
        logger.debug("Cooling: PTC10=%.1f °C", ptc10.position)
        yield from bps.sleep(30)

    logger.info("Cooled to %.1f °C", ptc10.position)
    appendToMdFile(f"Cooled to {ptc10.position:.1f} °C")

    # --- Block 6: Final dataset at 40 °C ------------------------------------
    logger.info("Block 6: final dataset at %.1f °C", ptc10.position)
    appendToMdFile(f"Final dataset at {ptc10.position:.1f} °C")
    yield from collectOne(isDebugMode)

    # --- Block 7: Teardown --------------------------------------------------
    if not isDebugMode:
        logger.info("Running after_command_list()")
        yield from after_command_list()
    else:
        logger.info("[DEBUG] Skipping after_command_list()")

    appendToMdFile(f"PTC10_zhang complete: {sample_name}")
    logger.info("Plan complete: %s", sample_name)
