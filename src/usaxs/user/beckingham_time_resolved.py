"""
Beckingham time-resolved experiments — DATA-COLLECTION plan (inlet / mid / outlet).

==============================================================================
PURPOSE
==============================================================================

Plan 2 of 2 for the Beckingham time-resolved experiments (plan 1 is
``usaxs.user.beckingham_tune_blank``: optics re-tunes + capillary blank).

One capillary sample is measured at THREE positions along the capillary:

    inlet  ->  mid  ->  outlet        (repeated in a loop)

At each position a full USAXS -> SAXS -> WAXS set is collected.  The loop runs
for ``run_min`` minutes (different for every sample), counted from t = 0,
which is reset right after the usual startup (before_command_list()).

New coordinates are supplied for every sample, so positions are plan
arguments, not module constants.  Thickness is the same for all capillaries
(1.2 mm) and is a module constant.

==============================================================================
USAGE
==============================================================================

Load:
    %run -im usaxs.user.beckingham_time_resolved

Debug / dry run (no instrument operations; stage is NOT moved):
    tr_debug.put(True)
    RE(timeResolvedTube("Sr3p3Q0p5", 210,
                        inlet=(-49.7, 80), mid=(-49.8, 44), outlet=(-49.9, 9)))

Real run:
    tr_debug.put(False)
    RE(timeResolvedTube("Sr3p3Q0p5", 210,
                        inlet=(-49.7, 80), mid=(-49.8, 44), outlet=(-49.9, 9)))

Next sample: same call with the new name, run time and coordinates.

If aborted (RE.abort() / Ctrl-C), after_command_list() does NOT run.  Run it by
hand afterwards:   RE(after_command_list())

==============================================================================
SAMPLE NAME FORMAT
==============================================================================

    {sample}_{position}_{elapsed_minutes:.0f}min

    e.g.  Sr3p3Q0p5_inlet_0min, Sr3p3Q0p5_mid_4min, Sr3p3Q0p5_outlet_8min

The elapsed time is rebuilt before EACH detector (USAXS, SAXS, WAXS), so every
file records the time at which its own scan started.  Time is measured from
t0, set right after before_command_list().

Name length: the longest name is {sample}_outlet_{run_min}min.  Up to 35
characters are accepted for these experiments; a warning is printed above that.

COLLECTION ORDER / END OF RUN
    A round (inlet, mid, outlet) is always completed once started, so the three
    positions of the last round stay time-consistent.  The run therefore ends
    after the last round that was started before run_min (expected).

CHANGE LOG:
    * 2026-11-03 : Initial version for Beckingham experiments (NMR tube, 4 mm)
    * 2026-11-03 : Switched to capillary: thickness 1.2 mm
"""

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

import time

from apsbits.core.instrument_init import oregistry
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

s_stage = oregistry["s_stage"]

SECOND = 1
MINUTE = 60 * SECOND
HOUR = 60 * MINUTE

# Thickness of every capillary sample, mm (drives the transmission correction).
TUBE_THICKNESS = 1.2

# Maximum accepted length of a sample name (sample names become file names).
# Relaxed to 35 characters for these experiments (beamline norm: ~15, up to 25).
MAX_NAME_LENGTH = 35

# Debug / dry-run flag.  Set at the IPython prompt BEFORE calling RE():
#   tr_debug.put(True)   → no instrument operations, no stage motion
#   tr_debug.put(False)  → normal data collection (default)
tr_debug = Signal(name="tr_debug", value=False)


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


