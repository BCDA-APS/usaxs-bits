"""
Beckingham time-resolved experiments — PRE-RUN plan: optics re-tune + blank.

==============================================================================
PURPOSE
==============================================================================

Plan 1 of 2 for the Beckingham time-resolved (1-6 h) experiments.

This plan is run right after the hutch search, so that the user's data
collection plan (plan 2, separate file) can start with minimal delay.  It does
two things, in this order:

    1. Re-tunes the USAXS optics (MR -> AR -> A2RP, i.e. tune_usaxs_optics)
       at least TWICE, with the sample stage parked at the tune position
       (SX = -20 mm, SY = 43 mm), so alignment to the APS beam is good for
       the whole long experiment.
    2. Measures the capillary blank (USAXS -> SAXS -> WAXS) at
       SX = 33.8 mm, SY = 43 mm, sample name "CapillaryBlank".

The blank is measured AFTER the tune, so it is taken under the same alignment
as the samples that follow.  Matilda uses the closest earlier file with
"blank" in its name as the instrumental background.

==============================================================================
USAGE
==============================================================================

Load:
    %run -im usaxs.user.beckingham_tune_blank

Debug / dry run (tunes and data collection are NOT executed):
    tune_blank_debug.put(True)
    RE(tuneAndBlank())

Real run:
    tune_blank_debug.put(False)
    RE(tuneAndBlank())

    RE(tuneAndBlank(numTunes=3))      # more than two tunes, if wanted

In debug mode the sample-stage moves (tune position, blank position) still run
for real, so the positions are exercised; the tunes, the before/after command
list and all data collection are skipped.

If aborted (RE.abort() / Ctrl-C), after_command_list() does NOT run.  Run it by
hand afterwards:   RE(after_command_list())

==============================================================================
SAMPLE NAME
==============================================================================

    CapillaryBlank      (single shot, no time suffix, same name for USAXS,
                         SAXS and WAXS; the instrument adds the order number)

CHANGE LOG:
    * 2026-11-03 : Initial version for Beckingham experiments (NMR tube blank)
    * 2026-11-03 : Switched to capillary: blank at SX=33.8, SY=43,
                   name "CapillaryBlank"
"""

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

from apsbits.core.instrument_init import oregistry
from bluesky import plan_stubs as bps
from ophyd import Signal

from usaxs.plans.axis_tuning import tune_usaxs_optics
from usaxs.plans.command_list import after_command_list
from usaxs.plans.command_list import before_command_list
from usaxs.plans.command_list import sync_order_numbers
from usaxs.plans.plans_usaxs import USAXSscan
from usaxs.plans.plans_user_facing import saxsExp
from usaxs.plans.plans_user_facing import waxsExp
from usaxs.utils.obsidian import appendToMdFile
from usaxs.utils.obsidian import recordFunctionRun

s_stage = oregistry["s_stage"]

# ----------------------------------------------------------------------------
# Experiment constants — edit here, then reload the file.
# ----------------------------------------------------------------------------
TUNE_SX = -20.0  # mm, sample stage X while tuning the optics
TUNE_SY = 43.0  # mm, sample stage Y while tuning the optics

BLANK_SX = 33.8  # mm, capillary blank position X
BLANK_SY = 43.0  # mm, capillary blank position Y
BLANK_THICKNESS = 0.0  # mm, blank thickness (customary 0 for a blank) -- CONFIRM
BLANK_NAME = "CapillaryBlank"

MIN_TUNES = 2  # the experiment requires at least two optics tunes

# Debug / dry-run flag.  Set at the IPython prompt BEFORE calling RE():
#   tune_blank_debug.put(True)   → tunes and data collection are skipped
#   tune_blank_debug.put(False)  → normal operation (default)
tune_blank_debug = Signal(name="tune_blank_debug", value=False)


def _check_stage_limits(sx, sy, label):
    """Raise ValueError if (sx, sy) is outside the sample-stage travel."""
    problems = []
    if not s_stage.x.low_limit <= sx <= s_stage.x.high_limit:
        problems.append(
            f"SX={sx} outside [{s_stage.x.low_limit:.2f}, {s_stage.x.high_limit:.2f}]"
        )
    if not s_stage.y.low_limit <= sy <= s_stage.y.high_limit:
        problems.append(
            f"SY={sy} outside [{s_stage.y.low_limit:.2f}, {s_stage.y.high_limit:.2f}]"
        )
    if problems:
        raise ValueError(f"{label} position out of range: " + "; ".join(problems))


