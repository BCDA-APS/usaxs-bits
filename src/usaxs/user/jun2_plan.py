"""
User jun2 — multi-sample time-series plan with inter-pass sleep.

Collects USAXS → SAXS → WAXS at every position in SampleList, sleeps for
sleep_min minutes, then repeats the full sample loop until delay_min minutes
have elapsed.

==============================================================================
EDIT BEFORE EACH RUN
==============================================================================

1.  Update SampleList below (module level) with the correct positions,
    thicknesses, and names for your samples.
2.  Reload the file:
        %run -im usaxs.user.jun2_plan
3.  Test in debug mode (no instrument motion):
        loop_debug.put(True)
        RE(jun2MultiSampleLoop(delay_min=10, sleep_min=1))
4.  Real run:
        loop_debug.put(False)
        RE(jun2MultiSampleLoop(delay_min=120, sleep_min=5))

==============================================================================
SAMPLELIST FORMAT
==============================================================================

    [pos_X_mm, pos_Y_mm, thickness_mm, "SampleName"]

Each row is one beam position on the sample holder.  The function visits them
in order, top to bottom, for every pass.

==============================================================================
SAMPLE NAMING
==============================================================================

Each scan file is named:  {SampleName}_{elapsed_minutes:.0f}min
Elapsed time resets to 0 at the start of the plan (not at each pass).

==============================================================================
PARAMETERS
==============================================================================

delay_min  : total duration of the outer loop in minutes.
sleep_min  : idle time between consecutive complete passes through SampleList.
             Set to 0 to collect passes back-to-back with no wait.

CHANGE LOG:
    * JIL, 2026-03-11 : Initial plan for user jun2 (AI-generated)
"""

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

import time

from bluesky import plan_stubs as bps
from usaxs.plans.plans_user_facing import saxsExp
from usaxs.plans.plans_user_facing import waxsExp
from usaxs.plans.plans_usaxs import USAXSscan
from usaxs.plans.command_list import after_command_list, sync_order_numbers
from usaxs.plans.command_list import before_command_list
from ophyd import Signal
from usaxs.utils.obsidian import appendToMdFile, recordFunctionRun

# Convenient time-unit constants.
SECOND = 1
MINUTE = 60 * SECOND
HOUR = 60 * MINUTE
DAY = 24 * HOUR

# Debug / dry-run flag.
#   loop_debug.put(True)   → debug mode on  (no instrument operations)
#   loop_debug.put(False)  → normal mode on (default)
loop_debug = Signal(name="loop_debug", value=False)

# ==============================================================================
# MODULE-LEVEL SampleList  ← EDIT THIS before each run, then reload the file.
# Format: [pos_X_mm, pos_Y_mm, thickness_mm, "SampleName"]
# ==============================================================================

SampleList = [
    [0.0,  0.0, 1.0, "jun2_sample1"],
    [5.0,  0.0, 1.0, "jun2_sample2"],
    [10.0, 0.0, 1.0, "jun2_sample3"],
    # Add or remove rows as needed; number of samples is set by this list.
]


# ==============================================================================
# PLAN: Multi-sample loop with inter-pass sleep
# ==============================================================================

