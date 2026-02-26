"""
AI-assisted template for finite time-resolved data collection plans.

==============================================================================
PURPOSE AND USAGE FOR AI PLAN DEVELOPMENT
==============================================================================

This file is the recommended starting point when an AI assistant (e.g. Claude)
is asked to write a custom ambient-temperature time-series or kinetics plan.

These plans do NOT control temperature — they collect repeated USAXS/SAXS/WAXS
datasets at fixed sample positions for a user-specified duration.  They are used
for:
    - Kinetics measurements (reaction, crystallisation, gelation, etc.)
    - Time-series at room temperature (beam-induced changes, slow dynamics)
    - Multi-sample parallel measurements (several positions on a sample holder)
    - Spatial mapping combined with time-series (y-drift variant)

Workflow for AI-assisted plan creation:
    1. User describes their experiment (how many positions, how long, which
       detectors, whether positions shift over time, single vs multi-position).
    2. AI picks the closest template variant below and copies it to a new file.
    3. AI fills in the SampleList, adjusts parameters, selects detectors, and
       updates the docstring.
    4. Load the file:
           %run -im usaxs.user.<new_filename>
    5. Test in debug mode:
           loop_debug.put(True)
           RE(myNewPlan(...))
    6. Real run:
           loop_debug.put(False)
           RE(myNewPlan(...))

==============================================================================
TEMPLATE VARIANTS IN THIS FILE
==============================================================================

1. myFiniteLoop_AI_template(pos_X, pos_Y, thickness, scan_title, delay_min)
       Single fixed position, time-based loop.
       Simplest possible plan — use as the default starting point.

2. myFiniteMultiPosLoop_AI_template(delay_min)
       Multiple positions defined in a module-level SampleList, time-based.
       Per-position sequential collection: USAXS→SAXS→WAXS per spot.
       Most common multi-sample plan.

3. myFiniteListLoop_AI_template(delay_min)
       Multiple positions, grouped-detector collection order:
       all-USAXS → all-SAXS → all-WAXS per complete round.
       Use when minimising detector-switching overhead matters more than
       grouping all data for one sample together.

4. myFiniteYDriftLoop_AI_template(numIterations, yOffset)
       Fixed number of complete iterations with a per-iteration Y-position drift.
       Use for radiation-dose spreading or spatial mapping over time.
       Sample names encode iteration number (not elapsed time).

==============================================================================
CHOOSING A VARIANT (guide for AI)
==============================================================================

User says...                                     → Use variant
"collect data for N minutes at one spot"         → 1 (single position)
"several samples in the beam at once"            → 2 (multi-pos)
"multiple positions, kinetics"                   → 2 (multi-pos)
"all USAXS first, then SAXS, then WAXS"         → 3 (grouped detector)
"N iterations, move sample a little each time"   → 4 (y-drift)
"only WAXS" or "only USAXS+SAXS"                → modify collectAllThree
                                                    in any variant

==============================================================================
DEBUG MODE
==============================================================================

loop_debug.put(True)   → skip instrument operations, print names, sleep
loop_debug.put(False)  → normal data collection (default)

In debug mode:
    - before_command_list() / after_command_list() are SKIPPED
    - Data-collection calls print the sample name + position and sleep briefly
    - No stage motion, no beam

==============================================================================
SAMPLE NAMING CONVENTIONS
==============================================================================

Time-based (most plans):
    {scan_title}_{elapsed_minutes:.0f}min
    Reset t0 = time.time() at plan start. Time counts from then.

Counter-based (grouped-detector variant):
    {scan_title}_{counter}
    counter increments once per complete round.

Iteration-based (y-drift variant):
    {scan_title}_{iteration_index}
    Encodes which iteration this scan belongs to.

==============================================================================
DETECTOR SELECTION GUIDE (for AI)
==============================================================================

Full sequence (default):
    USAXS → SAXS → WAXS  (all three, per position)

USAXS + SAXS only (faster, complementary q-range):
    Comment out the waxsExp block inside collectAllThree.

WAXS only (fastest, ~2–3 min/frame):
    Comment out USAXSscan and saxsExp; keep only waxsExp.
    Use sync_order_numbers() only when combining with USAXS in the same session.

SAXS only:
    Comment out USAXSscan and waxsExp; keep saxsExp.

When changing detectors, update the function docstring and appendToMdFile
message at plan start to reflect the actual detectors collected.

==============================================================================
SAMPLELIST FORMAT
==============================================================================

Define at MODULE LEVEL (top of file, not inside a function) so users can
edit and reload without rewriting the function:

    SampleList = [
        [pos_X_mm, pos_Y_mm, thickness_mm, "SampleName"],
        ...
    ]

Each entry corresponds to one beam position on the sample holder.
Iterate as:
    for pos_X, pos_Y, thickness, scan_title in SampleList:
        yield from collectAllThree(pos_X, pos_Y, thickness, scan_title, isDebugMode)

For single-position plans, pass pos_X, pos_Y, thickness, scan_title as
function arguments instead.

==============================================================================
OBSIDIAN LOGGING GUIDE
==============================================================================

appendToMdFile() writes to the user's Obsidian notebook. Call at:
    - Plan start (sample name(s), duration, key parameters)
    - Plan end (number of rounds/iterations completed, elapsed time)

Do NOT call inside the data-collection loop — that floods the notebook.
One line at start, one line at end is sufficient for ambient-temperature plans.

==============================================================================
CUSTOMISATION CHECKLIST FOR AI
==============================================================================

    [ ] Rename the function
    [ ] Edit SampleList (module level for multi-position variants)
    [ ] Choose detectors (full / USAXS+SAXS / WAXS only)
    [ ] Choose naming convention (time / counter / iteration)
    [ ] Set default delay_min or numIterations to match the experiment
    [ ] Update appendToMdFile messages to name the actual detectors used
    [ ] Confirm debug guards are in place for before/after_command_list
    [ ] If using y-drift, set yOffset = total_Y_motion / numIterations

CHANGE LOG:
    * JIL, 2026-02-25 : Initial AI-development template
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
from usaxs.utils.obsidian import appendToMdFile

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
# MODULE-LEVEL SampleList
# Edit before each run, then reload the file.
# Used by the multi-position variants (Templates 2, 3).
# ==============================================================================

# Format: [pos_X_mm, pos_Y_mm, thickness_mm, "SampleName"]
SampleList = [
    [0.0, 0.0, 1.0, "SamplePos1"],
    [5.0, 0.0, 1.0, "SamplePos2"],
    # [10.0, 0.0, 1.0, "SamplePos3"],  # uncomment to add positions
]


# ==============================================================================
# TEMPLATE 1: Single fixed position, time-based loop
# ==============================================================================

# DO NOT MODIFY THIS TEMPLATE — copy to a new file and rename.
def myFiniteLoop_AI_template(
    pos_X, pos_Y, thickness, scan_title, delay_min, md={}
):
    """
    Collect USAXS/SAXS/WAXS at one fixed position for delay_min minutes.

    Parameters
    ----------
    pos_X, pos_Y : float
        Sample stage position in mm.
    thickness : float
        Sample thickness in mm.
    scan_title : str
        Base name for all scans.
    delay_min : float
        Total run time in minutes.
    md : dict, optional
        Extra metadata.

    Load:
        %run -im usaxs.user.finite_loop_template

    Debug mode (no instrument):
        loop_debug.put(True)

    Run:
        RE(myFiniteLoop_AI_template(0, 0, 1.0, "MySample", 60))
    """

    # ------------------------------------------------------------------
    # Inner helper functions
    # ------------------------------------------------------------------

    def getSampleName():
        """
        Return sample name encoding scan_title and elapsed minutes since t0.
        Format: {scan_title}_{elapsed_minutes:.0f}min
        """
        return f"{scan_title}_{(time.time() - t0) / 60:.0f}min"

    def collectAllThree(debug=False):
        """
        Collect USAXS → SAXS → WAXS at (pos_X, pos_Y).

        getSampleName() is called before each detector so the filename reflects
        conditions at acquisition time.  sync_order_numbers() groups all three
        into a single scan-group entry.

        Parameters
        ----------
        debug : bool
            True → print sample name and sleep (no instrument motion).
            Pass isDebugMode — never hardcode True or False.
        """
        if debug:
            sampleMod = getSampleName()
            print(f"[DEBUG] collectAllThree: {sampleMod}  pos=({pos_X}, {pos_Y})")
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

    # ------------------------------------------------------------------
    # Execution sequence
    # ------------------------------------------------------------------

    isDebugMode = loop_debug.get()
    logger.info(
        "Starting myFiniteLoop_AI_template | sample=%s | pos=(%.2f, %.2f) "
        "| duration=%s min | debug=%s",
        scan_title, pos_X, pos_Y, delay_min, isDebugMode,
    )

    if not isDebugMode:
        yield from before_command_list()
    else:
        logger.info("[DEBUG] Skipping before_command_list()")

    appendToMdFile(
        f"Starting finite loop: sample={scan_title}, "
        f"pos=({pos_X}, {pos_Y}), thickness={thickness} mm, "
        f"USAXS+SAXS+WAXS for {delay_min} min"
    )

    t0 = time.time()
    checkpoint = time.time() + delay_min * MINUTE
    loop_count = 0

    logger.info("Collecting USAXS/SAXS/WAXS for %s minutes", delay_min)

    while time.time() < checkpoint:
        logger.debug(
            "Loop %d: %.1f min remaining",
            loop_count, (checkpoint - time.time()) / MINUTE,
        )
        yield from collectAllThree(isDebugMode)
        loop_count += 1

    elapsed_min = (time.time() - t0) / MINUTE
    logger.info(
        "myFiniteLoop_AI_template finished | %d rounds | %.1f min elapsed",
        loop_count, elapsed_min,
    )
    appendToMdFile(
        f"Finite loop complete: {scan_title}, "
        f"{loop_count} rounds, {elapsed_min:.0f} min elapsed"
    )

    if not isDebugMode:
        yield from after_command_list()
    else:
        logger.info("[DEBUG] Skipping after_command_list()")


# ==============================================================================
# TEMPLATE 2: Multi-position, per-position sequential collection
# USAXS→SAXS→WAXS at each position before moving to the next.
# Uses module-level SampleList.
# ==============================================================================

# DO NOT MODIFY THIS TEMPLATE — copy to a new file and rename.
def myFiniteMultiPosLoop_AI_template(delay_min, md={}):
    """
    Cycle through SampleList collecting USAXS/SAXS/WAXS per position.

    Each loop pass visits every entry in SampleList in order, collecting a
    complete USAXS → SAXS → WAXS sequence before moving to the next position.
    The outer loop repeats until delay_min minutes have elapsed.

    Edit SampleList at the top of this file, then reload and run.

    Parameters
    ----------
    delay_min : float
        Total run time in minutes.
    md : dict, optional
        Extra metadata.

    Load:
        %run -im usaxs.user.finite_loop_template

    Debug mode:
        loop_debug.put(True)

    Run:
        RE(myFiniteMultiPosLoop_AI_template(120))
    """

    # ------------------------------------------------------------------
    # Inner helper functions
    # pos_X, pos_Y, thickness, and scan_title are provided by the
    # enclosing for-loop over SampleList at call time.
    # ------------------------------------------------------------------

    def getSampleName(scan_title):
        """
        Return sample name encoding the given scan_title and elapsed minutes.
        scan_title is passed explicitly so each SampleList entry gets its own name.
        """
        return f"{scan_title}_{(time.time() - t0) / 60:.0f}min"

    def collectAllThree(pos_X, pos_Y, thickness, scan_title, debug=False):
        """
        Collect USAXS → SAXS → WAXS for one SampleList position.

        Parameters
        ----------
        pos_X, pos_Y : float  — stage position for this sample
        thickness : float     — sample thickness
        scan_title : str      — name for this sample (from SampleList)
        debug : bool          — pass isDebugMode
        """
        if debug:
            sampleMod = getSampleName(scan_title)
            print(f"[DEBUG] collectAllThree [{scan_title}]: {sampleMod}  pos=({pos_X}, {pos_Y})")
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
    logger.info(
        "Starting myFiniteMultiPosLoop_AI_template | %d positions | "
        "duration=%s min | debug=%s",
        len(SampleList), delay_min, isDebugMode,
    )

    if not isDebugMode:
        yield from before_command_list()
    else:
        logger.info("[DEBUG] Skipping before_command_list()")

    sample_names = ", ".join(s[3] for s in SampleList)
    appendToMdFile(
        f"Starting multi-position finite loop: {len(SampleList)} positions "
        f"({sample_names}), USAXS+SAXS+WAXS per position, {delay_min} min"
    )

    t0 = time.time()
    checkpoint = time.time() + delay_min * MINUTE
    round_count = 0

    logger.info(
        "Cycling through %d positions for %s minutes", len(SampleList), delay_min
    )

    while time.time() < checkpoint:
        logger.debug(
            "Round %d: %.1f min remaining",
            round_count, (checkpoint - time.time()) / MINUTE,
        )
        for pos_X, pos_Y, thickness, scan_title in SampleList:
            yield from collectAllThree(pos_X, pos_Y, thickness, scan_title, isDebugMode)
        round_count += 1

    elapsed_min = (time.time() - t0) / MINUTE
    logger.info(
        "myFiniteMultiPosLoop_AI_template finished | %d rounds | %.1f min elapsed",
        round_count, elapsed_min,
    )
    appendToMdFile(
        f"Multi-position finite loop complete: {len(SampleList)} positions, "
        f"{round_count} rounds, {elapsed_min:.0f} min elapsed"
    )

    if not isDebugMode:
        yield from after_command_list()
    else:
        logger.info("[DEBUG] Skipping after_command_list()")


# ==============================================================================
# TEMPLATE 3: Multi-position, grouped-detector collection order
# all-USAXS → all-SAXS → all-WAXS per complete round.
# Uses module-level SampleList. Sample names use an integer counter.
# ==============================================================================

# DO NOT MODIFY THIS TEMPLATE — copy to a new file and rename.
def myFiniteListLoop_AI_template(delay_min, md={}):
    """
    Cycle through SampleList with grouped detector order for delay_min minutes.

    Each complete round:
        1. USAXSscan at every position in SampleList
        2. saxsExp   at every position in SampleList
        3. waxsExp   at every position in SampleList

    Use this variant when minimising the total USAXS↔SAXS mode-switch overhead
    is more important than grouping all scans for a single sample together.
    Sample names use an integer counter (increments once per complete round)
    rather than elapsed time.

    Edit SampleList at the top of this file, then reload and run.

    Parameters
    ----------
    delay_min : float
        Total run time in minutes.
    md : dict, optional
        Extra metadata.

    Load:
        %run -im usaxs.user.finite_loop_template

    Debug mode:
        loop_debug.put(True)

    Run:
        RE(myFiniteListLoop_AI_template(120))
    """

    # ------------------------------------------------------------------
    # Inner helper functions
    # ------------------------------------------------------------------

    def getSampleName(scan_title):
        """
        Return sample name encoding the scan_title and current integer counter.
        Format: {scan_title}_{counter}
        counter is incremented once per complete round in the execution block.
        """
        return f"{scan_title}_{counter}"

    def collectRound(debug=False):
        """
        One complete grouped-detector round for all positions in SampleList.

        Order: all-USAXS, then all-SAXS, then all-WAXS.
        sync_order_numbers() is NOT called here because the three detector
        passes are time-separated and treated as independent scan groups.

        Parameters
        ----------
        debug : bool
            True → print names and positions for the entire round, then sleep.
        """
        if debug:
            for pos_X, pos_Y, thickness, scan_title in SampleList:
                sampleMod = getSampleName(scan_title)
                print(
                    f"[DEBUG] round {counter} | "
                    f"USAXS: {sampleMod}  pos=({pos_X}, {pos_Y})"
                )
            yield from bps.sleep(1)
        else:
            # --- All USAXS ---
            for pos_X, pos_Y, thickness, scan_title in SampleList:
                sampleMod = getSampleName(scan_title)
                md["title"] = sampleMod
                logger.info("USAXSscan [round %d]: %s", counter, sampleMod)
                yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})

            # --- All SAXS ---
            for pos_X, pos_Y, thickness, scan_title in SampleList:
                sampleMod = getSampleName(scan_title)
                md["title"] = sampleMod
                logger.info("saxsExp [round %d]: %s", counter, sampleMod)
                yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

            # --- All WAXS ---
            for pos_X, pos_Y, thickness, scan_title in SampleList:
                sampleMod = getSampleName(scan_title)
                md["title"] = sampleMod
                logger.info("waxsExp [round %d]: %s", counter, sampleMod)
                yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    # ------------------------------------------------------------------
    # Execution sequence
    # ------------------------------------------------------------------

    isDebugMode = loop_debug.get()
    logger.info(
        "Starting myFiniteListLoop_AI_template (grouped detectors) | "
        "%d positions | duration=%s min | debug=%s",
        len(SampleList), delay_min, isDebugMode,
    )

    if not isDebugMode:
        yield from before_command_list()
    else:
        logger.info("[DEBUG] Skipping before_command_list()")

    sample_names = ", ".join(s[3] for s in SampleList)
    appendToMdFile(
        f"Starting grouped-detector finite loop: {len(SampleList)} positions "
        f"({sample_names}), all-USAXS→all-SAXS→all-WAXS order, {delay_min} min"
    )

    t0 = time.time()
    counter = 0
    checkpoint = time.time() + delay_min * MINUTE

    logger.info(
        "Grouped detector collection (%d samples/round) for %s minutes",
        len(SampleList), delay_min,
    )

    while time.time() < checkpoint:
        logger.debug(
            "Round %d: %.1f min remaining",
            counter, (checkpoint - time.time()) / MINUTE,
        )
        yield from collectRound(isDebugMode)
        counter += 1

    elapsed_min = (time.time() - t0) / MINUTE
    logger.info(
        "myFiniteListLoop_AI_template finished | %d rounds | %.1f min elapsed",
        counter, elapsed_min,
    )
    appendToMdFile(
        f"Grouped-detector finite loop complete: {len(SampleList)} positions, "
        f"{counter} rounds, {elapsed_min:.0f} min elapsed"
    )

    if not isDebugMode:
        yield from after_command_list()
    else:
        logger.info("[DEBUG] Skipping after_command_list()")


# ==============================================================================
# TEMPLATE 4: Fixed number of iterations with per-iteration Y-position drift
# Collection order: USAXS→SAXS→WAXS per position, per iteration.
# Sample names encode the iteration number.
# ==============================================================================

# DO NOT MODIFY THIS TEMPLATE — copy to a new file and rename.
def myFiniteYDriftLoop_AI_template(numIterations, yOffset, md={}):
    """
    Run numIterations complete passes over SampleList with a Y-position drift.

    On each pass the Y position of every sample is shifted by yOffset relative
    to the nominal value, so successive passes probe slightly different spots.
    Uses the module-level SampleList (pos_Y in SampleList is the nominal value).

    Use cases:
        - Spreading radiation dose over a larger sample area
        - Spatial mapping: systematic scan across the sample
        - Avoiding beam-damage accumulation on sensitive samples

    Sample name format:  {scan_title}_{iteration_number}

    Parameters
    ----------
    numIterations : int
        Total number of complete passes through SampleList.
    yOffset : float
        Y shift in mm applied per iteration.
        Total Y travel = numIterations × yOffset.
        Example: 50 iterations × 0.06 mm = 3.0 mm total.
    md : dict, optional
        Extra metadata.

    Load:
        %run -im usaxs.user.finite_loop_template

    Debug mode:
        loop_debug.put(True)

    Run:
        RE(myFiniteYDriftLoop_AI_template(50, 0.06))
    """

    # ------------------------------------------------------------------
    # Inner helper functions
    # pos_X, pos_Y, thickness, and scan_title are provided by the
    # enclosing for-loop over SampleList at call time.
    # ------------------------------------------------------------------

    def getSampleName(scan_title):
        """
        Return sample name encoding the scan_title and current iteration index.
        Format: {scan_title}_{iteration_index}
        """
        return f"{scan_title}_{iteration}"

    def collectAllThree(pos_X, pos_Y, thickness, scan_title, debug=False):
        """
        Collect USAXS → SAXS → WAXS for one SampleList position.

        pos_Y passed here already includes the iteration drift offset.

        Parameters
        ----------
        pos_X, pos_Y : float  — stage position (pos_Y includes drift offset)
        thickness : float     — sample thickness
        scan_title : str      — name for this sample
        debug : bool          — pass isDebugMode
        """
        if debug:
            sampleMod = getSampleName(scan_title)
            print(
                f"[DEBUG] iter {iteration} | [{scan_title}]: {sampleMod}  "
                f"pos=({pos_X}, {pos_Y:.3f})  drift={iteration * yOffset:.3f} mm"
            )
            yield from bps.sleep(1)
        else:
            yield from sync_order_numbers()
            sampleMod = getSampleName(scan_title)
            md["title"] = sampleMod
            logger.info("USAXSscan [iter %d, %s]: %s", iteration, scan_title, sampleMod)
            yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = getSampleName(scan_title)
            md["title"] = sampleMod
            logger.info("saxsExp [iter %d, %s]: %s", iteration, scan_title, sampleMod)
            yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = getSampleName(scan_title)
            md["title"] = sampleMod
            logger.info("waxsExp [iter %d, %s]: %s", iteration, scan_title, sampleMod)
            yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    # ------------------------------------------------------------------
    # Execution sequence
    # ------------------------------------------------------------------

    isDebugMode = loop_debug.get()
    total_y = numIterations * yOffset
    logger.info(
        "Starting myFiniteYDriftLoop_AI_template | %d iterations | "
        "yOffset=%.3f mm (total %.2f mm) | %d samples | debug=%s",
        numIterations, yOffset, total_y, len(SampleList), isDebugMode,
    )

    if not isDebugMode:
        yield from before_command_list()
    else:
        logger.info("[DEBUG] Skipping before_command_list()")

    sample_names = ", ".join(s[3] for s in SampleList)
    appendToMdFile(
        f"Starting Y-drift finite loop: {numIterations} iterations, "
        f"{len(SampleList)} positions ({sample_names}), "
        f"yOffset={yOffset} mm (total {total_y:.2f} mm)"
    )

    t0 = time.time()

    for iteration in range(numIterations):
        elapsed_min = (time.time() - t0) / MINUTE
        logger.info(
            "Iteration %d/%d  (%.1f min elapsed)",
            iteration + 1, numIterations, elapsed_min,
        )
        for pos_X, pos_Y_nominal, thickness, scan_title in SampleList:
            # Apply the cumulative Y drift for this iteration.
            pos_Y = pos_Y_nominal + iteration * yOffset
            yield from collectAllThree(pos_X, pos_Y, thickness, scan_title, isDebugMode)

    elapsed_min = (time.time() - t0) / MINUTE
    logger.info(
        "myFiniteYDriftLoop_AI_template finished | %d iterations | %.1f min total",
        numIterations, elapsed_min,
    )
    appendToMdFile(
        f"Y-drift finite loop complete: {numIterations} iterations, "
        f"{len(SampleList)} positions, {elapsed_min:.0f} min total"
    )

    if not isDebugMode:
        yield from after_command_list()
    else:
        logger.info("[DEBUG] Skipping after_command_list()")
