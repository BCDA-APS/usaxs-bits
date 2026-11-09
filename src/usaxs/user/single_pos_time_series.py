"""
Single-position time series: USAXS -> SAXS -> WAXS repeated for a total time.

Watch ONE sample position for a long time.  Each "cycle" collects USAXS, then
SAXS, then WAXS at (pos_X, pos_Y).  Between cycles the plan waits a fixed
delay.  Cycles keep starting until the requested total time is used up.

Sample thickness is fixed at 4 mm (THICKNESS_MM below) -- it is not a plan
argument.  Edit the constant at the top of this file if that ever changes.

Timing rules
------------
* total_min : time budget for the whole plan, measured from the start of the
  first cycle.  A new cycle is only started if it can START before total_min
  has elapsed.  A cycle that has already started is never cut short, so the
  plan can end up to roughly one cycle length (~10-15 min) after total_min.
* delay_min : pause AFTER a cycle finishes and BEFORE the next one starts
  (end-to-start gap, NOT start-to-start period).  So
      time between cycle starts  =  cycle duration  +  delay_min.
  Use delay_min = 0 for back-to-back cycles.  No delay is added after the
  last cycle.

Sample name format (elapsed time is rebuilt before EACH detector):
    {scan_title}_{elapsed_minutes}min        e.g.  Gel1_0min, Gel1_17min

Load:
    %run -im usaxs.user.single_pos_time_series

Dry run (no instrument motion, no beam; the delays still run in real time):
    watch_debug.put(True)
    RE(watchSamplePosition(10.0, 5.0, "Gel1", 20, 1))

Real run:
    watch_debug.put(False)
    RE(watchSamplePosition(10.0, 5.0, "Gel1", 240, 10))

If you abort (RE.abort() / Ctrl-C), after_command_list() does NOT run.
Run the teardown by hand afterwards:
    RE(after_command_list())
"""

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

import re
import time

from bluesky import plan_stubs as bps
from ophyd import Signal
from usaxs.plans.command_list import after_command_list
from usaxs.plans.command_list import before_command_list
from usaxs.plans.command_list import sync_order_numbers
from usaxs.plans.plans_usaxs import USAXSscan
from usaxs.plans.plans_user_facing import saxsExp
from usaxs.plans.plans_user_facing import waxsExp
from usaxs.utils.obsidian import appendToMdFile
from usaxs.utils.obsidian import recordFunctionRun

SECOND = 1
MINUTE = 60 * SECOND

# Sample thickness in mm -- always 4 mm for this experiment.
# It sets the transmission / absolute-intensity correction.
THICKNESS_MM = 4.0

# Debug / dry-run flag (module level, persists in the IPython session).
#   watch_debug.put(True)   -> no instrument operations
#   watch_debug.put(False)  -> real data collection (default)
watch_debug = Signal(name="watch_debug", value=False)


