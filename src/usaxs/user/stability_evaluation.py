"""
Instrument/beamline stability evaluation — infinite grouped-detector loop.

Two samples are each probed on a 3x3 grid (+/-1 mm in X and Y around their
nominal position), giving 18 measurement points total.  Every round collects
USAXS at all 18 points, then SAXS at all 18 points, then WAXS at all 18
points, then sleeps for a fixed interval before repeating.  This runs forever
until the user stops it -- intended as an overnight/long-duration stability
check of the instrument and beamline.

Samples (nominal / center positions):
    AirBlank     : x=100, y=20, thickness=1 mm
    GC_SRM3600   : x=100, y=40, thickness=1 mm

Grid: dx, dy in {-1, 0, +1} mm -> 9 points per sample -> 18 points total.

Round order:  all-USAXS -> all-SAXS -> all-WAXS -> sleep(sleep_min) -> repeat.

==============================================================================
USAGE
==============================================================================

Load:
    %run -im usaxs.user.stability_evaluation

Debug / dry-run (no instrument motion; loop runs a couple of rounds quickly
with short sleeps so you can confirm the point list, order, and naming):
    stability_debug.put(True)
    RE(stabilityEvaluation())
    # let it print 1-2 rounds, then Ctrl-C or RE.abort() to stop the test

Real run (runs forever, 30 min sleep between rounds by default):
    stability_debug.put(False)
    RE(stabilityEvaluation())
    RE(stabilityEvaluation(sleep_min=15))   # shorter gap between rounds

==============================================================================
STOPPING IT
==============================================================================

This plan is intentionally infinite -- it does not stop on its own.  To stop:

    RE.abort()          # or Ctrl-C at the IPython prompt

IMPORTANT: RE.abort() / Ctrl-C do NOT run after_command_list().  Once RE has
stopped, restore the instrument to its normal (safe) state by hand:

    RE(after_command_list())

CHANGE LOG:
    * Aida, initial version for overnight stability evaluation (2 samples,
      3x3 grid each, grouped-detector order, infinite loop with 30 min sleep).
"""

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

import time

from bluesky import plan_stubs as bps
from ophyd import Signal

from usaxs.plans.command_list import after_command_list
from usaxs.plans.command_list import before_command_list
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
#   stability_debug.put(True)   -> debug mode  (no instrument operations)
#   stability_debug.put(False)  -> normal mode (default)
stability_debug = Signal(name="stability_debug", value=False)

# ==============================================================================
# Nominal ("home") sample positions.
# Format: [pos_X_mm, pos_Y_mm, thickness_mm, "SampleName"]
# ==============================================================================
BaseSamples = [
    [100, 20, 1, "AirBlank"],
    [100, 40, 1, "GC_SRM3600"],
]

# Grid offsets applied around each base position: +/-1 mm in X and Y (3x3 = 9 pts).
GridOffsets = [-1, 0, 1]


def buildSampleList():
    """
    Expand BaseSamples into the full 3x3 grid (9 points) per sample.

    Returns a flat list in the same [pos_X, pos_Y, thickness, name] format
    used everywhere else, so it can be consumed directly by collectRound().
    """
    samples = []
    for base_x, base_y, thickness, name in BaseSamples:
        for dx in GridOffsets:
            for dy in GridOffsets:
                pos_X = base_x + dx
                pos_Y = base_y + dy
                pt_name = f"{name}_x{dx:+.0f}_y{dy:+.0f}"
                samples.append([pos_X, pos_Y, thickness, pt_name])
    return samples


# 18 points total: 9 grid points x 2 samples.  Rebuilt at import time from
# BaseSamples/GridOffsets above -- edit those, not this list, then reload.
SampleList = buildSampleList()