def jun2MultiSampleLoop(delay_min, sleep_min, md={}):
    """
    Collect USAXS/SAXS/WAXS at every SampleList position, sleep, then repeat.

    One "pass" = visiting every entry in SampleList in order and collecting a
    complete USAXS → SAXS → WAXS sequence at each position before moving on.
    After every pass the plan sleeps for sleep_min minutes, then checks whether
    delay_min has elapsed.  If time remains, a new pass begins.

    Edit SampleList at the top of this file, then reload and run.

    Parameters
    ----------
    delay_min : float
        Total plan duration in minutes.  The plan exits after the first pass
        that completes after this deadline.
    sleep_min : float
        Sleep time in minutes between consecutive passes.  Use 0 for
        back-to-back collection with no idle period.
    md : dict, optional
        Extra metadata forwarded to each scan.

    Load:
        %run -im usaxs.user.jun2_plan

    Debug mode (no instrument motion, prints only):
        loop_debug.put(True)

    Run:
        RE(jun2MultiSampleLoop(delay_min=120, sleep_min=5))
    """

    # ------------------------------------------------------------------
    # Inner helper functions
    # ------------------------------------------------------------------

    def getSampleName(scan_title):
        """
        Return scan name encoding scan_title and elapsed minutes since t0.
        Format: {scan_title}_{elapsed_minutes:.0f}min
        """
        return f"{scan_title}_{(time.time() - t0) / 60:.0f}min"

    def collectAllThree(pos_X, pos_Y, thickness, scan_title, debug=False):
        """
        Collect USAXS → SAXS → WAXS for one SampleList entry.

        Parameters
        ----------
        pos_X, pos_Y : float
            Stage position in mm for this sample.
        thickness : float
            Sample thickness in mm.
        scan_title : str
            Base name for this sample (from SampleList).
        debug : bool
            True → print sample name and position, sleep briefly.
            Always pass isDebugMode — never hardcode True or False.
        """
        if debug:
            sampleMod = getSampleName(scan_title)
            print(
                f"[DEBUG] collectAllThree [{scan_title}]: {sampleMod}"
                f"  pos=({pos_X}, {pos_Y})"
            )
            yield from bps.sleep(20)
        else:
            yield from sync_order_numbers()
            sampleMod = getSampleName(scan_title)
            md["title"] = sampleMod
            logger.info("USAXSscan [%s]: %s", scan_title, sampleMod)
            yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})

            sampleMod = getSampleName(scan_title)
            md["title"] = sampleMod
            logger.info("saxsExp [%s]: %s", scan_title, sampleMod)
            yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

            sampleMod = getSampleName(scan_title)
            md["title"] = sampleMod
            logger.info("waxsExp [%s]: %s", scan_title, sampleMod)
            yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    # ------------------------------------------------------------------
    # Execution sequence
    # ------------------------------------------------------------------

    isDebugMode = loop_debug.get()
    recordFunctionRun()
    logger.info(
        "Starting jun2MultiSampleLoop | %d samples | "
        "duration=%s min | sleep=%s min | debug=%s",
        len(SampleList), delay_min, sleep_min, isDebugMode,
    )

    if not isDebugMode:
        yield from before_command_list()
    else:
        logger.info("[DEBUG] Skipping before_command_list()")

    sample_names = ", ".join(s[3] for s in SampleList)
    appendToMdFile(
        f"Starting jun2MultiSampleLoop: {len(SampleList)} samples "
        f"({sample_names}), USAXS+SAXS+WAXS per sample, "
        f"{delay_min} min total, {sleep_min} min sleep between passes"
    )

    t0 = time.time()
    checkpoint = time.time() + delay_min * MINUTE
    pass_count = 0

    logger.info(
        "Cycling through %d samples for %s minutes (%s min sleep between passes)",
        len(SampleList), delay_min, sleep_min,
    )

    while time.time() < checkpoint:
        logger.info(
            "Pass %d: %.1f min remaining",
            pass_count + 1, (checkpoint - time.time()) / MINUTE,
        )

        # Collect USAXS→SAXS→WAXS at every sample position.
        for pos_X, pos_Y, thickness, scan_title in SampleList:
            yield from collectAllThree(pos_X, pos_Y, thickness, scan_title, isDebugMode)

        pass_count += 1

        # Sleep between passes (skip if no time remains or sleep_min == 0).
        if sleep_min > 0 and time.time() < checkpoint:
            logger.info(
                "Pass %d complete — sleeping %.1f min before next pass",
                pass_count, sleep_min,
            )
            if isDebugMode:
                print(f"[DEBUG] Sleeping {sleep_min} min between passes")
            yield from bps.sleep(sleep_min * MINUTE)

    elapsed_min = (time.time() - t0) / MINUTE
    logger.info(
        "jun2MultiSampleLoop finished | %d passes | %.1f min elapsed",
        pass_count, elapsed_min,
    )
    appendToMdFile(
        f"jun2MultiSampleLoop complete: {len(SampleList)} samples, "
        f"{pass_count} passes, {elapsed_min:.0f} min elapsed"
    )

    if not isDebugMode:
        yield from after_command_list()
    else:
        logger.info("[DEBUG] Skipping after_command_list()")
