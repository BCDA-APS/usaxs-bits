"""
AI-assisted Linkam TC-1 experiment plan template for USAXS/SAXS/WAXS data collection.

==============================================================================
PURPOSE AND USAGE FOR AI PLAN DEVELOPMENT
==============================================================================

This file is the recommended starting point when an AI assistant (e.g. Claude)
is asked to write a custom Linkam temperature-ramp experiment plan for a user.

Workflow for AI-assisted plan creation:
    1. User describes their experiment (temperatures, ramp rates, hold times,
       which detectors to use during each segment, etc.).
    2. AI copies myLinkamPlan_AI_template to a new function with a descriptive name.
    3. AI fills in parameters, adds/removes heating segments, selects data-collection
       strategy for each segment, and updates the docstring.
    4. The new file is loaded with:
           %run -im usaxs.user.<new_filename>
    5. Tested in debug mode first:
           linkam_debug.put(True)
           RE(myNewPlan(...))
    6. Real run after validation:
           linkam_debug.put(False)
           RE(myNewPlan(...))

==============================================================================
DEBUG MODE — CRITICAL FOR SAFE TESTING
==============================================================================

``linkam_debug`` is an ophyd Signal (persistent in the IPython session).
Set it BEFORE calling RE():

    linkam_debug.put(True)   # enable debug mode
    linkam_debug.put(False)  # restore normal operation

When isDebugMode is True:
    - before_command_list() is SKIPPED  → no instrument initialisation
    - after_command_list() is SKIPPED   → no instrument teardown
    - collectAllThree() / collectWAXS() / collectSAXS() print the sample name
      and sleep 20 s instead of moving the instrument
    - Linkam temperature ramps and holds run NORMALLY — the full thermal cycle
      is exercised so timing can be validated without risk to the instrument

The three instrument-triggering calls that MUST be gated on isDebugMode are:
    1. before_command_list()        — instrument startup
    2. collectAllThree() / collect* — data acquisition
    3. after_command_list()         — instrument teardown

==============================================================================
INSTRUMENT OPERATIONS OVERVIEW
==============================================================================

before_command_list():
    Standard pre-scan startup:
      - Checks beam/shutter status
      - Opens Obsidian notebook entry for this measurement session
      - Sets up scan metadata
    SKIP IN DEBUG MODE.

after_command_list():
    Standard post-scan teardown:
      - Closes shutters, returns instrument to safe state
      - Writes "session ended" to Obsidian notebook
    SKIP IN DEBUG MODE.

sync_order_numbers():
    Synchronises USAXS / SAXS / WAXS scan counter values so the three
    detectors within one collectAllThree() call share a common scan-group ID.
    Call once at the START of each collectAllThree() (not inside debug branch).

appendToMdFile(message):
    Appends a human-readable line to the Obsidian Markdown notebook that is
    written for the user after each beamtime.  Use SPARINGLY — write only at
    meaningful transitions (plan start, temperature changes, segment changes,
    plan end).  Do NOT call in tight loops.

recordFunctionRun(func_name):
    Records that a named function was executed.  Optional, used for audit trail.

==============================================================================
LINKAM CONTROLLER INTERFACE
==============================================================================

linkam.temperature.position   : current temperature readback in °C
linkam.ramprate.setpoint      : target ramp rate in °C/min (set before set_target)
linkam.set_target(t, wait)    : move to temperature t in °C
    wait=True  → blocks until setpoint is reached (use for fast ramps where
                 data collection during the ramp is not desired or practical)
    wait=False → returns immediately; use a ``while not linkam.temperature.inposition``
                 loop around a collect* call to gather data during the ramp

linkam.temperature.inposition : True once setpoint has been reached and stabilised

==============================================================================
SAMPLE NAMING CONVENTION
==============================================================================

Format:  {scan_title}_{temperature:.0f}C_{elapsed_minutes:.0f}min

Examples:
    "MySample_200C_0min"     — first scan at 200 °C, t0 just reset
    "MySample_198C_22min"    — scan during cooling, 22 min since last t0 reset

Rules:
    - Call setSampleName() immediately before EVERY scan call so temperature
      and time values are accurate.
    - Reset  t0 = time.time()  at meaningful milestones:
        * After reaching a target temperature — time then means "hold time"
        * At plan start — time then means "total experiment elapsed"
        * At user-defined checkpoints for multi-segment plans
    - Do NOT share a single sampleMod across multiple scan calls in a sequence;
      refresh with setSampleName() before each scan because USAXS alone takes
      ~1–1.5 min and conditions change.

==============================================================================
DATA COLLECTION STRATEGY GUIDE (for AI plan writing)
==============================================================================

During a HEATING or COOLING ramp the choice between wait=True / wait=False
trades off temporal resolution against data density:

  wait=True  + no collect loop:
      Fastest to target; clean before/after datasets; no data during transition.
      Use for:  fast ramps (>50 °C/min), unwanted intermediate data, short ramps.

  wait=False + while not inposition loop + collectAllThree:
      Full USAXS/SAXS/WAXS sets collected every ~15 min during ramp.
      Use for:  slow ramps (<20 °C/min), phase transitions expected during ramp.

  wait=False + while not inposition loop + collectWAXS:
      WAXS only during ramp — much faster (~2–3 min/frame), better time resolution.
      Use for:  fast structural changes, kinetics, any ramp >10 °C/min.

During a HOLD (isothermal segment):
    Always use a time-based while loop:
        hold_until = time.time() + hold_minutes * MINUTE
        while time.time() < hold_until:
            yield from collectAllThree(isDebugMode)

For STEP RAMPS (discrete temperature steps):
    Use a for/while loop over temperature values; call change_rate_and_temperature
    with wait=True then collect 1–N datasets at each step before moving on.

==============================================================================
OBSIDIAN NOTEBOOK LOGGING GUIDE
==============================================================================

appendToMdFile() writes to the user's Obsidian notebook.  Write at:
    - Plan start (sample ID, conditions summary)
    - Start of each heating or cooling ramp (target T, rate)
    - Arrival at each target temperature
    - Start and end of each hold segment
    - Plan end (brief summary)

Do NOT write inside data-collection loops — that would flood the notebook.
Keep each message to one concise line; the notebook reader is a human.

==============================================================================
CUSTOMISATION CHECKLIST FOR AI
==============================================================================

When creating a new plan from this template:
    [ ] Rename the function (replace myLinkamPlan_AI_template)
    [ ] Update the module-level docstring and function docstring
    [ ] Add/remove parameters for extra heating segments
    [ ] Choose collect strategy (collectAllThree / collectWAXS / collectSAXS)
      for each segment (heat ramp, hold, cool ramp)
    [ ] Set appropriate ramp rates (fast 100–150 °C/min, slow 2–20 °C/min)
    [ ] Decide where to reset t0 (start, each temperature arrival, or both)
    [ ] Verify appendToMdFile calls cover key transitions without over-logging
    [ ] Confirm debug-mode guards are in place for all three instrument calls

CHANGE LOG:
    * JIL, 2026-02-25 : Initial AI-development template

LIMITATIONS:
    Uses new Linkam support only for tc1 with Linux IOC.
"""

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