def tuneAndBlank(numTunes=MIN_TUNES, md=None):
    """
    Re-tune the USAXS optics at the tune position, then measure the capillary blank.

    Sequence
    --------
    1. Check both positions against the sample-stage limits (before any motion).
    2. before_command_list()                                  [skipped in debug]
    3. Move sample stage to the tune position (TUNE_SX, TUNE_SY).
    4. tune_usaxs_optics() numTunes times (MR -> AR -> A2RP each)
                                                              [skipped in debug]
    5. Measure the blank: USAXS -> SAXS -> WAXS at (BLANK_SX, BLANK_SY),
       name "CapillaryBlank".                                 [skipped in debug]
    6. after_command_list()                                   [skipped in debug]

    Parameters
    ----------
    numTunes : int
        Number of times tune_usaxs_optics() is run.  Must be >= 2.
    md : dict, optional
        Extra metadata.

    Load:
        %run -im usaxs.user.beckingham_tune_blank

    Run:
        RE(tuneAndBlank())
    """
    if numTunes < MIN_TUNES:
        raise ValueError(
            f"numTunes={numTunes}: this experiment needs at least {MIN_TUNES} tunes"
        )
    _check_stage_limits(TUNE_SX, TUNE_SY, "tune")
    _check_stage_limits(BLANK_SX, BLANK_SY, "blank")

    if md is None:
        md = {}

    def collectBlank(debug=False):
        """Collect USAXS -> SAXS -> WAXS of the blank at the blank position."""
        if debug:
            print(f"[DEBUG] collectBlank: {BLANK_NAME}  pos=({BLANK_SX}, {BLANK_SY})")
            yield from bps.sleep(20)
        else:
            yield from sync_order_numbers()
            md["title"] = BLANK_NAME
            logger.info("USAXSscan: %s", BLANK_NAME)
            yield from USAXSscan(BLANK_SX, BLANK_SY, BLANK_THICKNESS, BLANK_NAME, md={})
            logger.info("saxsExp: %s", BLANK_NAME)
            yield from saxsExp(BLANK_SX, BLANK_SY, BLANK_THICKNESS, BLANK_NAME, md={})
            logger.info("waxsExp: %s", BLANK_NAME)
            yield from waxsExp(BLANK_SX, BLANK_SY, BLANK_THICKNESS, BLANK_NAME, md={})

    # ------------------------------------------------------------------
    # Execution sequence
    # ------------------------------------------------------------------
    isDebugMode = tune_blank_debug.get()
    recordFunctionRun()
    logger.info(
        "Starting tuneAndBlank | numTunes=%d | tune=(%.2f, %.2f) | "
        "blank=(%.2f, %.2f) | debug=%s",
        numTunes,
        TUNE_SX,
        TUNE_SY,
        BLANK_SX,
        BLANK_SY,
        isDebugMode,
    )

    if not isDebugMode:
        yield from before_command_list()
    else:
        logger.info("[DEBUG] Skipping before_command_list()")

    appendToMdFile(
        f"Starting pre-run: {numTunes}x tune_usaxs_optics at "
        f"SX={TUNE_SX}, SY={TUNE_SY}; then USAXS+SAXS+WAXS blank "
        f"'{BLANK_NAME}' at SX={BLANK_SX}, SY={BLANK_SY}"
    )

    # --- optics tunes at the tune position -------------------------------
    yield from bps.mv(s_stage.x, TUNE_SX, s_stage.y, TUNE_SY)
    for i in range(1, numTunes + 1):
        if isDebugMode:
            print(f"[DEBUG] tune_usaxs_optics {i}/{numTunes} skipped")
            yield from bps.sleep(5)
        else:
            logger.info("tune_usaxs_optics %d of %d", i, numTunes)
            yield from tune_usaxs_optics(md={})

    # --- blank -----------------------------------------------------------
    # USAXSscan/saxsExp/waxsExp move the sample stage themselves; this move
    # just parks the stage at the blank before the first scan starts.
    yield from bps.mv(s_stage.x, BLANK_SX, s_stage.y, BLANK_SY)
    yield from collectBlank(isDebugMode)

    logger.info("tuneAndBlank finished")
    appendToMdFile(
        f"Pre-run complete: {numTunes} optics tunes done, blank '{BLANK_NAME}' "
        "collected (USAXS+SAXS+WAXS)"
    )

    if not isDebugMode:
        yield from after_command_list()
    else:
        logger.info("[DEBUG] Skipping after_command_list()")