def timeResolvedTube(scan_title, run_min, inlet, mid, outlet, md=None):
    """
    Loop inlet -> mid -> outlet (USAXS+SAXS+WAXS each) for run_min minutes.

    Parameters
    ----------
    scan_title : str
        Sample name (letters, digits, "_" only; keep it short).
    run_min : float
        Total run time in minutes, counted from t = 0 (after startup).
        3.5 hours = 210.
    inlet, mid, outlet : (float, float)
        (sx, sy) in mm of the three positions on the tube.
    md : dict, optional
        Extra metadata.

    Load:
        %run -im usaxs.user.beckingham_time_resolved

    Run:
        RE(timeResolvedTube("Sr3p3Q0p5", 210,
                            inlet=(-49.7, 80), mid=(-49.8, 44), outlet=(-49.9, 9)))
    """
    if md is None:
        md = {}

    # Order matters: this is the collection order within a round.
    PositionList = [
        ("inlet", float(inlet[0]), float(inlet[1])),
        ("mid", float(mid[0]), float(mid[1])),
        ("outlet", float(outlet[0]), float(outlet[1])),
    ]

    # Validate everything BEFORE any instrument operation.
    if run_min <= 0:
        raise ValueError(f"run_min={run_min} must be > 0")
    for label, pos_X, pos_Y in PositionList:
        _check_stage_limits(pos_X, pos_Y, label)
    longest = len(f"{scan_title}_outlet_{run_min:.0f}min")
    if longest > MAX_NAME_LENGTH:
        logger.warning(
            "Longest sample name is %d characters (accepted max %d): consider "
            "a shorter sample name than '%s'",
            longest,
            MAX_NAME_LENGTH,
            scan_title,
        )
        print(
            f"WARNING: longest file name will be {longest} characters "
            f"(accepted max {MAX_NAME_LENGTH}); consider shortening '{scan_title}'"
        )

    # ------------------------------------------------------------------
    # Inner helper functions
    # ------------------------------------------------------------------

    def getSampleName(position):
        """Return {scan_title}_{position}_{elapsed_minutes}min (time from t0)."""
        return f"{scan_title}_{position}_{(time.time() - t0) / MINUTE:.0f}min"

    def collectAllThree(position, pos_X, pos_Y, debug=False):
        """
        Collect USAXS -> SAXS -> WAXS at one tube position.

        The name is rebuilt before each detector so each file records the
        elapsed time at the moment its own scan starts.
        """
        if debug:
            sampleMod = getSampleName(position)
            print(f"[DEBUG] collectAllThree: {sampleMod}  pos=({pos_X}, {pos_Y})")
            yield from bps.sleep(20)
        else:
            yield from sync_order_numbers()
            sampleMod = getSampleName(position)
            md["title"] = sampleMod
            logger.info("USAXSscan: %s", sampleMod)
            yield from USAXSscan(pos_X, pos_Y, TUBE_THICKNESS, sampleMod, md={})
            sampleMod = getSampleName(position)
            md["title"] = sampleMod
            logger.info("saxsExp: %s", sampleMod)
            yield from saxsExp(pos_X, pos_Y, TUBE_THICKNESS, sampleMod, md={})
            sampleMod = getSampleName(position)
            md["title"] = sampleMod
            logger.info("waxsExp: %s", sampleMod)
            yield from waxsExp(pos_X, pos_Y, TUBE_THICKNESS, sampleMod, md={})

    # ------------------------------------------------------------------
    # Execution sequence
    # ------------------------------------------------------------------

    isDebugMode = tr_debug.get()
    recordFunctionRun()
    logger.info(
        "Starting timeResolvedTube | sample=%s | run_min=%s | debug=%s | %s",
        scan_title,
        run_min,
        isDebugMode,
        PositionList,
    )

    if not isDebugMode:
        yield from before_command_list()
    else:
        logger.info("[DEBUG] Skipping before_command_list()")

    pos_text = "; ".join(f"{n}=({x}, {y})" for n, x, y in PositionList)
    appendToMdFile(
        f"Starting time-resolved tube: sample={scan_title}, {pos_text}, "
        f"thickness={TUBE_THICKNESS} mm, USAXS+SAXS+WAXS per position, "
        f"{run_min} min"
    )

    # t = 0 is set AFTER the usual startup plans.
    t0 = time.time()
    checkpoint = t0 + run_min * MINUTE
    round_count = 0

    # A started round is always completed (see module docstring).
    while time.time() < checkpoint:
        logger.debug(
            "Round %d: %.1f min remaining",
            round_count,
            (checkpoint - time.time()) / MINUTE,
        )
        for position, pos_X, pos_Y in PositionList:
            yield from collectAllThree(position, pos_X, pos_Y, isDebugMode)
        round_count += 1

    elapsed_min = (time.time() - t0) / MINUTE
    logger.info(
        "timeResolvedTube finished | %s | %d rounds | %.1f min elapsed",
        scan_title,
        round_count,
        elapsed_min,
    )
    appendToMdFile(
        f"Time-resolved tube complete: {scan_title}, {round_count} rounds "
        f"(inlet/mid/outlet), {elapsed_min:.0f} min elapsed"
    )

    if not isDebugMode:
        yield from after_command_list()
    else:
        logger.info("[DEBUG] Skipping after_command_list()")