import time

from bluesky import plan_stubs as bps
from apsbits.core.instrument_init import oregistry

from usaxs.plans.plans_user_facing import saxsExp
from usaxs.plans.plans_user_facing import waxsExp
from usaxs.plans.plans_usaxs import USAXSscan
from usaxs.plans.command_list import after_command_list
from usaxs.plans.command_list import before_command_list
from ophyd import Signal
from usaxs.plans.command_list import sync_order_numbers
from usaxs.utils.obsidian import appendToMdFile, recordFunctionRun

# Linkam TC-1 device registered in the ophyd device registry.
# All plans in this file use this controller.
linkam_tc1 = oregistry["linkam_tc1"]

# Convenient time-unit constants — use these in delay expressions.
# Example:  hold_until = time.time() + 30 * MINUTE
SECOND = 1
MINUTE = 60 * SECOND
HOUR = 60 * MINUTE
DAY = 24 * HOUR
WEEK = 7 * DAY

# Debug / dry-run flag.  Read once at plan start as isDebugMode.
# At the IPython prompt:
#   linkam_debug.put(True)   → debug mode on  (no instrument operations)
#   linkam_debug.put(False)  → normal mode on (real data collection)
linkam_debug = Signal(name="linkam_debug", value=False)


# ==============================================================================
# DO NOT MODIFY THIS TEMPLATE FUNCTION.
# Copy it to a new file and rename it for your experiment.
# ==============================================================================
def myLinkamPlan_AI_template(
    pos_X,
    pos_Y,
    thickness,
    scan_title,
    temp_target,
    rate_heat,
    delay_hold_min,
    temp_final=40,
    rate_cool=100,
    collect_during_heat=False,
    collect_during_cool=True,
    md={},
):
    """
    Standard single-ramp Linkam experiment with optional data collection during ramps.

    Sequence:
        1. Baseline: heat/cool to 40 °C, collect USAXS/SAXS/WAXS.
        2. Ramp to temp_target at rate_heat °C/min.
           If collect_during_heat=True: collect WAXS continuously during ramp.
           If collect_during_heat=False: wait silently for arrival.
        3. Hold at temp_target for delay_hold_min minutes, collecting USAXS/SAXS/WAXS.
        4. Cool to temp_final at rate_cool °C/min.
           If collect_during_cool=True: collect WAXS continuously during cooling.
           If collect_during_cool=False: wait silently for arrival.
        5. Final: collect USAXS/SAXS/WAXS at temp_final.

    Parameters
    ----------
    pos_X, pos_Y : float
        Sample stage X/Y position in mm.
    thickness : float
        Sample thickness in mm (used for transmission correction).
    scan_title : str
        Base name for all scans. Temperature and elapsed time are appended automatically.
    temp_target : float
        Target (hold) temperature in °C.
    rate_heat : float
        Ramp rate from baseline to temp_target in °C/min.
        Typical values: 5–20 °C/min (slow/kinetics), 50–150 °C/min (fast/jump).
    delay_hold_min : float
        Hold time at temp_target in minutes.
    temp_final : float, optional
        Terminal temperature in °C (default 40 °C, near room temperature).
    rate_cool : float, optional
        Cooling rate from temp_target to temp_final in °C/min (default 100 °C/min).
    collect_during_heat : bool, optional
        True  → collect WAXS while ramping to temp_target (wait=False mode).
        False → ramp silently to temp_target then begin data collection (wait=True mode).
        Default False (fast ramps are usually too quick for full sequences).
    collect_during_cool : bool, optional
        True  → collect WAXS while cooling to temp_final (wait=False mode).
        False → cool silently to temp_final then collect a final dataset.
        Default True (cooling is often slow enough for useful data).
    md : dict, optional
        Extra metadata passed into scan functions.

    Load with:
        %run -im usaxs.user.linkam_template_AI

    Enable debug mode (no instrument operations):
        linkam_debug.put(True)

    Run:
        RE(myLinkamPlan_AI_template(0, 0, 1.0, "MySample", 200, 20, 30))
    """

    # =========================================================================
    # INNER HELPER FUNCTIONS
    # These three functions are the standard building blocks for all Linkam plans.
    # Copy them verbatim to any new plan function derived from this template.
    # =========================================================================

    def setSampleName():
        """
        Return a sample name encoding scan_title, current temperature, and elapsed time.

        Format: {scan_title}_{temperature:.0f}C_{elapsed_minutes:.0f}min

        Call this immediately before every scan to capture current conditions.
        Time is measured from the last t0 = time.time() assignment.
        """
        return (
            f"{scan_title}"
            f"_{linkam.temperature.position:.0f}C"
            f"_{(time.time() - t0) / 60:.0f}min"
        )

    def collectAllThree(debug=False):
        """
        Run a full USAXS → SAXS → WAXS data-collection sequence.

        Each scan receives an independently generated sample name so that
        temperature and elapsed time are accurate for that specific scan,
        even though USAXS can take 10–15 minutes.

        sync_order_numbers() is called first so all three scans share one
        scan-group counter.

        Parameters
        ----------
        debug : bool
            When True, prints sample name and sleeps 20 s (no instrument motion).
            Pass isDebugMode here — NEVER hardcode True or False.
        """
        sampleMod = setSampleName()
        logger.debug("collectAllThree: sample name = %s", sampleMod)
        if debug:
            # Simulate a ~20 s data-collection cycle without moving the instrument.
            print(f"[DEBUG] collectAllThree: {sampleMod}")
            yield from bps.sleep(20)
        else:
            yield from sync_order_numbers()
            # --- USAXS ---
            sampleMod = setSampleName()
            md["title"] = sampleMod
            logger.info("Starting USAXSscan: %s", sampleMod)
            yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
            # --- SAXS ---
            sampleMod = setSampleName()
            md["title"] = sampleMod
            logger.info("Starting saxsExp: %s", sampleMod)
            yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
            # --- WAXS ---
            sampleMod = setSampleName()
            md["title"] = sampleMod
            logger.info("Starting waxsExp: %s", sampleMod)
            yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    def collectWAXS(debug=False):
        """
        Collect a single WAXS frame (~2–3 min per frame).

        Use during ramps where time resolution matters more than complete
        USAXS/SAXS/WAXS datasets.  WAXS is the fastest detector and gives
        the highest temporal sampling of structural changes.

        Parameters
        ----------
        debug : bool
            When True, prints sample name and sleeps 5 s (no instrument motion).
            Pass isDebugMode here — NEVER hardcode True or False.
        """
        sampleMod = setSampleName()
        logger.debug("collectWAXS: sample name = %s", sampleMod)
        if debug:
            print(f"[DEBUG] collectWAXS: {sampleMod}")
            yield from bps.sleep(5)
        else:
            md["title"] = sampleMod
            logger.info("Starting waxsExp (WAXS-only): %s", sampleMod)
            yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    def collectSAXS(debug=False):
        """
        Collect a single SAXS frame.

        Use when only SAXS is needed during a particular segment (e.g. when
        WAXS has no useful signal at the experiment temperature).

        Parameters
        ----------
        debug : bool
            When True, prints sample name and sleeps 5 s (no instrument motion).
            Pass isDebugMode here — NEVER hardcode True or False.
        """
        sampleMod = setSampleName()
        logger.debug("collectSAXS: sample name = %s", sampleMod)
        if debug:
            print(f"[DEBUG] collectSAXS: {sampleMod}")
            yield from bps.sleep(5)
        else:
            md["title"] = sampleMod
            logger.info("Starting saxsExp (SAXS-only): %s", sampleMod)
            yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    def change_rate_and_temperature(rate, t, wait=False):
        """
        Set the Linkam ramp rate and move to a new target temperature.

        Parameters
        ----------
        rate : float
            Ramp rate in °C/min.  Set before changing temperature.
        t : float
            Target temperature in °C.
        wait : bool
            True  → plan blocks here until the setpoint is reached.
                    No data collection during this time.
                    Use for fast ramps or when intermediate data are unwanted.
            False → plan returns immediately after sending the setpoint.
                    Immediately follow with a while not linkam.temperature.inposition
                    loop to collect data as the temperature changes.
        """
        logger.debug(
            "change_rate_and_temperature: rate=%s °C/min, target=%s °C, wait=%s",
            rate, t, wait,
        )
        yield from bps.mv(linkam.ramprate.setpoint, rate)
        yield from linkam.set_target(t, wait=wait)

    # =========================================================================
    # EXECUTION SEQUENCE
    # =========================================================================
    # Resolve Linkam device alias used throughout this plan.
    linkam = linkam_tc1

    # Read the debug flag once so behaviour is consistent for the entire plan.
    isDebugMode = linkam_debug.get()
    logger.info(
        "Starting myLinkamPlan_AI_template | sample=%s | debug=%s",
        scan_title, isDebugMode,
    )

    # -------------------------------------------------------------------------
    # BLOCK 1: Startup
    # before_command_list() initialises the instrument and opens the Obsidian
    # notebook entry for this session.  MUST be skipped in debug mode.
    # -------------------------------------------------------------------------
    if not isDebugMode:
        logger.info("Running before_command_list()")
        yield from before_command_list()
    else:
        logger.info("[DEBUG] Skipping before_command_list()")

    # Log plan parameters to both logger and Obsidian for traceability.
    appendToMdFile(
        f"Starting Linkam plan: sample={scan_title}, "
        f"target={temp_target} °C @ {rate_heat} °C/min, "
        f"hold={delay_hold_min} min, "
        f"cool to {temp_final} °C @ {rate_cool} °C/min"
    )
    logger.info(
        "Plan parameters: temp_target=%s C, rate_heat=%s C/min, "
        "hold=%s min, temp_final=%s C, rate_cool=%s C/min",
        temp_target, rate_heat, delay_hold_min, temp_final, rate_cool,
    )

    # -------------------------------------------------------------------------
    # BLOCK 2: Baseline data at near-room-temperature (40 °C)
    # 40 °C is the standard USAXS baseline temperature — above condensation
    # risk but low enough to compare against ambient-condition references.
    # Ramp at 150 °C/min (fast) and wait until stable before collecting.
    # -------------------------------------------------------------------------
    logger.info("Moving to baseline temperature 40 C at 150 C/min")
    yield from change_rate_and_temperature(150, 40, wait=True)

    # t0 marks "experiment start" — file names will show elapsed time from here.
    t0 = time.time()
    logger.info("At 40 C baseline. Collecting initial USAXS/SAXS/WAXS dataset.")
    appendToMdFile(f"At 40 C baseline. Collecting initial dataset.")
    yield from collectAllThree(isDebugMode)

    # -------------------------------------------------------------------------
    # BLOCK 3: Heat to temp_target
    # Two modes controlled by collect_during_heat:
    #   False (default): fast ramp, no data → cleaner experiment, simpler logic.
    #   True: WAXS only during ramp → useful for slow ramps / phase transitions.
    # -------------------------------------------------------------------------
    logger.info(
        "Heating to %s C at %s C/min (collect_during_heat=%s)",
        temp_target, rate_heat, collect_during_heat,
    )
    appendToMdFile(
        f"Heating to {temp_target} C at {rate_heat} C/min"
        + (" — collecting WAXS during ramp" if collect_during_heat else "")
    )

    if collect_during_heat:
        # Collect WAXS frames continuously as temperature rises.
        # WAXS is fastest (2–3 min/frame) for maximum time resolution.
        yield from change_rate_and_temperature(rate_heat, temp_target, wait=False)
        while not linkam.temperature.inposition:
            logger.debug("Collecting WAXS during heating ramp (T=%.1f C)", linkam.temperature.position)
            yield from collectWAXS(isDebugMode)
    else:
        # Silent ramp: block here until temp_target is reached, then continue.
        yield from change_rate_and_temperature(rate_heat, temp_target, wait=True)

    # Reset t0 so file names count elapsed time from when temp_target was reached.
    t0 = time.time()
    logger.info("Arrived at %s C. Beginning hold phase.", temp_target)
    appendToMdFile(f"Arrived at {temp_target} C. Beginning {delay_hold_min} min hold.")

    # -------------------------------------------------------------------------
    # BLOCK 4: Isothermal hold at temp_target — collect USAXS/SAXS/WAXS
    # Repeat full sequences until the hold timer expires.
    # The loop collects as many complete datasets as time allows.
    # -------------------------------------------------------------------------
    hold_until = time.time() + delay_hold_min * MINUTE
    logger.info("Hold phase: collecting until %s min elapsed.", delay_hold_min)
    while time.time() < hold_until:
        logger.debug(
            "Hold loop: %.1f min remaining",
            (hold_until - time.time()) / MINUTE,
        )
        yield from collectAllThree(isDebugMode)

    logger.info("Hold complete (%s min). Cooling to %s C.", delay_hold_min, temp_final)
    appendToMdFile(f"Hold complete ({delay_hold_min} min). Cooling to {temp_final} C.")

    # -------------------------------------------------------------------------
    # BLOCK 5: Cool to temp_final
    # Two modes controlled by collect_during_cool:
    #   True (default): collect WAXS during cooling → capture structural changes.
    #   False: cool silently then collect final dataset.
    # Cooling rate is typically 50–150 °C/min for fast cooling or
    # 2–10 °C/min for controlled slow cooling with kinetics data.
    # -------------------------------------------------------------------------
    logger.info(
        "Cooling to %s C at %s C/min (collect_during_cool=%s)",
        temp_final, rate_cool, collect_during_cool,
    )
    appendToMdFile(
        f"Cooling to {temp_final} C at {rate_cool} C/min"
        + (" — collecting WAXS during cooling" if collect_during_cool else "")
    )

    if collect_during_cool:
        yield from change_rate_and_temperature(rate_cool, temp_final, wait=False)
        while not linkam.temperature.inposition:
            logger.debug("Collecting WAXS during cooling (T=%.1f C)", linkam.temperature.position)
            yield from collectWAXS(isDebugMode)
    else:
        yield from change_rate_and_temperature(rate_cool, temp_final, wait=True)

    # -------------------------------------------------------------------------
    # BLOCK 6: Final dataset at temp_final
    # This serves as the post-treatment room-temperature reference, symmetric
    # with the baseline dataset collected in Block 2.
    # -------------------------------------------------------------------------
    logger.info("At %s C. Collecting final USAXS/SAXS/WAXS dataset.", temp_final)
    appendToMdFile(f"At {temp_final} C. Collecting final dataset.")
    yield from collectAllThree(isDebugMode)

    logger.info("Plan complete: %s", scan_title)
    appendToMdFile(f"Plan complete: {scan_title}")

    # -------------------------------------------------------------------------
    # BLOCK 7: Teardown
    # after_command_list() closes shutters, returns instrument to safe state,
    # and writes the session-end entry to the Obsidian notebook.
    # MUST be skipped in debug mode (mirrors Block 1 guard).
    # -------------------------------------------------------------------------
    if not isDebugMode:
        logger.info("Running after_command_list()")
        yield from after_command_list()
    else:
        logger.info("[DEBUG] Skipping after_command_list()")