def stabilityEvaluation(sleep_min=30, md={}):
    """
    Infinite grouped-detector stability loop over an 18-point sample grid.

    Two samples (AirBlank, GC_SRM3600), each sampled on a 3x3 grid spanning
    +/-1 mm in X and Y around its nominal position (18 points total).  Each
    round collects, in this order:
        1. USAXSscan at all 18 grid points
        2. saxsExp   at all 18 grid points
        3. waxsExp   at all 18 grid points
        4. sleep sleep_min minutes
    then repeats forever.

    sync_order_numbers() is deliberately NOT used here: USAXS/SAXS/WAXS for a
    given point are collected many minutes apart (grouped by detector, not by
    point), so they are not a single scan-group in the usual sense.

    Parameters
    ----------
    sleep_min : float, optional
        Minutes to sleep between rounds.  Default 30.
    md : dict, optional
        Extra metadata.

    Load:
        %run -im usaxs.user.stability_evaluation

    Debug mode (short sleeps, no instrument motion):
        stability_debug.put(True)
        RE(stabilityEvaluation())

    Real run:
        stability_debug.put(False)
        RE(stabilityEvaluation())            # sleep_min=30 default
        RE(stabilityEvaluation(sleep_min=15))

    Stop:
        RE.abort()   (or Ctrl-C at the IPython prompt)
        NOTE: after_command_list() does NOT run automatically after an abort.
        Once RE has stopped, restore the instrument by hand:
            RE(after_command_list())
    """

    # ------------------------------------------------------------------
    # Inner helper functions
    # ------------------------------------------------------------------

    def getSampleName(sample_name, round_counter):
        """Return scan name encoding the grid-point name and round number."""
        return f"{sample_name}_r{round_counter}"

    def collectRound(round_counter, debug=False):
        """
        One complete grouped-detector round over all 18 grid points.

        Order: all-USAXS, then all-SAXS, then all-WAXS.

        Parameters
        ----------
        round_counter : int
            1-based round index, encoded into every sample name.
        debug : bool
            True -> print names/positions and sleep briefly instead of
            collecting data.  Pass isDebugMode -- never hardcode.
        """
        if debug:
            for pos_X, pos_Y, thickness, sample_name in SampleList:
                sampleMod = getSampleName(sample_name, round_counter)
                print(
                    f"[DEBUG] round {round_counter} | USAXS/SAXS/WAXS: "
                    f"{sampleMod}  pos=({pos_X}, {pos_Y})  thickness={thickness}"
                )
            yield from bps.sleep(1)
        else:
            # --- All USAXS, all 18 points ---
            for pos_X, pos_Y, thickness, sample_name in SampleList:
                sampleMod = getSampleName(sample_name, round_counter)
                md["title"] = sampleMod
                logger.info("USAXSscan [round %d]: %s", round_counter, sampleMod)
                yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})

            # --- All SAXS, all 18 points ---
            for pos_X, pos_Y, thickness, sample_name in SampleList:
                sampleMod = getSampleName(sample_name, round_counter)
                md["title"] = sampleMod
                logger.info("saxsExp [round %d]: %s", round_counter, sampleMod)
                yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

            # --- All WAXS, all 18 points ---
            for pos_X, pos_Y, thickness, sample_name in SampleList:
                sampleMod = getSampleName(sample_name, round_counter)
                md["title"] = sampleMod
                logger.info("waxsExp [round %d]: %s", round_counter, sampleMod)
                yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    # ------------------------------------------------------------------
    # Execution sequence
    # ------------------------------------------------------------------

    isDebugMode = stability_debug.get()
    recordFunctionRun()
    logger.info(
        "Starting stabilityEvaluation | %d grid points (%d samples x 9) | "
        "sleep=%s min | debug=%s",
        len(SampleList),
        len(BaseSamples),
        sleep_min,
        isDebugMode,
    )

    if not isDebugMode:
        yield from before_command_list()
    else:
        logger.info("[DEBUG] Skipping before_command_list()")

    base_summary = ", ".join(
        f"{n} (x={x}, y={y}, t={t} mm)" for x, y, t, n in BaseSamples
    )
    appendToMdFile(
        f"## Stability evaluation started\n"
        f"- **Base samples:** {base_summary}\n"
        f"- **Grid:** +/-1 mm in X and Y (3x3 = 9 points) around each base "
        f"position -> {len(SampleList)} points total\n"
        f"- **Order per round:** all-USAXS -> all-SAXS -> all-WAXS\n"
        f"- **Sleep between rounds:** {sleep_min} min\n"
        f"- **Runs until stopped** (RE.abort() / Ctrl-C), "
        f"then run RE(after_command_list()) by hand"
    )

    t0 = time.time()
    round_counter = 0

    logger.info(
        "Entering infinite stability loop -- stop with RE.abort() / Ctrl-C"
    )

    while True:
        round_counter += 1
        logger.info(
            "=== Round %d starting (%.1f min elapsed) ===",
            round_counter,
            (time.time() - t0) / MINUTE,
        )
        yield from collectRound(round_counter, isDebugMode)

        if isDebugMode:
            logger.info(
                "[DEBUG] Round %d complete, short sleep instead of %s min",
                round_counter,
                sleep_min,
            )
            yield from bps.sleep(5)
        else:
            logger.info(
                "Round %d complete, sleeping %s min before next round",
                round_counter,
                sleep_min,
            )
            yield from bps.sleep(sleep_min * MINUTE)

    # NOTE: this loop is infinite by design and is expected to be stopped via
    # RE.abort() / Ctrl-C, which does not reach the code below.  There is
    # deliberately no try/finally here -- see the module docstring and the
    # "Stopping it" section above for the manual teardown step
    # (RE(after_command_list())) to run once the plan has actually stopped.
