"""
Linkam plan for user Zhang.

Single position, with sample name as input parameter:
  1. Go to 40 °C, collect USAXS/SAXS/WAXS baseline.
  2. Ramp to 1100 °C at 200 °C/min (no data during ramp).
  3. Hold at 1100 °C for 4 hours, collecting USAXS/SAXS/WAXS continuously.
     Sample names show elapsed hold time (clock resets on arrival at 1100 °C).
  4. Cool to 40 °C at 200 °C/min (no data during cooling).
  5. Collect final USAXS/SAXS/WAXS at 40 °C.

Reload:
    %run -im usaxs.user.linkam_zhang

Debug mode (no instrument motion, Linkam still heats):
    linkam_debug.put(True)
    linkam_debug.put(False)

Usage:
    RE(linkam_zhang("MySample", 0, 0, 1.3))
"""

import logging
import time

from bluesky import plan_stubs as bps
from apsbits.core.instrument_init import oregistry
from ophyd import Signal

from usaxs.plans.plans_user_facing import saxsExp, waxsExp
from usaxs.plans.plans_usaxs import USAXSscan
from usaxs.plans.command_list import after_command_list, before_command_list, sync_order_numbers
from usaxs.utils.obsidian import appendToMdFile, recordFunctionRun

logger = logging.getLogger(__name__)
logger.info(__file__)

linkam_tc1 = oregistry["linkam_tc1"]

SECOND = 1
MINUTE = 60 * SECOND
HOUR = 60 * MINUTE

TEMP_START = 40.0       # °C — baseline and final temperature
TEMP_TARGET = 1100.0    # °C — hold temperature
RAMP_RATE = 200.0       # °C/min — used for both heating and cooling
HOLD_HOURS = 4          # hours at 1100 °C

linkam_debug = Signal(name="linkam_debug", value=False)


