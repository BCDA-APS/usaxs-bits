"""
Bluesky plans for finite time-resolved data collection at ambient temperature.

PURPOSE:
    These plans run repeated USAXS/SAXS/WAXS sequences over one or more sample
    positions for a fixed duration or a fixed number of iterations.  They are
    used for kinetics measurements, time-series, and any experiment that needs
    sequential data collection at room (ambient) temperature without active
    temperature control.

LOADING:
    %run -im usaxs.user.finite_loop

DEBUG / DRY-RUN MODE:
    loop_debug.put(True)   → enable debug mode (no instrument motion)
    loop_debug.put(False)  → restore normal operation (default)
    In debug mode, before_command_list() and after_command_list() are skipped
    and data-collection calls print the sample name and sleep briefly instead
    of moving the instrument.

FUNCTION INVENTORY:
    larryLoop(numIterations, yOffset)
        N complete iterations over a hardcoded position list with a per-iteration
        Y-position drift (simulates slow sample consumption or spatial mapping).
        Sample name encodes the iteration number.

    myFiniteLoop(pos_X, pos_Y, thickness, scan_title, delay1minutes)
        Single fixed position, runs for delay1minutes.  Collects USAXS + SAXS
        (WAXS intentionally disabled for this plan variant).
        Sample name encodes elapsed time in minutes.

    myTwoPosFiniteLoop(pos_XA, thicknessA, scan_titleA,
                       pos_XB, thicknessB, scan_titleB, delay1minutes)
        Alternates between two positions using the LAXm2 (SAMX) motor.
        Collects USAXS + SAXS at each position (WAXS intentionally disabled).
        The LAXm2 motor performs the actual stage motion; pos_X is passed as
        metadata only.  Sample name encodes elapsed time in minutes.

    myFiniteMultiPosLoop(delay1minutes)
        Cycles through a hardcoded SampleList collecting USAXS/SAXS/WAXS at
        each position in turn (per-position, sequential detector order).
        Runs until delay1minutes is exhausted.
        Sample name encodes elapsed time in minutes.

    myFiniteListLoop(delay1minutes, StartTime)
        Cycles through a hardcoded SampleList with a GROUPED detector order:
        all-USAXS for every sample, then all-SAXS for every sample, then
        all-WAXS for every sample (one complete round per loop iteration).
        Sample name encodes a sequential integer counter.
        StartTime parameter is retained for backwards compatibility but is
        currently unused.

SAMPLE NAMING CONVENTIONS:
    - Time-based names:      {scan_title}_{elapsed_minutes:.0f}min
    - Iteration-based names: {scan_title}_{iteration_number}
    - Counter-based names:   {scan_title}_{counter}

CHANGE LOG:
    * JIL, 2022-11-17 : first release
    * JIL, 2022-11-18 : added different modes
    * JIL, 2025-05-28 : fixes for BITS
    * JIL, 2025-07-09 : user changes
    * JIL, 2026-02-25 : AI-assisted documentation, Obsidian logging, bug fix
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
WEEK = 7 * DAY

# Debug / dry-run flag.
# Set at the IPython prompt before calling RE():
#   loop_debug.put(True)   → skip instrument operations, print names and sleep
#   loop_debug.put(False)  → real data collection (default)
loop_debug = Signal(name="loop_debug", value=False)


# ==============================================================================
# larryLoop
# N complete passes over a fixed sample list with a per-pass Y-position drift.
# Intended for long kinetics runs where each "frame" is one full pass.
# Sample names encode the iteration number (not time).
# ==============================================================================
def larryLoop(numIterations, yOffset, md={}):
    """
    Run numIterations complete passes over a hardcoded position list.

    On each pass the Y position of every sample is shifted by yOffset relative
    to its nominal value, so successive passes sample slightly different spots.
    This is used for kinetics experiments that accumulate a spatial drift to
    distribute radiation dose or probe sample heterogeneity.

    Sample name format:  {scan_title}_{iteration_number}

    Parameters
    ----------
    numIterations : int
        Total number of complete passes through ListOfSamples.
    yOffset : float
        Y shift in mm applied per iteration.
        After numIterations passes the total Y travel is numIterations * yOffset.
        Example: 50 iterations × 0.06 mm/iter = 3 mm total Y motion.
    md : dict, optional
        Extra metadata forwarded to scan functions.

    Edit ListOfSamples inside this function, reload, then run:
        RE(larryLoop(50, 0.06))
    """

    # Hardcoded sample list for this run.
    # Format: [pos_X_mm, pos_Y_mm (nominal), thickness_mm, "SampleName"]
    # The actual Y used is pos_Y + i * yOffset where i is the iteration index.
    ListOfSamples = [
        [42.9,   19.8, 0.48, "NaCl6m_LE"],
        [43.9,   48.2, 0.48, "RbCl6m_LE"],
        [44.9,   76.7, 0.48, "NaNO3p5m_LE"],
        [43.3,  105.1, 0.48, "RbNO3p5m_LE"],
        [89.0,   23.6, 0.48, "BoeNaCl6m_LE"],
        [89.0,   50.4, 0.48, "BoeRbCl6m_LE"],
        [88.8,   78.4, 0.48, "BoeNaNO3p5m_LE"],
        [89.0,  105.8, 0.48, "BoeRbNO3p5m_LE"],
    ]

    def setSampleName():
        """Return sample name encoding the scan title and current iteration index."""
        return f"{scan_title}_{i}"

    def collectAllThree(debug=False):
        """
        Collect USAXS → SAXS → WAXS for the current (pos_X, pos_Y, thickness, scan_title).

        pos_X, pos_Y, thickness, and scan_title are taken from the enclosing
        for-loop in the execution block.

        Parameters
        ----------
        debug : bool
            True → print sample name and sleep (no instrument motion).
        """
        sampleMod = setSampleName()
        if debug:
            print(f"[DEBUG] collectAllThree: {sampleMod}  pos=({pos_X}, {pos_Y})")
            yield from bps.sleep(1)
        else:
            yield from sync_order_numbers()
            md["title"] = sampleMod
            yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = setSampleName()
            md["title"] = sampleMod
            yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = setSampleName()
            md["title"] = sampleMod
            yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    # --- Execution sequence ---
    isDebugMode = loop_debug.get()
    logger.info(
        "Starting larryLoop | %d iterations | yOffset=%.3f mm | %d samples | debug=%s",
        numIterations, yOffset, len(ListOfSamples), isDebugMode,
    )

    if not isDebugMode:
        yield from before_command_list()
    else:
        logger.info("[DEBUG] Skipping before_command_list()")

    appendToMdFile(
        f"Starting larryLoop: {numIterations} iterations, "
        f"{len(ListOfSamples)} positions, yOffset={yOffset} mm"
    )

    t0 = time.time()

    for i in range(numIterations):
        logger.info(
            "larryLoop: iteration %d/%d  (elapsed %.1f min)",
            i + 1, numIterations, (time.time() - t0) / MINUTE,
        )
        for pos_X, pos_Yo, thickness, scan_title in ListOfSamples:
            # Apply the per-iteration Y drift to this sample's nominal Y position.
            pos_Y = pos_Yo + i * yOffset
            yield from collectAllThree(isDebugMode)

    elapsed_min = (time.time() - t0) / MINUTE
    logger.info("larryLoop finished | %d iterations | %.1f min total", numIterations, elapsed_min)
    appendToMdFile(
        f"larryLoop complete: {numIterations} iterations in {elapsed_min:.0f} min"
    )

    if not isDebugMode:
        yield from after_command_list()
    else:
        logger.info("[DEBUG] Skipping after_command_list()")


# ==============================================================================
# myFiniteLoop
# Single fixed position, time-based loop.
# Collects USAXS + SAXS only (WAXS intentionally disabled for this variant).
# Sample name encodes elapsed time in minutes.
# ==============================================================================
def myFiniteLoop(pos_X, pos_Y, thickness, scan_title, delay1minutes, md={}):
    """
    Collect USAXS + SAXS repeatedly at one fixed position for delay1minutes.

    WAXS is intentionally disabled in this plan variant.  To enable WAXS,
    uncomment the waxsExp lines inside collectAllThree.

    Sample name format:  {scan_title}_{elapsed_minutes:.0f}min

    Parameters
    ----------
    pos_X, pos_Y : float
        Sample stage X/Y position in mm.
    thickness : float
        Sample thickness in mm.
    scan_title : str
        Base name for all scans.
    delay1minutes : float
        Total run time in minutes.
    md : dict, optional
        Extra metadata.

    Reload:
        %run -im usaxs.user.finite_loop

    Run:
        RE(myFiniteLoop(0, 0, 1, "MySample", 20))
    """

    def setSampleName():
        """Return sample name encoding scan_title and elapsed minutes since t0."""
        return f"{scan_title}_{(time.time() - t0) / 60:.0f}min"

    def collectAllThree(debug=False):
        """
        Collect USAXS + SAXS for the fixed position (WAXS disabled).

        All scans in one call share the same sampleMod (name is not refreshed
        between USAXS and SAXS) because the elapsed-time resolution in the name
        format is one minute and back-to-back scans land in the same minute.

        Parameters
        ----------
        debug : bool
            True → print sample name and sleep (no instrument motion).
        """
        if debug:
            sampleMod = setSampleName()
            print(f"[DEBUG] collectAllThree: {sampleMod}")
            yield from bps.sleep(20)
        else:
            yield from sync_order_numbers()
            sampleMod = setSampleName()
            md["title"] = sampleMod
            yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
            # SAXS uses the same sampleMod — both scans share the same minute-level name.
            md["title"] = sampleMod
            yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
            # WAXS disabled for this plan variant. Uncomment to enable:
            # sampleMod = setSampleName()
            # md["title"] = sampleMod
            # yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    # --- Execution sequence ---
    isDebugMode = loop_debug.get()
    logger.info(
        "Starting myFiniteLoop | sample=%s | pos=(%.2f, %.2f) | duration=%s min | debug=%s",
        scan_title, pos_X, pos_Y, delay1minutes, isDebugMode,
    )

    if not isDebugMode:
        yield from before_command_list()
    else:
        logger.info("[DEBUG] Skipping before_command_list()")

    appendToMdFile(
        f"Starting myFiniteLoop: sample={scan_title}, "
        f"pos=({pos_X}, {pos_Y}), duration={delay1minutes} min"
    )

    t0 = time.time()
    checkpoint = time.time() + delay1minutes * MINUTE

    logger.info("Collecting USAXS+SAXS for %s minutes", delay1minutes)

    while time.time() < checkpoint:
        logger.debug(
            "myFiniteLoop: %.1f min remaining",
            (checkpoint - time.time()) / MINUTE,
        )
        yield from collectAllThree(isDebugMode)

    elapsed_min = (time.time() - t0) / MINUTE
    logger.info("myFiniteLoop finished | %.1f min elapsed", elapsed_min)
    appendToMdFile(f"myFiniteLoop complete: {scan_title}, {elapsed_min:.0f} min elapsed")

    if not isDebugMode:
        yield from after_command_list()
    else:
        logger.info("[DEBUG] Skipping after_command_list()")


# ==============================================================================
# myTwoPosFiniteLoop
# Alternates between two positions using the LAXm2 (SAMX) motor.
# Collects USAXS + SAXS only (WAXS intentionally disabled for this variant).
# The LAXm2 motor moves the stage; pos_X arguments are passed as metadata.
# ==============================================================================
def myTwoPosFiniteLoop(
    pos_XA, thicknessA, scan_titleA,
    pos_XB, thicknessB, scan_titleB,
    delay1minutes,
    md={},
):
    """
    Alternate between two stage positions (via LAXm2 motor) for delay1minutes.

    On each pass the plan moves LAXm2 to pos_XA, collects USAXS+SAXS for
    sample A, then moves to pos_XB and collects for sample B, repeating until
    the total time exceeds delay1minutes.

    DESIGN NOTE: The stage motion is performed by ``bps.mv(samx, pos_XA/B)``.
    The pos_X argument passed to USAXSscan/saxsExp is set to 0 (a metadata
    placeholder); the actual beam position is determined by the motor.
    WAXS is intentionally disabled in this plan variant.

    Parameters
    ----------
    pos_XA : float
        LAXm2 motor position (mm) for sample A.
    thicknessA : float
        Sample A thickness in mm.
    scan_titleA : str
        Base name for sample A scans.
    pos_XB : float
        LAXm2 motor position (mm) for sample B.
    thicknessB : float
        Sample B thickness in mm.
    scan_titleB : str
        Base name for sample B scans.
    delay1minutes : float
        Total run time in minutes.
    md : dict, optional
        Extra metadata.

    Reload:
        %run -im usaxs.user.finite_loop

    Run:
        RE(myTwoPosFiniteLoop(0, 1, "SampleA", 5, 2, "SampleB", 20))
    """
    from apsbits.core.instrument_init import oregistry
    # LAXm2 is the SAMX stage motor used to switch between the two positions.
    samx = oregistry["LAXm2"]

    def setSampleName():
        """Return sample name encoding scan_title and elapsed minutes since t0."""
        return f"{scan_title}_{(time.time() - t0) / 60:.0f}min"

    def collectAllThree(debug=False):
        """
        Collect USAXS + SAXS for the current (thickness, scan_title) values.

        thickness and scan_title are re-assigned in the main loop before each
        call to collectAllThree.  pos_X and pos_Y are fixed at 0 (metadata
        placeholders; stage is moved by the LAXm2 motor before this call).
        WAXS is disabled. Uncomment waxsExp lines to enable.

        Parameters
        ----------
        debug : bool
            True → print sample name and sleep (no instrument motion).
        """
        if debug:
            sampleMod = setSampleName()
            print(f"[DEBUG] collectAllThree: {sampleMod}  thickness={thickness}")
            yield from bps.sleep(20)
        else:
            yield from sync_order_numbers()
            sampleMod = setSampleName()
            md["title"] = sampleMod
            yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
            md["title"] = sampleMod
            yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
            # WAXS disabled for this plan variant. Uncomment to enable:
            # sampleMod = setSampleName()
            # md["title"] = sampleMod
            # yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    # --- Execution sequence ---
    isDebugMode = loop_debug.get()
    logger.info(
        "Starting myTwoPosFiniteLoop | A=%s@%.2fmm | B=%s@%.2fmm | duration=%s min | debug=%s",
        scan_titleA, pos_XA, scan_titleB, pos_XB, delay1minutes, isDebugMode,
    )

    if not isDebugMode:
        yield from before_command_list()
    else:
        logger.info("[DEBUG] Skipping before_command_list()")

    appendToMdFile(
        f"Starting myTwoPosFiniteLoop: "
        f"A={scan_titleA}@LAXm2={pos_XA} mm, "
        f"B={scan_titleB}@LAXm2={pos_XB} mm, "
        f"duration={delay1minutes} min"
    )

    t0 = time.time()
    checkpoint = time.time() + delay1minutes * MINUTE

    # pos_X and pos_Y are metadata placeholders; stage motion uses the samx motor.
    pos_X = 0
    pos_Y = 0

    logger.info("Alternating between two positions for %s minutes", delay1minutes)

    while time.time() < checkpoint:
        logger.debug(
            "myTwoPosFiniteLoop: %.1f min remaining",
            (checkpoint - time.time()) / MINUTE,
        )
        # Sample A
        thickness = thicknessA
        scan_title = scan_titleA
        yield from bps.mv(samx, pos_XA)
        yield from collectAllThree(isDebugMode)
        # Sample B
        thickness = thicknessB
        scan_title = scan_titleB
        yield from bps.mv(samx, pos_XB)
        yield from collectAllThree(isDebugMode)

    elapsed_min = (time.time() - t0) / MINUTE
    logger.info("myTwoPosFiniteLoop finished | %.1f min elapsed", elapsed_min)
    appendToMdFile(
        f"myTwoPosFiniteLoop complete: {scan_titleA}/{scan_titleB}, "
        f"{elapsed_min:.0f} min elapsed"
    )

    if not isDebugMode:
        yield from after_command_list()
    else:
        logger.info("[DEBUG] Skipping after_command_list()")


# ==============================================================================
# myFiniteMultiPosLoop
# Time-based loop over a hardcoded position list.
# Collects USAXS/SAXS/WAXS per position sequentially (standard order).
# Sample name encodes elapsed time.
# ==============================================================================
def myFiniteMultiPosLoop(delay1minutes, md={}):
    """
    Cycle through a position list collecting USAXS/SAXS/WAXS at each spot.

    Each loop iteration visits every position in ListOfSamples in order,
    collecting a full USAXS → SAXS → WAXS sequence at each before moving on.
    The outer loop repeats until delay1minutes has elapsed.

    Sample name format:  {scan_title}_{elapsed_minutes:.0f}min

    To use:
        1. Edit ListOfSamples inside this function to match your sample positions.
        2. Reload: %run -im usaxs.user.finite_loop
        3. Run:    RE(myFiniteMultiPosLoop(60))

    Parameters
    ----------
    delay1minutes : float
        Total run time in minutes.
    md : dict, optional
        Extra metadata.
    """

    # Edit this list to match your samples.
    # Format: [pos_X_mm, pos_Y_mm, thickness_mm, "SampleName"]
    ListOfSamples = [
        [ 15, 58, 4.0, "water_blank"],
        [ 25, 58, 4.0, "Z_15mgmL_DPEG_1p5mgmL_36hr"],
        [ 35, 58, 4.0, "Z_15mgmL_DPEG_3mgmL_36hr"],
        [ 45, 58, 4.0, "Z_15mgmL_DPEG_4p5mgmL_36hr"],
        [ 55, 58, 4.0, "Z_15mgmL_DPEG_6gmL_36hr"],
        [ 65, 58, 4.0, "Z_15mgmL_DPEG_6p75mgmL_36hr"],
        [ 75, 58, 4.0, "Z_15mgmL_DPEG_7p5mgmL_36hr"],
        [ 85, 58, 4.0, "Z_15mgmL_DPEG_3mgmL_47C_14hr"],
        [ 95, 58, 4.0, "Z_15mgmL_DPEG_4p5mgmL_47C_14hr"],
        [105, 58, 4.0, "Z_15mgmL_DPEG_6p75mgmL_47C_14hr"],
        [115, 58, 4.0, "Z_15mgmL_DPEG_50mgmL_14hr"],
    ]

    def setSampleName():
        """Return sample name encoding scan_title and elapsed minutes since t0."""
        return f"{scan_title}_{(time.time() - t0) / 60:.0f}min"

    def collectAllThree(debug=False):
        """
        Collect USAXS → SAXS → WAXS for the current (pos_X, pos_Y, thickness, scan_title).

        Called inside the inner for-loop so pos_X, pos_Y, thickness, and scan_title
        are all provided by the enclosing loop variable at call time.

        Parameters
        ----------
        debug : bool
            True → print sample name and sleep (no instrument motion).
        """
        if debug:
            sampleMod = setSampleName()
            print(f"[DEBUG] collectAllThree: {sampleMod}  pos=({pos_X}, {pos_Y})")
            yield from bps.sleep(20)
        else:
            yield from sync_order_numbers()
            sampleMod = setSampleName()
            md["title"] = sampleMod
            yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = setSampleName()
            md["title"] = sampleMod
            yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = setSampleName()
            md["title"] = sampleMod
            yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    # --- Execution sequence ---
    isDebugMode = loop_debug.get()
    logger.info(
        "Starting myFiniteMultiPosLoop | %d positions | duration=%s min | debug=%s",
        len(ListOfSamples), delay1minutes, isDebugMode,
    )

    if not isDebugMode:
        yield from before_command_list()
    else:
        logger.info("[DEBUG] Skipping before_command_list()")

    appendToMdFile(
        f"Starting myFiniteMultiPosLoop: "
        f"{len(ListOfSamples)} positions, duration={delay1minutes} min"
    )

    t0 = time.time()
    checkpoint = time.time() + delay1minutes * MINUTE

    logger.info("Cycling through %d positions for %s minutes", len(ListOfSamples), delay1minutes)

    while time.time() < checkpoint:
        logger.debug(
            "myFiniteMultiPosLoop: %.1f min remaining",
            (checkpoint - time.time()) / MINUTE,
        )
        for pos_X, pos_Y, thickness, scan_title in ListOfSamples:
            yield from collectAllThree(isDebugMode)

    elapsed_min = (time.time() - t0) / MINUTE
    logger.info("myFiniteMultiPosLoop finished | %.1f min elapsed", elapsed_min)
    appendToMdFile(
        f"myFiniteMultiPosLoop complete: {len(ListOfSamples)} positions, "
        f"{elapsed_min:.0f} min elapsed"
    )

    if not isDebugMode:
        yield from after_command_list()
    else:
        logger.info("[DEBUG] Skipping after_command_list()")


# ==============================================================================
# myFiniteListLoop
# Time-based loop over a hardcoded position list using GROUPED detector order.
# One iteration = all-USAXS → all-SAXS → all-WAXS for all positions.
# Sample name encodes a sequential integer counter (not elapsed time).
# This strategy minimises the time between USAXS and SAXS scans for each
# sample, which matters when comparing complementary q-ranges.
# ==============================================================================
def myFiniteListLoop(delay1minutes, StartTime, md={}):
    """
    Cycle through a position list with grouped detector order for delay1minutes.

    One complete iteration performs:
        - USAXSscan for every sample in ListOfSamples
        - saxsExp   for every sample in ListOfSamples
        - waxsExp   for every sample in ListOfSamples

    This is different from myFiniteMultiPosLoop where the order is
    USAXS→SAXS→WAXS per position.  The grouped order here is useful when
    minimising the total mechanical overhead of switching between USAXS and
    SAXS modes outweighs the benefit of grouping by position.

    Sample name format:  {scan_title}_{counter}
    where counter increments by 1 per complete iteration.

    Parameters
    ----------
    delay1minutes : float
        Total run time in minutes.
    StartTime : float
        Legacy parameter retained for backwards compatibility.
        Currently unused — sample names use an integer counter instead.
    md : dict, optional
        Extra metadata.

    To use:
        1. Edit ListOfSamples inside this function.
        2. Reload: %run -im usaxs.user.finite_loop  (or %run -im user.finite_loop)
        3. Run:    RE(myFiniteListLoop(20, 0))
    """

    # Edit this list to match your samples.
    # Format: [pos_X_mm, pos_Y_mm, thickness_mm, "SampleName"]
    ListOfSamples = [
        [100.0,  160.0, 1.000, "BlankLE"],
        [139.0,  100.6, 0.686, "RbCl6mLE"],
        [139.0,  160.3, 0.658, "NaCl6mLE"],
        [179.6,  100.6, 0.684, "BoehRbCl6mLE"],
        [178.8,  161.0, 0.654, "BoehNaCl6mLE"],
    ]

    def setSampleName(scan_titlePar):
        """
        Return sample name encoding the sample title and the current iteration counter.

        Using an integer counter (not elapsed time) gives cleaner filenames for
        grouped-detector collection where the meaning of "time" within one round
        is ambiguous.  The counter increments once per complete round.
        """
        return f"{scan_titlePar}_{counter}"

    def collectAllThree(debug=False):
        """
        One complete grouped-detector round: all USAXS, all SAXS, all WAXS.

        GROUPED ORDER: all samples at one detector before moving to the next.
        This differs from the per-position order used in myFiniteMultiPosLoop.

        Note: sync_order_numbers() is NOT called here because the three detector
        passes are separated in time and treated as independent scan groups.

        Parameters
        ----------
        debug : bool
            True → print sample names and positions for all samples, then sleep.
        """
        if debug:
            for pos_X, pos_Y, thickness, sampleName in ListOfSamples:
                sampleMod = setSampleName(sampleName)
                print(f"[DEBUG] USAXS: {sampleMod}  pos=({pos_X}, {pos_Y})  t={thickness}")
            yield from bps.sleep(1)
        else:
            # --- All USAXS ---
            for pos_X, pos_Y, thickness, sampleName in ListOfSamples:
                sampleMod = setSampleName(sampleName)
                md["title"] = sampleMod
                yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})

            # --- All SAXS ---
            for pos_X, pos_Y, thickness, sampleName in ListOfSamples:
                sampleMod = setSampleName(sampleName)
                md["title"] = sampleMod
                yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

            # --- All WAXS ---
            for pos_X, pos_Y, thickness, sampleName in ListOfSamples:
                sampleMod = setSampleName(sampleName)
                md["title"] = sampleMod
                yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    # --- Execution sequence ---
    isDebugMode = loop_debug.get()
    logger.info(
        "Starting myFiniteListLoop | %d positions | duration=%s min | debug=%s",
        len(ListOfSamples), delay1minutes, isDebugMode,
    )

    if not isDebugMode:
        yield from before_command_list()
    else:
        logger.info("[DEBUG] Skipping before_command_list()")

    appendToMdFile(
        f"Starting myFiniteListLoop (grouped detector order): "
        f"{len(ListOfSamples)} positions, duration={delay1minutes} min"
    )

    t0 = time.time()
    counter = 0
    checkpoint = time.time() + delay1minutes * MINUTE

    logger.info(
        "Grouped detector collection for %s minutes (%d samples per round)",
        delay1minutes, len(ListOfSamples),
    )

    while time.time() < checkpoint:
        logger.debug(
            "myFiniteListLoop: round %d, %.1f min remaining",
            counter, (checkpoint - time.time()) / MINUTE,
        )
        yield from collectAllThree(isDebugMode)
        counter += 1

    elapsed_min = (time.time() - t0) / MINUTE
    logger.info(
        "myFiniteListLoop finished | %d rounds | %.1f min elapsed", counter, elapsed_min
    )
    appendToMdFile(
        f"myFiniteListLoop complete: {counter} rounds, "
        f"{len(ListOfSamples)} positions, {elapsed_min:.0f} min elapsed"
    )

    if not isDebugMode:
        yield from after_command_list()
    else:
        logger.info("[DEBUG] Skipping after_command_list()")
