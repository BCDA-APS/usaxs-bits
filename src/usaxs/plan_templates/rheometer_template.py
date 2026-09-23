"""
AI-assisted rheometer experiment plan template for USAXS/SAXS/WAXS data collection.

==============================================================================
PURPOSE AND USAGE FOR AI PLAN DEVELOPMENT
==============================================================================

This file is the recommended starting point when an AI assistant (e.g. Claude)
is asked to write a custom rheometer experiment plan for a user.

Unlike the Linkam/PTC10 templates, the rheometer is not a networked
controller: USAXS positions its own sample stage and fires a single TTL
trigger pulse; all rheological control (shear rate, oscillation, etc.) is
driven independently by the Anton Paar RheoCompass software on its own PC.
The trigger pulse is the only synchronisation point between the two systems.

Workflow for AI-assisted plan creation:
    1. User describes their experiment: where to move the rheometer stage for
       each sample/position, how many datasets to collect before triggering
       RheoCompass (baseline), and how many to collect after (response).
    2. AI copies myRheometerPlan_template to a new function with a
       descriptive name.
    3. AI fills in RheometerPositions (or the function parameters for a
       single position), adjusts numCollections_before/after, and updates
       the docstring.
    4. The new file is loaded with:
           %run -im usaxs.user.<new_filename>
    5. Tested in debug mode first:
           rheometer_debug.put(True)
           RE(myNewPlan(...))
    6. Real run after validation:
           rheometer_debug.put(False)
           RE(myNewPlan(...))

==============================================================================
DEBUG MODE — CRITICAL FOR SAFE TESTING
==============================================================================

``rheometer_debug`` is an ophyd Signal (persistent in the IPython session).
Set it BEFORE calling RE():

    rheometer_debug.put(True)   # enable debug mode
    rheometer_debug.put(False)  # restore normal operation

When isDebugMode is True:
    - before_command_list() is SKIPPED  → no instrument initialisation
    - after_command_list() is SKIPPED   → no instrument teardown
    - collectAllThree() prints the sample name and sleeps 20 s instead of
      moving the instrument
    - the rheometer stage move and the RheoCompass trigger pulse run
      NORMALLY — positioning and synchronisation timing are exercised for
      real even in debug mode, since they carry no beam-time cost

The instrument-triggering calls that MUST be gated on isDebugMode are:
    1. before_command_list()        — instrument startup
    2. collectAllThree()            — data acquisition
    3. after_command_list()         — instrument teardown

==============================================================================
INSTRUMENT OPERATIONS OVERVIEW
==============================================================================

before_command_list():
    Standard pre-scan startup: checks beam/shutter status, opens the
    Obsidian notebook entry for this measurement session, sets up scan
    metadata.  SKIP IN DEBUG MODE.

after_command_list():
    Standard post-scan teardown: closes shutters, returns instrument to a
    safe state, writes "session ended" to Obsidian.  SKIP IN DEBUG MODE.

sync_order_numbers():
    Synchronises USAXS / SAXS / WAXS scan counter values so the detectors
    within one collectAllThree() call share a common scan-group ID.  Call
    once at the START of each collectAllThree() (not inside the debug
    branch).

appendToMdFile(message):
    Appends a human-readable line to the Obsidian notebook.  Use SPARINGLY —
    write only at meaningful transitions (plan start, each position move,
    trigger events, plan end).  Do NOT call in tight loops.

recordFunctionRun():
    Records that a named function was executed.  Optional, used for audit trail.

==============================================================================
RHEOMETER STAGE INTERFACE
==============================================================================

``rheometer_stage`` (usaxs.devices.rheometer.RheometerStageDevice, registered
in devices.yml) has four independent EPICS motors:

    rheometer_stage.x     : horizontal translation (mm)
    rheometer_stage.leg1  : vertical leveling motor (triangle leg 1)
    rheometer_stage.leg2  : vertical leveling motor (triangle leg 2)
    rheometer_stage.leg3  : vertical leveling motor (triangle leg 3)

leg1/leg2/leg3 have no shared setpoint or interlock — they are NOT
guaranteed to start at equal positions.  Level the stage by driving all
three to the SAME absolute target in a single concurrent move (see
moveRheometerStage() below), never one at a time and never by a relative
offset.

IMPORTANT — USAXSscan/saxsExp/waxsExp position the *main* sample stage
(s_stage), which is a different physical stage from the rheometer.  For
rheometer experiments, s_stage must stay parked at (0, 0) (verify this is
the correct beam-path position for the rheometer setup before running) and
all real sample positioning is done through rheometer_stage instead.  This
is why every detector call below passes pos_X=0, pos_Y=0.

==============================================================================
RHEOCOMPASS TRIGGER (SYNCHRONISATION SIGNAL)
==============================================================================

``galil_voltage`` is a Galil analogue output (usxRIO:GalilAo1_SP) wired into
RheoCompass as a TTL-level start trigger.  Normally at 0 V; USAXS raises it
to 5 V for about 1 second, then drops it back to 0 V, to tell RheoCompass
"start now".  Use triggerRheoCompass() below rather than driving
galil_voltage directly, so the pulse width stays consistent across plans.

Do not shorten the 1 s hold — it is set to comfortably exceed RheoCompass's
input debounce/scan time on the Anton Paar side.

==============================================================================
SAMPLE NAMING CONVENTION
==============================================================================

Format:  {scan_title}_sx{x:.2f}_sy{leg:.2f}_{phase}{index}_{elapsed_minutes:.0f}min

    sx, sy   : rheometer_stage.x and the common leg target, in mm — NOT the
               (always-zero) s_stage position passed to the detector calls.
               Keeping sx/sy in the name preserves the usual USAXS naming
               convention and records where the sample actually was.
    phase    : "pre"  — collected before the RheoCompass trigger (baseline)
               "post" — collected after the RheoCompass trigger (response)
    index    : 1-based collection number within that phase
    elapsed_minutes : minutes since the phase started (t0 reset at trigger)

Examples:
    "Shear1_sx12.50_sy3.00_pre1_0min"
    "Shear1_sx12.50_sy3.00_post3_4min"

Rules:
    - Call setSampleName() immediately before EVERY scan call.
    - Reset t0 = time.time() at the start of each phase (baseline start,
      and again right after the trigger pulse) so "elapsed" means "time
      into this phase", not total plan run time.

==============================================================================
DATA COLLECTION STRATEGY GUIDE (for AI plan writing)
==============================================================================

numCollections_before (baseline, pre-trigger):
    Use 1–3 to confirm the sample is aligned and quiescent before RheoCompass
    starts its program.  Use 0 to skip baseline entirely if not needed.

numCollections_after (response, post-trigger):
    Set according to how long RheoCompass's own program runs and how many
    time points are wanted.  Each USAXS+SAXS pair takes roughly 2–3 minutes;
    size numCollections_after so the plan does not run long past the
    RheoCompass program's completion.

MULTIPLE POSITIONS AT ONE CONDITION:
    When the user wants several spots measured under the same RheoCompass
    condition (e.g. several locations on one sample after one shear step),
    loop the position-move + collect block over a RheometerPositions list
    instead of hardcoding a single (x, leg) pair — see the commented
    multi-position skeleton at the end of this file.

==============================================================================
OBSIDIAN NOTEBOOK LOGGING GUIDE
==============================================================================

appendToMdFile() writes to the user's Obsidian notebook.  Write at:
    - Plan start (sample ID, target position, collection counts)
    - Each rheometer stage move
    - The RheoCompass trigger event
    - Plan end (brief summary)

Do NOT call inside the collection loops — that would flood the notebook.

==============================================================================
CUSTOMISATION CHECKLIST FOR AI
==============================================================================

When creating a new plan from this template:
    [ ] Rename the function (replace myRheometerPlan_template)
    [ ] Update the module-level docstring and function docstring
    [ ] Set thickness correctly for the sample being measured
    [ ] Choose numCollections_before / numCollections_after
    [ ] If multiple positions are needed, expand to a RheometerPositions
        list (see the commented skeleton at the end of this file)
    [ ] Confirm s_stage really should stay at (0, 0) for this setup
    [ ] Confirm debug-mode guards are in place for all instrument calls

CHANGE LOG:
    * JIL, 2026-09-15 : Initial AI-development template
"""

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

