"""
Minimal USAXS/SAXS/WAXS plan template — the smallest complete, correct plan.

==============================================================================
PURPOSE
==============================================================================

This is the base skeleton every other template is built on.  Use it when the
experiment has no temperature controller, no external device, and no loop:
move to one position, collect one USAXS/SAXS/WAXS set, done.

It exists so an AI assistant (or a user) writing a new plan has one short,
complete, correct starting point that shows every mandatory element:

    1. module-level logger and debug Signal
    2. inner getSampleName() helper
    3. inner collectAllThree() helper with a debug branch
    4. recordFunctionRun()  — Obsidian record of the call and its arguments
    5. before_command_list() / after_command_list(), both gated on debug mode
    6. appendToMdFile() at start and end (never inside the collection loop)

Anything more complicated (a loop, a temperature ramp, a sample list, an
external device) starts from one of the other templates in this directory.

==============================================================================
USAGE
==============================================================================

Copy to a new file and edit:
    cp src/usaxs/plan_templates/minimal_plan_template.py \
       src/usaxs/user/my_experiment.py

Load:
    %run -im usaxs.user.my_experiment

Debug / dry-run (no instrument motion):
    plan_debug.put(True)
    RE(myMinimalPlan(0, 0, 1.0, "MySample"))

Real run:
    plan_debug.put(False)
    RE(myMinimalPlan(0, 0, 1.0, "MySample"))

==============================================================================
SAMPLE NAME FORMAT
==============================================================================

    {scan_title}_{elapsed_minutes:.0f}min

Drop the time suffix (return scan_title unchanged) for a true single-shot
measurement; keep it whenever the plan can collect more than one round.

CHANGE LOG:
    * JIL, 2026-09-09 : Initial minimal template
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
#   plan_debug.put(True)   → debug mode  (no instrument operations)
#   plan_debug.put(False)  → normal mode (default, real data collection)
# Read once at plan start into isDebugMode so behaviour is consistent.
plan_debug = Signal(name="plan_debug", value=False)


def myMinimalPlan(pos_X, pos_Y, thickness, scan_title, md={}):
    """
    Collect one USAXS → SAXS → WAXS set at a single sample position.

    Parameters
    ----------
    pos_X, pos_Y : float
        Sample stage X/Y position in mm.
    thickness : float
        Sample thickness in mm (used for transmission correction).
    scan_title : str
        Base name for the scans.  Elapsed time is appended.
    md : dict, optional
        Extra metadata.

    Load:
        %run -im usaxs.user.<new_filename>

    Run:
        RE(myMinimalPlan(0, 0, 1.0, "MySample"))
    """

    # ------------------------------------------------------------------
    # Inner helper functions
    # ------------------------------------------------------------------

    def getSampleName():
        """Return scan name encoding scan_title and elapsed minutes since t0."""
        return f"{scan_title}_{(time.time() - t0) / MINUTE:.0f}min"

    def collectAllThree(debug=False):
        """
        Collect USAXS → SAXS → WAXS at (pos_X, pos_Y).

        getSampleName() is called again before each detector so every file name
        reflects the conditions at the moment that scan starts (USAXS alone can
        take ~1.5 min).  sync_order_numbers() first, so the three scans share
        one scan-group number.

        To use fewer detectors, delete the blocks you do not need — and update
        the docstring and the appendToMdFile message below to match.

        Parameters
        ----------
        debug : bool
            True → print the sample name and sleep instead of moving the
            instrument.  Always pass isDebugMode; never hardcode.
        """
        sampleMod = getSampleName()
        if debug:
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

    isDebugMode = plan_debug.get()
    recordFunctionRun()
    logger.info(
        "Starting myMinimalPlan | sample=%s | pos=(%.2f, %.2f) | debug=%s",
        scan_title,
        pos_X,
        pos_Y,
        isDebugMode,
    )

    if not isDebugMode:
        yield from before_command_list()
    else:
        logger.info("[DEBUG] Skipping before_command_list()")

    appendToMdFile(
        f"Starting minimal plan: sample={scan_title}, "
        f"pos=({pos_X}, {pos_Y}), thickness={thickness} mm, USAXS+SAXS+WAXS"
    )

    t0 = time.time()
    yield from collectAllThree(isDebugMode)

    logger.info("myMinimalPlan finished for sample %s", scan_title)
    appendToMdFile(f"Minimal plan complete: {scan_title}")

    if not isDebugMode:
        yield from after_command_list()
    else:
        logger.info("[DEBUG] Skipping after_command_list()")
