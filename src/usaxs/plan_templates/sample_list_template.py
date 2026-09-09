"""
Sample-list batch template — measure a list of samples once, or N times.

==============================================================================
PURPOSE
==============================================================================

The most common ambient-temperature experiment: a holder carries several
samples (or one sample is measured at several spots), and each is measured
USAXS → SAXS → WAXS in turn.  Optionally the whole list is repeated a fixed
number of times.

Use this template when the experiment is defined by *how many samples* and
*how many repeats*.  Use ``finite_loop_template.py`` instead when it is
defined by *how long* (a time-based kinetics loop), and one of the
temperature templates when a controller is involved.

==============================================================================
USAGE
==============================================================================

Copy to a new file, edit SampleList, then:

Load:
    %run -im usaxs.user.<new_filename>

Debug / dry-run (no instrument motion):
    loop_debug.put(True)
    RE(measureSampleList())

Real run:
    loop_debug.put(False)
    RE(measureSampleList())            # one pass through SampleList
    RE(measureSampleList(numRepeats=5))  # five passes

Stop early:
    RE.abort()   (or Ctrl-C at the IPython prompt)
    NOTE: after_command_list() does NOT run on abort.  Once the plan has
    stopped, run teardown manually:  RE(after_command_list())

==============================================================================
SampleList FORMAT
==============================================================================

Defined at MODULE level (not inside the function) so it can be edited and the
file reloaded without rewriting the plan:

    SampleList = [
        [pos_X_mm, pos_Y_mm, thickness_mm, "SampleName"],
        ...
    ]

Thickness is per sample and is used for the transmission correction — set it
correctly for every entry, do not copy one value across different samples.

==============================================================================
SAMPLE NAME FORMAT
==============================================================================

    {sample_name}_{repeat_index}

Change getSampleName() to encode elapsed minutes instead if the repeats are
a time series rather than simple counting statistics.

CHANGE LOG:
    * JIL, 2026-09-09 : Initial sample-list batch template
"""

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

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

# Convenient time-unit constants.
SECOND = 1
MINUTE = 60 * SECOND
HOUR = 60 * MINUTE

# Debug / dry-run flag.  Set at the IPython prompt BEFORE calling RE():
#   loop_debug.put(True)   → debug mode  (no instrument operations)
#   loop_debug.put(False)  → normal mode (default)
loop_debug = Signal(name="loop_debug", value=False)

# ==============================================================================
# EDIT THIS LIST, then reload the file with %run -im ...
# Format: [pos_X_mm, pos_Y_mm, thickness_mm, "SampleName"]
# ==============================================================================
SampleList = [
    [0.0, 0.0, 1.0, "Blank"],
    [5.0, 0.0, 1.0, "Sample1"],
    [10.0, 0.0, 1.0, "Sample2"],
    # [15.0, 0.0, 1.0, "Sample3"],   # uncomment / add lines as needed
]


def measureSampleList(numRepeats=1, md={}):
    """
    Measure every entry in SampleList, USAXS → SAXS → WAXS, numRepeats times.

    Each pass visits the samples in list order and collects a complete
    USAXS/SAXS/WAXS sequence at each position before moving to the next.

    Parameters
    ----------
    numRepeats : int, optional
        Number of complete passes through SampleList.  Default 1.
    md : dict, optional
        Extra metadata.

    Load:
        %run -im usaxs.user.<new_filename>

    Run:
        RE(measureSampleList())
        RE(measureSampleList(numRepeats=5))
    """

    # ------------------------------------------------------------------
    # Inner helper functions
    # ------------------------------------------------------------------

    def getSampleName(sample_name, repeat):
        """
        Return scan name encoding the sample name and the repeat index.

        Format: {sample_name}_{repeat}

        For a time series, use elapsed minutes instead::

            return f"{sample_name}_{(time.time() - t0) / MINUTE:.0f}min"
        """
        return f"{sample_name}_{repeat}"

    def collectAllThree(pos_X, pos_Y, thickness, sample_name, repeat, debug=False):
        """
        Collect USAXS → SAXS → WAXS for one sample at (pos_X, pos_Y).

        The name is rebuilt before each detector so that, if getSampleName()
        is changed to encode time or temperature, every file records the value
        at its own acquisition time.  sync_order_numbers() first, so the three
        scans share one scan-group number.

        Parameters
        ----------
        pos_X, pos_Y : float
            Sample stage position in mm.
        thickness : float
            Sample thickness in mm.
        sample_name : str
            Base name from SampleList.
        repeat : int
            1-based index of the current pass through SampleList.
        debug : bool
            True → print and sleep instead of moving the instrument.
            Always pass isDebugMode; never hardcode.
        """
        sampleMod = getSampleName(sample_name, repeat)
        if debug:
            print(f"[DEBUG] collectAllThree: {sampleMod}  pos=({pos_X}, {pos_Y})")
            yield from bps.sleep(20)
        else:
            yield from sync_order_numbers()
            sampleMod = getSampleName(sample_name, repeat)
            md["title"] = sampleMod
            logger.info("USAXSscan: %s", sampleMod)
            yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = getSampleName(sample_name, repeat)
            md["title"] = sampleMod
            logger.info("saxsExp: %s", sampleMod)
            yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = getSampleName(sample_name, repeat)
            md["title"] = sampleMod
            logger.info("waxsExp: %s", sampleMod)
            yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    # ------------------------------------------------------------------
    # Execution sequence
    # ------------------------------------------------------------------

    isDebugMode = loop_debug.get()
    recordFunctionRun()
    logger.info(
        "Starting measureSampleList | %d samples | %d repeats | debug=%s",
        len(SampleList),
        numRepeats,
        isDebugMode,
    )

    if not isDebugMode:
        yield from before_command_list()
    else:
        logger.info("[DEBUG] Skipping before_command_list()")

    sample_lines = "\n".join(
        f"  - **{name}**: x={x} mm, y={y} mm, thickness={th} mm"
        for x, y, th, name in SampleList
    )
    appendToMdFile(
        f"## Sample list batch ({len(SampleList)} samples x {numRepeats} repeats)\n"
        f"- **Samples:**\n{sample_lines}\n"
        f"- **Detectors:** USAXS + SAXS + WAXS"
    )

    t0 = time.time()

    for repeat in range(1, numRepeats + 1):
        logger.info("Pass %d of %d", repeat, numRepeats)
        for pos_X, pos_Y, thickness, sample_name in SampleList:
            yield from collectAllThree(
                pos_X, pos_Y, thickness, sample_name, repeat, isDebugMode
            )

    elapsed_min = (time.time() - t0) / MINUTE
    logger.info(
        "measureSampleList finished | %d passes | %.1f min elapsed",
        numRepeats,
        elapsed_min,
    )
    appendToMdFile(
        f"Sample list batch complete: {numRepeats} passes, {elapsed_min:.0f} min"
    )

    if not isDebugMode:
        yield from after_command_list()
    else:
        logger.info("[DEBUG] Skipping after_command_list()")