def watchSamplePosition(pos_X, pos_Y, scan_title, total_min, delay_min, md=None):
    """
    Collect USAXS -> SAXS -> WAXS at one position, repeatedly, for total_min.

    Parameters
    ----------
    pos_X, pos_Y : float
        Sample stage position in mm (sx, sy).
    scan_title : str
        Base sample name.  Use only letters, digits and "_" and keep it short
        (ideally < 15 characters, max ~25).  No spaces, "+", "-", "=" etc.
    total_min : float
        Total time budget in minutes.  No new cycle starts after this time.
    delay_min : float
        Wait in minutes between the END of one cycle and the START of the
        next.  0 = back-to-back.
    md : dict, optional
        Extra metadata.

    Run:
        RE(watchSamplePosition(10.0, 5.0, "Gel1", 240, 10))
    """
    if md is None:
        md = {}

    if total_min <= 0:
        raise ValueError(f"total_min must be > 0, got {total_min}")
    if delay_min < 0:
        raise ValueError(f"delay_min must be >= 0, got {delay_min}")
    if not re.fullmatch(r"[A-Za-z0-9_]+", scan_title):
        logger.warning(
            "scan_title %r has characters other than letters/digits/_ -- "
            "this can break the data pipeline; please rename it.",
            scan_title,
        )
    if len(scan_title) > 25:
        logger.warning("scan_title %r is longer than 25 characters.", scan_title)

    # ------------------------------------------------------------------
    # Inner helpers
    # ------------------------------------------------------------------

    def getSampleName():
        """Return {scan_title}_{elapsed minutes since t0}min."""
        return f"{scan_title}_{(time.time() - t0) / MINUTE:.0f}min"

    def collectAllThree(debug=False):
        """USAXS -> SAXS -> WAXS at (pos_X, pos_Y); name rebuilt before each."""
        if debug:
            sampleMod = getSampleName()
            print(f"[DEBUG] collectAllThree: {sampleMod}  pos=({pos_X}, {pos_Y})")
            yield from bps.sleep(20)
        else:
            yield from sync_order_numbers()
            sampleMod = getSampleName()
            md["title"] = sampleMod
            logger.info("USAXSscan: %s", sampleMod)
            yield from USAXSscan(pos_X, pos_Y, THICKNESS_MM, sampleMod, md={})
            sampleMod = getSampleName()
            md["title"] = sampleMod
            logger.info("saxsExp: %s", sampleMod)
            yield from saxsExp(pos_X, pos_Y, THICKNESS_MM, sampleMod, md={})
            sampleMod = getSampleName()
            md["title"] = sampleMod
            logger.info("waxsExp: %s", sampleMod)
            yield from waxsExp(pos_X, pos_Y, THICKNESS_MM, sampleMod, md={})

    def waitDelay(seconds):
        """Sleep for `seconds` in short chunks so pause/abort stay responsive."""
        end = time.time() + seconds
        while True:
            remaining = end - time.time()
            if remaining <= 0:
                break
            yield from bps.sleep(min(10, remaining))

    # ------------------------------------------------------------------
    # Execution sequence
    # ------------------------------------------------------------------

    isDebugMode = watch_debug.get()  # read once
    recordFunctionRun()
    logger.info(
        "Starting watchSamplePosition | sample=%s | pos=(%.3f, %.3f) | "
        "thickness=%.1f mm | total=%s min | delay=%s min | debug=%s",
        scan_title,
        pos_X,
        pos_Y,
        THICKNESS_MM,
        total_min,
        delay_min,
        isDebugMode,
    )

    if not isDebugMode:
        yield from before_command_list()
    else:
        logger.info("[DEBUG] Skipping before_command_list()")

    appendToMdFile(
        f"Starting single-position time series: sample={scan_title}, "
        f"pos=({pos_X}, {pos_Y}), thickness={THICKNESS_MM} mm, "
        f"USAXS+SAXS+WAXS every cycle, total={total_min} min, "
        f"delay between cycles={delay_min} min"
    )

    t0 = time.time()
    deadline = t0 + total_min * MINUTE
    cycle_count = 0

    while True:
        logger.info(
            "Cycle %d starting (%.1f min elapsed of %s)",
            cycle_count + 1,
            (time.time() - t0) / MINUTE,
            total_min,
        )
        yield from collectAllThree(isDebugMode)
        cycle_count += 1

        # Stop if the next cycle could not START before the deadline.
        next_start = time.time() + delay_min * MINUTE
        if next_start >= deadline:
            break

        if delay_min > 0:
            logger.info("Waiting %s min before next cycle", delay_min)
            yield from waitDelay(delay_min * MINUTE)

    elapsed_min = (time.time() - t0) / MINUTE
    logger.info(
        "watchSamplePosition finished | %d cycles | %.1f min elapsed",
        cycle_count,
        elapsed_min,
    )
    appendToMdFile(
        f"Single-position time series complete: {scan_title}, "
        f"{cycle_count} cycles, {elapsed_min:.0f} min elapsed"
    )

    if not isDebugMode:
        yield from after_command_list()
    else:
        logger.info("[DEBUG] Skipping after_command_list()")
