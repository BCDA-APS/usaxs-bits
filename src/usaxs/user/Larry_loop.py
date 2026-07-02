"""
Vertical-scan multi-sample plan: USAXS/SAXS/WAXS with sy stepping per sample.

PURPOSE:
    Collect USAXS → SAXS → WAXS cycles on a set of samples mounted on the
    vertical stage.  For each sample the beam steps from the top of the sample
    (syStart, lowest sy value) to the bottom (syEnd, highest sy value) in a
    fixed number of cycles.  The sy step size is calculated automatically from
    the sample's syStart, syEnd, and numSteps.  sx is fixed for each sample.
    Samples are measured one at a time, in the order listed in SampleList.

FILE-NAMING CONVENTION:
    Each scan file is named:   {sampleName}_{stepIndex}_{elapsedMin:.0f}min
        stepIndex  — cycle number within the sample, starting at 0
        elapsedMin — minutes elapsed since the *start of that sample* (resets
                     to 0 for each new sample)

LOADING:
    %run -im usaxs.user.Larry_loop

DEBUG / DRY-RUN MODE:
    loop_debug.put(True)   → enable debug mode (no instrument motion)
    loop_debug.put(False)  → restore normal operation (default)

EDIT BEFORE EACH RUN:
    1. Update SampleList below (module level) with correct positions, names, etc.
    2. Reload:  %run -im usaxs.user.Larry_loop
    3. Debug:   loop_debug.put(True) ; RE(larryVerticalScan())
    4. Run:     loop_debug.put(False); RE(larryVerticalScan())

FUNCTION:
    larryVerticalScan()
        Iterates through SampleList.  For each sample, steps sy from syStart
        to syEnd in numSteps increments, collecting a full USAXS/SAXS/WAXS
        cycle at each step.  before_command_list() / after_command_list() are
        called once at the start / end of the entire plan.

CHANGE LOG:
    * JIL, 2026-06-24 : Initial plan (AI-generated from Larry_loop template)
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
# MODULE-LEVEL SampleList  ← EDIT BEFORE EACH RUN, then reload.
#
# Columns:
#   sampleName : str   — base name for scan files
#   thickness  : float — sample thickness in mm
#   sx         : float — horizontal position (fixed for all steps on this sample)
#   syStart    : float — vertical start (top of sample, lowest sy value) in mm
#   syEnd      : float — vertical end   (bottom of sample, highest sy value) in mm
#   numSteps   : int   — number of USAXS/SAXS/WAXS cycles for this sample
#
# sy step size is calculated automatically per sample:
#   sy_step = (syEnd - syStart) / (numSteps - 1)   when numSteps > 1
#   (for numSteps == 1 the single scan is taken at syStart)
# ==============================================================================
SampleList = [
    # sampleName              thickness   sx      syStart  syEnd   numSteps
    ["Empty_Blank",            0.50,    42.2,   18.0,   23,     2],
    ["Water_Blank",            0.50,    45.1,   43.4,   47.4,     2],
    ["RbOH",                   0.50,    42.4,   69.2,   76.4,    40],
    ["NaOH",                   0.50,    44.6,   95.3,  102.3,    40],
    ["Empty_Blank",            0.50,    42.2,   18.0,   23,     2],
    ["Water_Blank",            0.50,    45.1,   43.4,   47.4,     2],
    ["NaNO2_10m",              0.50,    43.6,  122.6,  129.6,    40],
    ["RbNO2_10m",              0.50,    44.0,  151.3,  155.9,    40],
    ["RbNO2_55m",              0.50,    44.3,  173.7,  180.5,    40],
    ["Empty_Blank",            0.50,    42.2,   18.0,   23,     2],
    ["Water_Blank",            0.50,    45.1,   43.4,   47.4,     2],    
    ["BoehRbNO2_10m",          0.50,    87.8,  25.4,  31.2,    40],
    ["BoehNaNO2_10m",          0.50,    87.8,  50.2,  56.4,    40],
    ["Al10Na30Gel",            0.50,    86.8,  77.6,  84.0,    40],
]


# ==============================================================================
# PLAN: larryVerticalScan
# One-pass vertical scan across each sample in SampleList.
# ==============================================================================

def larryVerticalScan(md={}):
    """
    Step sy from syStart to syEnd for each sample, collecting USAXS/SAXS/WAXS.

    For each entry in SampleList the plan:
        1. Calculates the sy step size:
               sy_step = (syEnd - syStart) / (numSteps - 1)   (numSteps > 1)
        2. Iterates stepIndex from 0 to numSteps-1:
               sy = syStart + stepIndex * sy_step
        3. Collects USAXS → SAXS → WAXS at (sx, sy).
        4. Names each scan file: {sampleName}_{stepIndex}_{elapsedMin:.0f}min
           where elapsedMin is measured from the start of *this sample's* collection.

    before_command_list() and after_command_list() are called once for the
    entire plan (not once per sample).

    Edit SampleList at the top of this file, then reload and run:
        %run -im usaxs.user.Larry_loop

    Debug mode (no instrument motion):
        loop_debug.put(True)

    Run:
        RE(larryVerticalScan())
    """

    # ------------------------------------------------------------------
    # Inner helper functions
    # ------------------------------------------------------------------

    def getSampleName(sampleName, stepIndex, t_sample_start):
        """
        Return scan name encoding sample, step index, and elapsed minutes.

        Parameters
        ----------
        sampleName : str
            Base name for this sample.
        stepIndex : int
            Cycle index within this sample (0-based).
        t_sample_start : float
            time.time() value at the start of this sample's collection.

        Returns
        -------
        str
            Format: {sampleName}_{stepIndex}_{elapsedMin:.0f}min
        """
        elapsed_min = (time.time() - t_sample_start) / MINUTE
        return f"{sampleName}_{stepIndex}_{elapsed_min:.0f}min"

    def collectAllThree(sx, sy, thickness, sampleName, stepIndex, t_sample_start, debug=False):
        """
        Collect USAXS → SAXS → WAXS at (sx, sy) for one cycle.

        Parameters
        ----------
        sx : float
            Horizontal stage position in mm (fixed for this sample).
        sy : float
            Vertical stage position in mm (current step).
        thickness : float
            Sample thickness in mm.
        sampleName : str
            Base sample name (from SampleList).
        stepIndex : int
            Cycle index within this sample (for file naming).
        t_sample_start : float
            time.time() value at the start of this sample's collection.
        debug : bool
            True → print name/position and sleep (no instrument motion).
            Always pass isDebugMode — never hardcode True or False.
        """
        if debug:
            sampleMod = getSampleName(sampleName, stepIndex, t_sample_start)
            print(
                f"[DEBUG] collectAllThree [{sampleName}] step {stepIndex}: "
                f"{sampleMod}  pos=({sx}, {sy:.4f})"
            )
            yield from bps.sleep(5)
        else:
            yield from sync_order_numbers()

            sampleMod = getSampleName(sampleName, stepIndex, t_sample_start)
            md["title"] = sampleMod
            logger.info("USAXSscan [%s, step %d]: %s  sy=%.4f", sampleName, stepIndex, sampleMod, sy)
            yield from USAXSscan(sx, sy, thickness, sampleMod, md={})

            sampleMod = getSampleName(sampleName, stepIndex, t_sample_start)
            md["title"] = sampleMod
            logger.info("saxsExp [%s, step %d]: %s  sy=%.4f", sampleName, stepIndex, sampleMod, sy)
            yield from saxsExp(sx, sy, thickness, sampleMod, md={})

            sampleMod = getSampleName(sampleName, stepIndex, t_sample_start)
            md["title"] = sampleMod
            logger.info("waxsExp [%s, step %d]: %s  sy=%.4f", sampleName, stepIndex, sampleMod, sy)
            yield from waxsExp(sx, sy, thickness, sampleMod, md={})

    # ------------------------------------------------------------------
    # Execution sequence
    # ------------------------------------------------------------------

    isDebugMode = loop_debug.get()
    recordFunctionRun()

    total_cycles = sum(row[5] for row in SampleList)
    logger.info(
        "Starting larryVerticalScan | %d samples | %d total cycles | debug=%s",
        len(SampleList), total_cycles, isDebugMode,
    )

    if not isDebugMode:
        yield from before_command_list()
    else:
        logger.info("[DEBUG] Skipping before_command_list()")

    sample_names = ", ".join(row[0] for row in SampleList)
    appendToMdFile(
        f"Starting larryVerticalScan: {len(SampleList)} samples ({sample_names}), "
        f"{total_cycles} total USAXS+SAXS+WAXS cycles, vertical sy scan per sample"
    )

    t0_plan = time.time()

    for sampleName, thickness, sx, syStart, syEnd, numSteps in SampleList:
        # Calculate the sy step size for this sample.
        sy_step = (syEnd - syStart) / (numSteps - 1) if numSteps > 1 else 0.0

        logger.info(
            "larryVerticalScan: sample=%s | sx=%.3f | sy %.3f → %.3f in %d steps "
            "(step=%.4f mm) | thickness=%.3f mm",
            sampleName, sx, syStart, syEnd, numSteps, sy_step, thickness,
        )
        appendToMdFile(
            f"  Sample {sampleName}: sx={sx}, sy {syStart:.3f}→{syEnd:.3f}, "
            f"{numSteps} steps (sy_step={sy_step:.4f} mm)"
        )

        # Record the start time for this sample (elapsed time resets per sample).
        t_sample_start = time.time()

        for stepIndex in range(numSteps):
            sy = syStart + stepIndex * sy_step

            logger.info(
                "  %s: step %d/%d  sy=%.4f mm",
                sampleName, stepIndex + 1, numSteps, sy,
            )
            yield from collectAllThree(
                sx, sy, thickness, sampleName, stepIndex, t_sample_start, isDebugMode
            )

        sample_elapsed = (time.time() - t_sample_start) / MINUTE
        logger.info(
            "  %s: %d steps complete in %.1f min",
            sampleName, numSteps, sample_elapsed,
        )

    elapsed_min = (time.time() - t0_plan) / MINUTE
    logger.info(
        "larryVerticalScan finished | %d samples | %d cycles | %.1f min total",
        len(SampleList), total_cycles, elapsed_min,
    )
    appendToMdFile(
        f"larryVerticalScan complete: {len(SampleList)} samples, "
        f"{total_cycles} cycles, {elapsed_min:.0f} min total"
    )

    if not isDebugMode:
        yield from after_command_list()
    else:
        logger.info("[DEBUG] Skipping after_command_list()")