import time

from apsbits.core.instrument_init import oregistry
from bluesky import plan_stubs as bps
from ophyd import EpicsSignal
from ophyd import Signal

from usaxs.plans.command_list import after_command_list
from usaxs.plans.command_list import before_command_list
from usaxs.plans.command_list import sync_order_numbers
from usaxs.plans.plans_usaxs import USAXSscan
from usaxs.plans.plans_user_facing import saxsExp
from usaxs.plans.plans_user_facing import waxsExp
from usaxs.utils.obsidian import appendToMdFile
from usaxs.utils.obsidian import recordFunctionRun

# Rheometer sample stage: x (horizontal) + leg1/leg2/leg3 (vertical leveling).
rheometer_stage = oregistry["rheometer_stage"]

# Galil analogue output wired into RheoCompass as a TTL start trigger.
# Normally 0 V; pulsed to 5 V for ~1 s to tell RheoCompass "start now".
galil_voltage = EpicsSignal("usxRIO:GalilAo1_SP.VAL", name="galil_voltage")

# Convenient time-unit constants — use these in delay expressions.
SECOND = 1
MINUTE = 60 * SECOND
HOUR = 60 * MINUTE

# Debug / dry-run flag.  Read once at plan start as isDebugMode.
# At the IPython prompt:
#   rheometer_debug.put(True)   → debug mode on  (no instrument operations)
#   rheometer_debug.put(False)  → normal mode on (real data collection)
rheometer_debug = Signal(name="rheometer_debug", value=False)