# ==============================================================================
# EXAMPLE: MULTI-SEGMENT PLAN STRUCTURE
# ==============================================================================
# The following commented-out skeleton shows how to extend the template for
# experiments with multiple heating/cooling segments.  Each segment block
# follows the same structure: change temperature → optionally collect during
# ramp → hold and collect → log transitions.
#
# When an AI creates a multi-segment plan, expand the function signature to
# include (temp1, rate1, hold1min, temp2, rate2, hold2min, ...) as needed.
#
# def myMultiSegmentPlan(pos_X, pos_Y, thickness, scan_title,
#                        temp1, rate1, hold1min,
#                        temp2, rate2, hold2min,
#                        temp_final=40, rate_cool=100, md={}):
#     """
#     Two-segment heating plan example (extend as needed).
#     Segment 1: ramp to temp1, hold hold1min min, collect USAXS/SAXS/WAXS.
#     Segment 2: ramp to temp2, hold hold2min min, collect USAXS/SAXS/WAXS.
#     Cool to temp_final, collect final dataset.
#     """
#     # ... (inner helper functions: setSampleName, collectAllThree,
#     #      collectWAXS, change_rate_and_temperature) ...
#
#     linkam = linkam_tc1
#     isDebugMode = linkam_debug.get()
#
#     if not isDebugMode:
#         yield from before_command_list()
#     appendToMdFile(f"Starting multi-segment plan: {scan_title}")
#
#     # --- Baseline at 40 C ---
#     yield from change_rate_and_temperature(150, 40, wait=True)
#     t0 = time.time()
#     yield from collectAllThree(isDebugMode)
#
#     # --- Segment 1: heat to temp1, hold hold1min ---
#     appendToMdFile(f"Heating to {temp1} C at {rate1} C/min")
#     yield from change_rate_and_temperature(rate1, temp1, wait=True)
#     t0 = time.time()
#     appendToMdFile(f"Arrived at {temp1} C, holding {hold1min} min")
#     hold_until = time.time() + hold1min * MINUTE
#     while time.time() < hold_until:
#         yield from collectAllThree(isDebugMode)
#     appendToMdFile(f"Segment 1 hold complete")
#
#     # --- Segment 2: heat/cool to temp2, hold hold2min ---
#     appendToMdFile(f"Changing to {temp2} C at {rate2} C/min")
#     yield from change_rate_and_temperature(rate2, temp2, wait=False)
#     while not linkam.temperature.inposition:
#         yield from collectWAXS(isDebugMode)
#     t0 = time.time()
#     appendToMdFile(f"Arrived at {temp2} C, holding {hold2min} min")
#     hold_until = time.time() + hold2min * MINUTE
#     while time.time() < hold_until:
#         yield from collectAllThree(isDebugMode)
#     appendToMdFile(f"Segment 2 hold complete")
#
#     # --- Cool to temp_final, final dataset ---
#     appendToMdFile(f"Cooling to {temp_final} C at {rate_cool} C/min")
#     yield from change_rate_and_temperature(rate_cool, temp_final, wait=False)
#     while not linkam.temperature.inposition:
#         yield from collectWAXS(isDebugMode)
#     appendToMdFile(f"At {temp_final} C, collecting final dataset")
#     yield from collectAllThree(isDebugMode)
#
#     appendToMdFile(f"Plan complete: {scan_title}")
#     if not isDebugMode:
#         yield from after_command_list()