def linkam_zhang(sample_name, pos_X, pos_Y, thickness, md={}):
    """
    Linkam heat-hold-cool plan for user Zhang.

    Sequence:
        1. Startup (before_command_list).
        2. Go to 40 °C, collect USAXS/SAXS/WAXS baseline.
        3. Ramp to 1100 °C at 200 °C/min (no data during ramp).
        4. Hold at 1100 °C for 4 h, collecting USAXS/SAXS/WAXS continuously.
           Sample name clock resets on arrival so names show hold-elapsed time.
        5. Cool to 40 °C at 200 °C/min (no data during cooling).
        6. Collect final USAXS/SAXS/WAXS at 40 °C.
        7. Teardown (after_command_list).

    Sample name format during hold:
        {sample_name}_{linkam_temp:.0f}C_{hold_elapsed:.0f}min

    Parameters
    ----------
    sample_name : str
        Base name prepended to every scan title.
    pos_X : float
        Sample stage X position in mm.
    pos_Y : float
        Sample stage Y position in mm.
    thickness : float
        Sample thickness in mm.
    md : dict, optional
        Extra metadata attached to every scan.

    Examples
    --------
    RE(linkam_zhang("LiMnO", 0, 0, 1.3))
    """

    # =========================================================================
    # INNER HELPERS
    # =========================================================================

    linkam = linkam_tc1

    def setSampleName():
        """Build scan name encoding Linkam temperature and elapsed time since t0."""
        return (
            f"{sample_name}"
            f"_{linkam.temperature.position:.0f}C"
            f"_{(time.time() - t0) / MINUTE:.0f}min"
        )

    def collectAllThree(debug=False):
        """Run USAXS → SAXS → WAXS with timestamped sample naming."""
        if debug:
            print(setSampleName())
            yield from bps.sleep(20)
        else:
            yield from sync_order_numbers()
            sampleMod = setSampleName()
            md["title"] = sampleMod
            logger.info("USAXSscan: %s", sampleMod)
            yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = setSampleName()
            md["title"] = sampleMod
            logger.info("saxsExp: %s", sampleMod)
            yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = setSampleName()
            md["title"] = sampleMod
            logger.info("waxsExp: %s", sampleMod)
            yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    def change_rate_and_temperature(rate, t, wait=False):
        """Set ramp rate (°C/min) and move to target temperature."""
        yield from bps.mv(linkam.ramprate.setpoint, rate)
        yield from linkam.set_target(t, wait=wait)

    # =========================================================================
    # EXECUTION SEQUENCE
    # =========================================================================

    isDebugMode = linkam_debug.get()
    recordFunctionRun()

    logger.info(
        "Starting linkam_zhang | sample=%s | pos=(%.1f, %.1f) | thickness=%.2f | debug=%s",
        sample_name, pos_X, pos_Y, thickness, isDebugMode,
    )

    # --- Block 1: Startup ---------------------------------------------------
    if not isDebugMode:
        logger.info("Running before_command_list()")
        yield from before_command_list()
    else:
        logger.info("[DEBUG] Skipping before_command_list()")

    appendToMdFile(
        f"## linkam_zhang: {sample_name}\n"
        f"- Position: X={pos_X}, Y={pos_Y}, thickness={thickness} mm\n"
        f"- Ramp to {TEMP_TARGET} °C at {RAMP_RATE} °C/min\n"
        f"- Hold {HOLD_HOURS} h, then cool to {TEMP_START} °C at {RAMP_RATE} °C/min"
    )

    # --- Block 2: Go to 40 °C, collect baseline ----------------------------
    logger.info("Block 2: going to %.0f °C for baseline dataset", TEMP_START)
    appendToMdFile(f"Going to {TEMP_START} °C — baseline dataset")
    yield from change_rate_and_temperature(RAMP_RATE, TEMP_START, wait=True)
    t0 = time.time()
    logger.info("At %.0f °C — collecting baseline", TEMP_START)
    yield from collectAllThree(isDebugMode)

    # --- Block 3: Ramp to 1100 °C (no data during ramp) --------------------
    logger.info(
        "Block 3: ramping to %.0f °C at %.0f °C/min (no data during ramp)",
        TEMP_TARGET, RAMP_RATE,
    )
    appendToMdFile(
        f"Ramping to {TEMP_TARGET} °C at {RAMP_RATE} °C/min — no data collection during ramp"
    )
    yield from change_rate_and_temperature(RAMP_RATE, TEMP_TARGET, wait=True)

    # Reset t0 — sample names now show minutes elapsed since hold started.
    t0 = time.time()
    logger.info("Reached %.0f °C — starting %.0f h hold", TEMP_TARGET, HOLD_HOURS)
    appendToMdFile(f"Reached {TEMP_TARGET} °C — holding for {HOLD_HOURS} h")

    # --- Block 4: Hold at 1100 °C for 4 hours, collect continuously --------
    hold_end = t0 + HOLD_HOURS * HOUR
    hold_count = 0
    while time.time() < hold_end:
        hold_count += 1
        elapsed_min = (time.time() - t0) / MINUTE
        logger.info(
            "Hold dataset %d | elapsed %.1f / %.0f min | Linkam=%.1f °C",
            hold_count, elapsed_min, HOLD_HOURS * 60, linkam.temperature.position,
        )
        yield from collectAllThree(isDebugMode)

    appendToMdFile(
        f"Hold complete: {hold_count} dataset(s) collected at {TEMP_TARGET} °C"
    )

    # --- Block 5: Cool to 40 °C (no data during cooling) -------------------
    logger.info(
        "Block 5: cooling to %.0f °C at %.0f °C/min (no data during cooling)",
        TEMP_START, RAMP_RATE,
    )
    appendToMdFile(
        f"Cooling to {TEMP_START} °C at {RAMP_RATE} °C/min — no data collection during cooling"
    )
    yield from change_rate_and_temperature(RAMP_RATE, TEMP_START, wait=True)

    # Reset t0 for the final dataset name to show 0 min.
    t0 = time.time()
    logger.info("Cooled to %.0f °C — collecting final dataset", TEMP_START)
    appendToMdFile(f"Reached {TEMP_START} °C — final dataset")

    # --- Block 6: Final dataset at 40 °C ------------------------------------
    yield from collectAllThree(isDebugMode)

    # --- Block 7: Teardown --------------------------------------------------
    if not isDebugMode:
        logger.info("Running after_command_list()")
        yield from after_command_list()
    else:
        logger.info("[DEBUG] Skipping after_command_list()")

    appendToMdFile(f"linkam_zhang complete: {sample_name}")
    logger.info("Plan complete: %s", sample_name)