# ==============================================================================
# DO NOT MODIFY THIS TEMPLATE FUNCTION.
# Copy it to a new file and rename it for your experiment.
# ==============================================================================
def myRheometerPlan_template(
    rheo_x,
    rheo_leg,
    thickness,
    scan_title,
    numCollections_before,
    numCollections_after,
    md={},
):
    """
    Move the rheometer into position, collect a baseline, trigger RheoCompass,
    then collect the response.

    Sequence:
        1. Move rheometer_stage to (rheo_x, rheo_leg): x moves independently,
           leg1/leg2/leg3 move concurrently to the same absolute rheo_leg
           value (see moveRheometerStage).
        2. Collect numCollections_before USAXS/SAXS datasets ("pre" phase) —
           confirms alignment before RheoCompass starts its own program.
        3. Pulse galil_voltage 5 V -> 0 V (see triggerRheoCompass) to start
           RheoCompass.
        4. Collect numCollections_after USAXS/SAXS datasets ("post" phase) —
           the time-resolved response while RheoCompass runs its program.

    Parameters
    ----------
    rheo_x : float
        rheometer_stage.x target position in mm.
    rheo_leg : float
        Common absolute target for leg1/leg2/leg3, in mm.  Determine this
        value separately (e.g. from a prior leveling pass) — it is not
        computed here.
    thickness : float
        Sample thickness in mm (used for transmission correction).
    scan_title : str
        Base name for all scans.  Position and phase/index are appended
        automatically (see module docstring, SAMPLE NAMING CONVENTION).
    numCollections_before : int
        Number of USAXS+SAXS datasets to collect before the trigger pulse.
        Use 0 to skip the baseline entirely.
    numCollections_after : int
        Number of USAXS+SAXS datasets to collect after the trigger pulse.
    md : dict, optional
        Extra metadata passed into scan functions.

    Load with:
        %run -im usaxs.plan_templates.rheometer_template

    Enable debug mode (no instrument operations):
        rheometer_debug.put(True)

    Run:
        RE(myRheometerPlan_template(12.5, 3.0, 1.0, "Shear1", 2, 10))
    """

    # =========================================================================
    # INNER HELPER FUNCTIONS
    # Copy these verbatim to any new plan function derived from this template.
    # =========================================================================

    def setSampleName(phase, index):
        """
        Return a sample name encoding scan_title, rheometer position, the
        pre/post-trigger phase, its 1-based index, and elapsed time.

        Format: {scan_title}_sx{x:.2f}_sy{leg:.2f}_{phase}{index}_{min}min

        sx/sy record the ACTUAL rheometer position, not the s_stage position
        passed to the detector calls (which is fixed at 0, 0 — see module
        docstring).  Call this immediately before every scan.
        """
        return (
            f"{scan_title}"
            f"_sx{rheo_x:.2f}_sy{rheo_leg:.2f}"
            f"_{phase}{index}"
            f"_{(time.time() - t0) / MINUTE:.0f}min"
        )

    def moveRheometerStage(x, leg_target):
        """
        Move rheometer_stage.x and all three legs concurrently.

        leg1/leg2/leg3 are independent motors with no shared setpoint, so
        they are not guaranteed to start at equal positions.  Passing all
        four moves to a single bps.mv() call moves them concurrently and
        waits for all to finish — this is what actually keeps the stage
        level, rather than moving the legs one at a time or by an offset.
        """
        yield from bps.mv(
            rheometer_stage.x,
            x,
            rheometer_stage.leg1,
            leg_target,
            rheometer_stage.leg2,
            leg_target,
            rheometer_stage.leg3,
            leg_target,
        )

    def triggerRheoCompass():
        """
        Pulse galil_voltage 5 V -> 0 V to signal RheoCompass to start.

        Holds 5 V for 1 s, comfortably longer than RheoCompass's input
        debounce/scan time.  Does not wait for anything on the RheoCompass
        side — the caller decides how long to keep collecting afterward.
        """
        logger.info("Triggering RheoCompass (galil_voltage 5V pulse)")
        yield from bps.mv(galil_voltage, 5)
        yield from bps.sleep(1)
        yield from bps.mv(galil_voltage, 0)

    def collectAllThree(phase, index, debug=False):
        """
        Collect one USAXS + SAXS dataset at the fixed s_stage position (0, 0).

        WAXS is disabled by default for rheometer time series (kinetics
        favour USAXS+SAXS cadence over completeness) — uncomment the waxsExp
        block below to re-enable.

        Parameters
        ----------
        phase : str
            "pre" or "post" — see setSampleName().
        index : int
            1-based collection index within the phase.
        debug : bool
            When True, prints the sample name and sleeps 20 s (no
            instrument motion).  Pass isDebugMode here — NEVER hardcode.
        """
        sampleMod = setSampleName(phase, index)
        logger.debug("collectAllThree: sample name = %s", sampleMod)
        if debug:
            print(f"[DEBUG] collectAllThree: {sampleMod}")
            yield from bps.sleep(20)
        else:
            yield from sync_order_numbers()
            sampleMod = setSampleName(phase, index)
            md["title"] = sampleMod
            logger.info("Starting USAXSscan: %s", sampleMod)
            yield from USAXSscan(0, 0, thickness, sampleMod, md={})
            sampleMod = setSampleName(phase, index)
            md["title"] = sampleMod
            logger.info("Starting saxsExp: %s", sampleMod)
            yield from saxsExp(0, 0, thickness, sampleMod, md={})
            # WAXS disabled by default. Uncomment to enable:
            # sampleMod = setSampleName(phase, index)
            # md["title"] = sampleMod
            # yield from waxsExp(0, 0, thickness, sampleMod, md={})

    # =========================================================================
    # EXECUTION SEQUENCE
    # =========================================================================
    isDebugMode = rheometer_debug.get()
    recordFunctionRun()
    logger.info(
        "Starting myRheometerPlan_template | sample=%s | x=%.2f leg=%.2f | "
        "before=%d after=%d | debug=%s",
        scan_title,
        rheo_x,
        rheo_leg,
        numCollections_before,
        numCollections_after,
        isDebugMode,
    )

    # -------------------------------------------------------------------------
    # BLOCK 1: Startup
    # -------------------------------------------------------------------------
    if not isDebugMode:
        logger.info("Running before_command_list()")
        yield from before_command_list()
    else:
        logger.info("[DEBUG] Skipping before_command_list()")

    appendToMdFile(
        f"Starting rheometer plan: sample={scan_title}, "
        f"x={rheo_x} mm, leg={rheo_leg} mm, "
        f"before={numCollections_before}, after={numCollections_after}"
    )

    # -------------------------------------------------------------------------
    # BLOCK 2: Move rheometer into position
    # -------------------------------------------------------------------------
    logger.info("Moving rheometer to x=%.2f mm, legs=%.2f mm", rheo_x, rheo_leg)
    yield from moveRheometerStage(rheo_x, rheo_leg)
    appendToMdFile(f"Rheometer moved to x={rheo_x} mm, legs={rheo_leg} mm")

    # -------------------------------------------------------------------------
    # BLOCK 3: Baseline ("pre") collection, before the RheoCompass trigger
    # -------------------------------------------------------------------------
    t0 = time.time()
    for i in range(1, numCollections_before + 1):
        logger.info("Baseline collection %d of %d", i, numCollections_before)
        yield from collectAllThree("pre", i, isDebugMode)

    # -------------------------------------------------------------------------
    # BLOCK 4: Trigger RheoCompass
    # -------------------------------------------------------------------------
    yield from triggerRheoCompass()
    appendToMdFile("Sent RheoCompass trigger (galil_voltage 5V pulse)")

    # Reset t0 so "post" file names report minutes since the trigger.
    t0 = time.time()

    # -------------------------------------------------------------------------
    # BLOCK 5: Response ("post") collection, after the RheoCompass trigger
    # -------------------------------------------------------------------------
    for i in range(1, numCollections_after + 1):
        logger.info("Response collection %d of %d", i, numCollections_after)
        yield from collectAllThree("post", i, isDebugMode)

    logger.info("Plan complete: %s", scan_title)
    appendToMdFile(f"Plan complete: {scan_title}")

    # -------------------------------------------------------------------------
    # BLOCK 6: Teardown
    # -------------------------------------------------------------------------
    if not isDebugMode:
        logger.info("Running after_command_list()")
        yield from after_command_list()
    else:
        logger.info("[DEBUG] Skipping after_command_list()")


# ==============================================================================
# EXAMPLE: MULTIPLE POSITIONS UNDER ONE CONDITION
# ==============================================================================
# The following commented-out skeleton shows how to extend the template when
# several spots need to be measured under the same RheoCompass condition
# (e.g. several locations on one sample after one shear step), instead of
# the single (rheo_x, rheo_leg) pair above.
#
# RheometerPositions = [
#     # [x_mm, leg_mm, thickness_mm, "position_label"]
#     [10.0, 3.0, 1.0, "spot1"],
#     [12.5, 3.0, 1.0, "spot2"],
#     [15.0, 3.0, 1.0, "spot3"],
# ]
#
# def myRheometerMultiPosPlan_template(
#     scan_title, numCollections_before, numCollections_after, md={}
# ):
#     """Move through RheometerPositions; trigger + collect at each."""
#     # ... (inner helpers: setSampleName, moveRheometerStage,
#     #      triggerRheoCompass, collectAllThree — same as above, but
#     #      setSampleName should also fold position_label into the name) ...
#
#     isDebugMode = rheometer_debug.get()
#     recordFunctionRun()
#     if not isDebugMode:
#         yield from before_command_list()
#     appendToMdFile(f"Starting multi-position rheometer plan: {scan_title}")
#
#     for rheo_x, rheo_leg, thickness, position_label in RheometerPositions:
#         yield from moveRheometerStage(rheo_x, rheo_leg)
#         appendToMdFile(f"{position_label}: moved to x={rheo_x}, leg={rheo_leg}")
#
#         t0 = time.time()
#         for i in range(1, numCollections_before + 1):
#             yield from collectAllThree("pre", i, isDebugMode)
#
#         yield from triggerRheoCompass()
#         appendToMdFile(f"{position_label}: sent RheoCompass trigger")
#         t0 = time.time()
#
#         for i in range(1, numCollections_after + 1):
#             yield from collectAllThree("post", i, isDebugMode)
#
#     appendToMdFile(f"Plan complete: {scan_title}")
#     if not isDebugMode:
#         yield from after_command_list()
