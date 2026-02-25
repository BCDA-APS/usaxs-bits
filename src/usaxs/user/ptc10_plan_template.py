"""
AI-assisted PTC10 temperature controller experiment plan template.

==============================================================================
PURPOSE AND USAGE FOR AI PLAN DEVELOPMENT
==============================================================================

This file is the recommended starting point when an AI assistant (e.g. Claude)
is asked to write a custom PTC10 furnace experiment plan for a user.

Workflow for AI-assisted plan creation:
    1. User describes their experiment (temperatures, ramp rates, hold times,
       single vs multi-position, which detectors for each segment, etc.).
    2. AI copies the appropriate template function (single-position or SampleList)
       to a new file with a descriptive name.
    3. AI fills in parameters, adds/removes heating segments, adjusts the
       data collection strategy, and updates the docstring.
    4. Load the new file:
           %run -im usaxs.user.<new_filename>
    5. Test in debug mode first:
           ptc10_debug.put(True)
           RE(myNewPlan(...))
    6. Real run after validation:
           ptc10_debug.put(False)
           RE(myNewPlan(...))

==============================================================================
PTC10 vs LINKAM — KEY DIFFERENCES FOR AI PLAN WRITING
==============================================================================

| Feature                | Linkam TC-1                          | PTC10                                  |
|------------------------|--------------------------------------|----------------------------------------|
| Temperature readback   | linkam.temperature.position          | ptc10.position                         |
| Set target temperature | linkam.set_target(t, wait=True/False)| bps.mv(ptc10.temperature.setpoint, t) |
| Ramp rate units        | °C/min → ramprate.setpoint directly  | °C/min → must divide by 60 for °C/s   |
| Wait for arrival       | built into set_target(wait=True)     | manual: while not inposition: sleep()  |
| Heater on/off          | always on while connected            | explicit setheaterOn() / setheaterOff()|
| In-position check      | linkam.temperature.inposition        | ptc10.temperature.inposition           |

RAMP RATE CONVERSION (critical):
    PTC10 controller stores ramp rate in °C/second.
    User specifies rates in °C/minute — ALWAYS divide by 60:
        yield from bps.mv(ptc10.ramp, rate_C_per_min / 60.0)

HEATER SEQUENCE:
    To start a ramp correctly, always follow this order:
        1. Set rate:     yield from bps.mv(ptc10.ramp, rate / 60.0)
        2. Set target:   yield from bps.mv(ptc10.temperature.setpoint, temp)
        3. Start heater: yield from setheaterOn()
        4. Wait/collect: while not ptc10.temperature.inposition: ...
    At end of plan: yield from setheaterOff()

==============================================================================
DEBUG MODE — CRITICAL FOR SAFE TESTING
==============================================================================

``ptc10_debug`` is an ophyd Signal (persistent in the IPython session).
Set it BEFORE calling RE():

    ptc10_debug.put(True)   # enable debug mode
    ptc10_debug.put(False)  # restore normal operation

When isDebugMode is True:
    - before_command_list() is SKIPPED  → no instrument initialisation
    - after_command_list() is SKIPPED   → no instrument teardown
    - collectAllThree() / collectWAXS() print the sample name
      and sleep 20 s / 5 s instead of moving the instrument
    - PTC10 temperature control still runs NORMALLY — full thermal cycle
      is exercised so timing and setpoint logic can be validated safely

The three instrument-triggering calls that MUST be gated on isDebugMode:
    1. before_command_list()     — instrument startup
    2. collect*() functions      — data acquisition
    3. after_command_list()      — instrument teardown

setheaterOn() and setheaterOff() do NOT need debug guards — we want the
real PTC10 temperature cycle to run during debug testing.

==============================================================================
SAMPLE NAMING CONVENTION
==============================================================================

Format:  {scan_title}_{temperature:.0f}C_{elapsed_minutes:.0f}min

Rules:
    - Call getSampleName() immediately before EVERY scan to get current T and time.
    - Reset  t0 = time.time()  at meaningful milestones:
        * At plan start — total elapsed time
        * After reaching a target temperature — "hold time elapsed"
        * At user-defined checkpoints in multi-segment plans
    - In multi-position plans, scan_title is taken from each SampleList entry so
      each position gets its own unique identifier in the filename.

==============================================================================
MULTI-POSITION (SampleList) PATTERN
==============================================================================

The SampleList pattern allows measuring multiple sample spots or distinct samples
that are all in the furnace simultaneously. Each list entry is:
    [pos_X_mm, pos_Y_mm, thickness_mm, "SampleName"]

Define the list at the TOP of your plan file (module level), NOT inside the
function, so users can edit it easily before each beamtime:

    SampleList = [
        [0.0, 0.0, 1.3, "SampleA_pos1"],
        [1.5, 0.0, 1.3, "SampleA_pos2"],
        [3.0, 0.0, 1.2, "SampleB"],
    ]

Then iterate in the data-collection blocks:
    for pos_X, pos_Y, thickness, scan_title in SampleList:
        yield from collectAllThree(pos_X, pos_Y, thickness, scan_title, isDebugMode)

During heating ramps where only WAXS is collected, same pattern applies:
    for pos_X, pos_Y, thickness, scan_title in SampleList:
        yield from collectWAXS(pos_X, pos_Y, thickness, scan_title, isDebugMode)

==============================================================================
DATA COLLECTION STRATEGY GUIDE (for AI plan writing)
==============================================================================

During a HEATING RAMP:
    Option A — silent ramp (no data):
        while not ptc10.temperature.inposition:
            yield from bps.sleep(5)
        Use for: fast ramps, short ramps, unwanted intermediate data.

    Option B — WAXS only during ramp (best for kinetics, phase transitions):
        while not ptc10.temperature.inposition:
            yield from collectWAXS(pos_X, pos_Y, thickness, scan_title, isDebugMode)
        Use for: slow ramps where phase changes are expected.

    Option C — full USAXS/SAXS/WAXS during ramp (only for very slow ramps):
        while not ptc10.temperature.inposition:
            yield from collectAllThree(pos_X, pos_Y, thickness, scan_title, isDebugMode)
        Use for: <5 °C/min ramps where full datasets are feasible.

During an ISOTHERMAL HOLD:
    Always use a time-based while loop:
        hold_until = time.time() + hold_min * 60
        while time.time() < hold_until:
            yield from collectAllThree(...)    # or collectWAXS(...)

During PASSIVE COOLING (heater off):
    Collect until temperature drops below threshold:
        while ptc10.position > temp_threshold:
            yield from collectAllThree(...)

For STEP RAMPS (discrete temperature steps):
    for target_T in [100, 200, 300, 400, 500]:
        yield from bps.mv(ptc10.ramp, rate / 60.0)
        yield from bps.mv(ptc10.temperature.setpoint, target_T)
        yield from setheaterOn()
        while not ptc10.temperature.inposition:
            yield from bps.sleep(5)
        yield from bps.sleep(stabilize_min * 60)    # optional: wait to stabilise
        yield from collectAllThree(...)

==============================================================================
OBSIDIAN NOTEBOOK LOGGING GUIDE
==============================================================================

appendToMdFile() writes to the user's Obsidian notebook. Write at:
    - Plan start (sample ID, key parameters)
    - Start of each heating or cooling ramp
    - Arrival at each target temperature
    - Start and end of each hold segment
    - Plan end

Do NOT call inside tight data-collection loops. One meaningful line per
transition. The notebook reader is a human.

==============================================================================
CUSTOMISATION CHECKLIST FOR AI
==============================================================================

When creating a new plan from this template:
    [ ] Rename the function (replace myPTC10Plan_AI_template or myPTC10PlanList_AI_template)
    [ ] Update the SampleList at module level (for multi-position plans)
    [ ] Update TemperatureList / TimeList if using the list-based pattern
    [ ] Add/remove parameters for extra heating segments
    [ ] Choose data collection strategy for each segment (silent / WAXS / all-three)
    [ ] Remember rate conversion: user °C/min → ptc10.ramp = rate / 60.0
    [ ] Confirm setheaterOn() is called AFTER setting rate and setpoint
    [ ] Confirm setheaterOff() is called at the end
    [ ] Verify debug-mode guards are in place for all three instrument calls
    [ ] Decide where to reset t0

CHANGE LOG:
    * JIL, 2026-02-25 : Initial AI-development template
"""

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

import time

from bluesky import plan_stubs as bps
from apsbits.core.instrument_init import oregistry
from ophyd import Signal

from usaxs.plans.plans_user_facing import saxsExp
from usaxs.plans.plans_user_facing import waxsExp
from usaxs.plans.plans_usaxs import USAXSscan
from usaxs.plans.command_list import after_command_list, sync_order_numbers
from usaxs.plans.command_list import before_command_list
from usaxs.utils.obsidian import appendToMdFile

# PTC10 temperature controller from the ophyd device registry.
ptc10 = oregistry["ptc10"]

# Convenient time-unit constants.
# Example: hold_until = time.time() + 30 * MINUTE
SECOND = 1
MINUTE = 60 * SECOND
HOUR = 60 * MINUTE
DAY = 24 * HOUR

# Debug / dry-run flag. Read once at plan start as isDebugMode.
# At the IPython prompt:
#   ptc10_debug.put(True)   → debug mode on  (no instrument operations)
#   ptc10_debug.put(False)  → normal mode on (real data collection)
ptc10_debug = Signal(name="ptc10_debug", value=False)

# ==============================================================================
# MODULE-LEVEL SAMPLE AND TEMPERATURE LISTS
# Edit these before each run, then reload the file.
# These are used by the multi-position (SampleList) plan variant below.
# ==============================================================================

# SampleList: each entry is [pos_X_mm, pos_Y_mm, thickness_mm, "SampleName"]
# Edit this to match the sample positions in the furnace for this experiment.
SampleList = [
    [0.0, 0.0, 1.3, "SamplePos1"],
    [1.5, 0.0, 1.3, "SamplePos2"],
    # [3.0, 0.0, 1.3, "SamplePos3"],  # uncomment to add more positions
]

# TemperatureList / TimeList: used by list-driven multi-temperature plans.
# Each pair (temperature, hold_time) is executed sequentially.
TemperatureList = [200, 400, 600]   # °C — temperatures to step through
TimeList = [30, 60, 30]             # minutes — hold time at each temperature


# ==============================================================================
# Heater control utilities (same as in ptc10_planG.py)
# ==============================================================================

def setheaterOff():
    """
    Power down the PTC10 heater and stop the PID control loop.

    Call at the end of every plan that activates the heater.
    Both 'enable' and 'pidmode' must be Off together.
    """
    yield from bps.mv(
        ptc10.enable, "Off",
        ptc10.pid.pidmode, "Off",
    )


def setheaterOn():
    """
    Power up the PTC10 heater and start the PID control loop.

    Always call AFTER setting ptc10.ramp and ptc10.temperature.setpoint.
    Both 'enable' and 'pidmode' must be On together.
    """
    yield from bps.mv(
        ptc10.enable, "On",
        ptc10.pid.pidmode, "On",
    )


# ==============================================================================
# TEMPLATE 1: SINGLE-POSITION PLAN
# Standard heat-hold-cool workflow for one sample at a fixed XY position.
# ==============================================================================

# DO NOT MODIFY THIS TEMPLATE — copy it to a new file and rename it.
def myPTC10Plan_AI_template(
    pos_X,
    pos_Y,
    thickness,
    scan_title,
    temp_target,
    rate_heat,
    delay_hold_min,
    temp_final=40,
    rate_cool=50,
    collect_during_heat=False,
    collect_during_cool=True,
    md={},
):
    """
    Standard single-position PTC10 experiment: baseline → heat → hold → cool.

    Sequence:
        1. Baseline: collect USAXS/SAXS/WAXS at ambient temperature.
        2. Ramp to temp_target at rate_heat °C/min.
           If collect_during_heat=True: collect WAXS during ramp.
           If collect_during_heat=False: wait silently (sleep-based).
        3. Hold at temp_target for delay_hold_min minutes, collecting USAXS/SAXS/WAXS.
        4. Switch heater off OR ramp to temp_final at rate_cool °C/min.
           If collect_during_cool=True: collect WAXS during cooling.
           If collect_during_cool=False: wait silently.
        5. Final: collect USAXS/SAXS/WAXS at temp_final.

    Parameters
    ----------
    pos_X, pos_Y : float
        Sample stage X/Y position in mm.
    thickness : float
        Sample thickness in mm.
    scan_title : str
        Base name for all scans. Temperature and elapsed time are appended automatically.
    temp_target : float
        Target (hold) temperature in °C.
    rate_heat : float
        Ramp rate to temp_target in °C/min.
    delay_hold_min : float
        Hold time at temp_target in minutes.
    temp_final : float, optional
        Terminal temperature in °C (default 40 °C, near room temperature).
        If None, heater is switched off and passive cooling is used.
    rate_cool : float, optional
        Cooling ramp rate in °C/min (default 50 °C/min).
        Only used when temp_final is specified.
    collect_during_heat : bool, optional
        True → collect WAXS while ramping to temp_target.
        False → wait silently (default — for fast ramps).
    collect_during_cool : bool, optional
        True → collect WAXS while cooling to temp_final (default).
        False → wait silently.
    md : dict, optional
        Extra metadata.

    Load:
        %run -im usaxs.user.ptc10_plan_template

    Debug mode (no instrument operations):
        ptc10_debug.put(True)

    Run:
        RE(myPTC10Plan_AI_template(0, 0, 1.3, "MySample", 500, 50, 60))
    """

    # =========================================================================
    # INNER HELPER FUNCTIONS
    # Copy these verbatim to any derived plan — they are the standard building
    # blocks. The only allowed modification is the function body of collectAllThree
    # if you need to change which detectors are used.
    # =========================================================================

    def getSampleName():
        """
        Return a sample name encoding scan_title, current PTC10 temperature,
        and elapsed minutes since the last t0 reset.

        Format: {scan_title}_{temperature:.0f}C_{elapsed_minutes:.0f}min

        Call immediately before every scan to capture current conditions.
        """
        return (
            f"{scan_title}"
            f"_{ptc10.position:.0f}C"
            f"_{(time.time() - t0) / 60:.0f}min"
        )

    def collectAllThree(debug=False):
        """
        Run a full USAXS → SAXS → WAXS sequence for this sample position.

        getSampleName() is called before each scan for accurate labels.
        sync_order_numbers() is called first to group the three scans.

        Parameters
        ----------
        debug : bool
            True → print sample name and sleep 20 s (no instrument motion).
            Pass isDebugMode here — never hardcode True or False.
        """
        sampleMod = getSampleName()
        logger.debug("collectAllThree: %s", sampleMod)
        if debug:
            print(f"[DEBUG] collectAllThree: {sampleMod}")
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

    def collectWAXS(debug=False):
        """
        Collect a single WAXS frame (~2–3 min).

        Use during ramps for maximum temporal resolution. WAXS is the fastest
        detector and best for tracking kinetic or structural changes during
        temperature transitions.

        Parameters
        ----------
        debug : bool
            True → print sample name and sleep 5 s (no instrument motion).
            Pass isDebugMode here — never hardcode True or False.
        """
        sampleMod = getSampleName()
        logger.debug("collectWAXS: %s", sampleMod)
        if debug:
            print(f"[DEBUG] collectWAXS: {sampleMod}")
            yield from bps.sleep(5)
        else:
            md["title"] = sampleMod
            logger.info("waxsExp (WAXS-only): %s", sampleMod)
            yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    # =========================================================================
    # EXECUTION SEQUENCE
    # =========================================================================

    # Read debug flag once so behaviour is consistent throughout the plan.
    isDebugMode = ptc10_debug.get()
    logger.info(
        "Starting myPTC10Plan_AI_template | sample=%s | target=%s C | debug=%s",
        scan_title, temp_target, isDebugMode,
    )

    # --- Block 1: Startup ------------------------------------------------
    if not isDebugMode:
        logger.info("Running before_command_list()")
        yield from before_command_list()
    else:
        logger.info("[DEBUG] Skipping before_command_list()")

    appendToMdFile(
        f"Starting PTC10 plan: sample={scan_title}, "
        f"target={temp_target} °C @ {rate_heat} °C/min, "
        f"hold={delay_hold_min} min"
    )

    # --- Block 2: Baseline data at ambient temperature -------------------
    # t0 marks experiment start — elapsed time in file names counts from here.
    t0 = time.time()
    logger.info("Collecting baseline dataset at ambient temperature")
    appendToMdFile(f"Collecting baseline data at ambient temperature")
    yield from collectAllThree(isDebugMode)

    # --- Block 3: Heat to temp_target ------------------------------------
    # Set rate (°C/min → °C/s), set target, start heater.
    logger.info(
        "Heating to %s C at %s C/min (collect_during_heat=%s)",
        temp_target, rate_heat, collect_during_heat,
    )
    appendToMdFile(
        f"Heating to {temp_target} C at {rate_heat} C/min"
        + (" — collecting WAXS during ramp" if collect_during_heat else "")
    )
    yield from bps.mv(ptc10.ramp, rate_heat / 60.0)          # rate: °C/s
    yield from bps.mv(ptc10.temperature.setpoint, temp_target)
    yield from setheaterOn()

    if collect_during_heat:
        # Collect WAXS frames continuously as temperature rises.
        while not ptc10.temperature.inposition:
            logger.debug(
                "Collecting WAXS during heating (T=%.1f C)", ptc10.position
            )
            yield from collectWAXS(isDebugMode)
    else:
        # Silent ramp: sleep-check loop until setpoint reached.
        while not ptc10.temperature.inposition:
            logger.debug("Ramping to %s C, current T=%.1f C", temp_target, ptc10.position)
            yield from bps.sleep(5)

    # Reset t0 so file names count "hold time" from temperature arrival.
    t0 = time.time()
    logger.info("Arrived at %s C. Beginning hold phase.", temp_target)
    appendToMdFile(f"Arrived at {temp_target} C. Beginning {delay_hold_min} min hold.")

    # --- Block 4: Isothermal hold ----------------------------------------
    # Collect USAXS/SAXS/WAXS repeatedly until hold timer expires.
    hold_until = time.time() + delay_hold_min * MINUTE
    logger.info("Hold phase: %s min", delay_hold_min)
    while time.time() < hold_until:
        logger.debug(
            "Hold loop: %.1f min remaining", (hold_until - time.time()) / MINUTE
        )
        yield from collectAllThree(isDebugMode)

    logger.info("Hold complete (%s min).", delay_hold_min)
    appendToMdFile(f"Hold complete ({delay_hold_min} min). Cooling to {temp_final} C.")

    # --- Block 5: Cool to temp_final -------------------------------------
    logger.info(
        "Cooling to %s C at %s C/min (collect_during_cool=%s)",
        temp_final, rate_cool, collect_during_cool,
    )
    appendToMdFile(
        f"Cooling to {temp_final} C at {rate_cool} C/min"
        + (" — collecting WAXS during cooling" if collect_during_cool else "")
    )
    yield from bps.mv(ptc10.ramp, rate_cool / 60.0)
    yield from bps.mv(ptc10.temperature.setpoint, temp_final)
    # Heater stays on for controlled cooling to temp_final.
    # To use passive (uncontrolled) cooling instead, call setheaterOff() here
    # and replace the loop below with: while ptc10.position > temp_final: ...

    if collect_during_cool:
        while not ptc10.temperature.inposition:
            logger.debug("Collecting WAXS during cooling (T=%.1f C)", ptc10.position)
            yield from collectWAXS(isDebugMode)
    else:
        while not ptc10.temperature.inposition:
            logger.debug(
                "Cooling to %s C, current T=%.1f C", temp_final, ptc10.position
            )
            yield from bps.sleep(5)

    yield from setheaterOff()

    # --- Block 6: Final dataset ------------------------------------------
    logger.info("At %s C. Collecting final dataset.", temp_final)
    appendToMdFile(f"At {temp_final} C. Collecting final dataset.")
    yield from collectAllThree(isDebugMode)

    logger.info("Plan complete: %s", scan_title)
    appendToMdFile(f"Plan complete: {scan_title}")

    # --- Block 7: Teardown -----------------------------------------------
    if not isDebugMode:
        logger.info("Running after_command_list()")
        yield from after_command_list()
    else:
        logger.info("[DEBUG] Skipping after_command_list()")


# ==============================================================================
# TEMPLATE 2: MULTI-POSITION (SampleList) PLAN
# Measures multiple positions at each temperature step using SampleList above.
# Key additions vs single-position:
#   - collectAllThree and collectWAXS accept (pos_X, pos_Y, thickness, scan_title)
#   - All data-collection blocks loop over SampleList
#   - SampleList and TemperatureList/TimeList are defined at module level
# ==============================================================================

# DO NOT MODIFY THIS TEMPLATE — copy it to a new file and rename it.
def myPTC10PlanList_AI_template(
    rate_heat,
    delay_hold_min,
    temp_final=40,
    rate_cool=50,
    collect_during_heat=False,
    collect_during_cool=True,
    md={},
):
    """
    Multi-position PTC10 experiment using module-level SampleList and TemperatureList.

    Measures all positions in SampleList at every temperature in TemperatureList.
    For each temperature step:
        - Ramp to target temperature
        - Hold for the corresponding time from TimeList
        - Cycle through all SampleList positions collecting USAXS/SAXS/WAXS

    Parameters
    ----------
    rate_heat : float
        Ramp rate for all heating steps in °C/min.
    delay_hold_min : float
        Hold time at each temperature step in minutes.
        (Overrides TimeList — set to 0 to use TimeList values instead.)
    temp_final : float, optional
        Terminal temperature after all steps (default 40 °C).
    rate_cool : float, optional
        Cooling rate from last temperature to temp_final in °C/min.
    collect_during_heat : bool, optional
        True → collect WAXS on all positions during each heating ramp.
    collect_during_cool : bool, optional
        True → collect WAXS on all positions during final cooling.
    md : dict, optional
        Extra metadata.

    Edit SampleList, TemperatureList, and TimeList at the top of this file
    before loading. Then:

    Load:
        %run -im usaxs.user.ptc10_plan_template

    Debug mode:
        ptc10_debug.put(True)

    Run:
        RE(myPTC10PlanList_AI_template(50, 30))
    """

    # =========================================================================
    # INNER HELPER FUNCTIONS
    # For multi-position plans, collectAllThree and collectWAXS accept explicit
    # position/title arguments so they can be called in a SampleList loop.
    # =========================================================================

    def getSampleName(scan_title):
        """
        Return a sample name encoding scan_title, current temperature, and elapsed time.
        scan_title comes from each SampleList entry so every position gets its own name.
        """
        return (
            f"{scan_title}"
            f"_{ptc10.position:.0f}C"
            f"_{(time.time() - t0) / 60:.0f}min"
        )

    def collectAllThree(pos_X, pos_Y, thickness, scan_title, debug=False):
        """
        Run USAXS → SAXS → WAXS for one position from SampleList.

        Parameters
        ----------
        pos_X, pos_Y : float   — stage position for this sample
        thickness : float      — sample thickness for this sample
        scan_title : str       — name for this sample (from SampleList)
        debug : bool           — pass isDebugMode; True skips real scans
        """
        sampleMod = getSampleName(scan_title)
        logger.debug("collectAllThree [%s]: %s", scan_title, sampleMod)
        if debug:
            print(f"[DEBUG] collectAllThree [{scan_title}]: {sampleMod}")
            yield from bps.sleep(20)
        else:
            yield from sync_order_numbers()
            sampleMod = getSampleName(scan_title)
            md["title"] = sampleMod
            logger.info("USAXSscan: %s", sampleMod)
            yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = getSampleName(scan_title)
            md["title"] = sampleMod
            logger.info("saxsExp: %s", sampleMod)
            yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = getSampleName(scan_title)
            md["title"] = sampleMod
            logger.info("waxsExp: %s", sampleMod)
            yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    def collectWAXS(pos_X, pos_Y, thickness, scan_title, debug=False):
        """
        Collect one WAXS frame for one position from SampleList.

        Parameters
        ----------
        pos_X, pos_Y : float   — stage position
        thickness : float      — sample thickness
        scan_title : str       — sample name (from SampleList)
        debug : bool           — pass isDebugMode
        """
        sampleMod = getSampleName(scan_title)
        logger.debug("collectWAXS [%s]: %s", scan_title, sampleMod)
        if debug:
            print(f"[DEBUG] collectWAXS [{scan_title}]: {sampleMod}")
            yield from bps.sleep(5)
        else:
            md["title"] = sampleMod
            logger.info("waxsExp (WAXS-only): %s", sampleMod)
            yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    def collectAllPositions(debug=False):
        """Iterate through SampleList and collect USAXS/SAXS/WAXS at each position."""
        for pos_X, pos_Y, thickness, scan_title in SampleList:
            yield from collectAllThree(pos_X, pos_Y, thickness, scan_title, debug)

    def collectWAXSAllPositions(debug=False):
        """Iterate through SampleList and collect one WAXS frame at each position."""
        for pos_X, pos_Y, thickness, scan_title in SampleList:
            yield from collectWAXS(pos_X, pos_Y, thickness, scan_title, debug)

    # =========================================================================
    # EXECUTION SEQUENCE
    # =========================================================================

    isDebugMode = ptc10_debug.get()
    logger.info(
        "Starting myPTC10PlanList_AI_template | %d samples | %d temperatures | debug=%s",
        len(SampleList), len(TemperatureList), isDebugMode,
    )

    # --- Block 1: Startup ------------------------------------------------
    if not isDebugMode:
        logger.info("Running before_command_list()")
        yield from before_command_list()
    else:
        logger.info("[DEBUG] Skipping before_command_list()")

    appendToMdFile(
        f"Starting multi-position PTC10 plan | "
        f"{len(SampleList)} positions | temperatures: {TemperatureList} C"
    )

    # --- Block 2: Baseline data at ambient temperature -------------------
    t0 = time.time()
    logger.info("Collecting baseline datasets at ambient temperature (%d positions)", len(SampleList))
    appendToMdFile(f"Collecting baseline data at ambient temperature for all {len(SampleList)} positions")
    yield from collectAllPositions(isDebugMode)

    # --- Block 3: Iterate through TemperatureList ------------------------
    # For each temperature step: ramp → optional data during ramp →
    # hold → collect all positions.
    yield from bps.mv(ptc10.ramp, rate_heat / 60.0)  # set ramp rate once

    for step_idx, (temp_target, hold_time) in enumerate(zip(TemperatureList, TimeList)):
        # Use delay_hold_min if non-zero, else use TimeList value.
        effective_hold = delay_hold_min if delay_hold_min > 0 else hold_time

        logger.info(
            "Step %d/%d: heating to %s C, hold %s min",
            step_idx + 1, len(TemperatureList), temp_target, effective_hold,
        )
        appendToMdFile(
            f"Step {step_idx+1}/{len(TemperatureList)}: "
            f"heating to {temp_target} C, hold {effective_hold} min"
        )

        yield from bps.mv(ptc10.temperature.setpoint, temp_target)
        yield from setheaterOn()

        if collect_during_heat:
            # Collect WAXS at all positions while ramping to temp_target.
            while not ptc10.temperature.inposition:
                logger.debug(
                    "Collecting WAXS during heating ramp (T=%.1f C)", ptc10.position
                )
                yield from collectWAXSAllPositions(isDebugMode)
        else:
            while not ptc10.temperature.inposition:
                logger.debug("Ramping to %s C, T=%.1f C", temp_target, ptc10.position)
                yield from bps.sleep(5)

        # Reset t0 at each temperature arrival so file names show "hold time".
        t0 = time.time()
        logger.info("Arrived at %s C. Holding for %s min.", temp_target, effective_hold)
        appendToMdFile(
            f"Arrived at {temp_target} C. Collecting all positions for {effective_hold} min."
        )

        hold_until = time.time() + effective_hold * MINUTE
        while time.time() < hold_until:
            logger.debug(
                "Hold at %s C: %.1f min remaining",
                temp_target, (hold_until - time.time()) / MINUTE,
            )
            yield from collectAllPositions(isDebugMode)

        appendToMdFile(f"Hold complete at {temp_target} C.")

    # --- Block 4: Cool to temp_final -------------------------------------
    logger.info(
        "All temperature steps complete. Cooling to %s C at %s C/min.",
        temp_final, rate_cool,
    )
    appendToMdFile(
        f"All steps complete. Cooling to {temp_final} C at {rate_cool} C/min."
    )

    yield from bps.mv(ptc10.ramp, rate_cool / 60.0)
    yield from bps.mv(ptc10.temperature.setpoint, temp_final)

    if collect_during_cool:
        while not ptc10.temperature.inposition:
            logger.debug("Collecting WAXS during cooling (T=%.1f C)", ptc10.position)
            yield from collectWAXSAllPositions(isDebugMode)
    else:
        while not ptc10.temperature.inposition:
            logger.debug("Cooling to %s C, T=%.1f C", temp_final, ptc10.position)
            yield from bps.sleep(5)

    yield from setheaterOff()

    # --- Block 5: Final datasets -----------------------------------------
    t0 = time.time()
    logger.info("At %s C. Collecting final datasets at all positions.", temp_final)
    appendToMdFile(f"At {temp_final} C. Collecting final datasets for all positions.")
    yield from collectAllPositions(isDebugMode)

    appendToMdFile("Multi-position PTC10 plan complete.")
    logger.info("myPTC10PlanList_AI_template finished")

    # --- Block 6: Teardown -----------------------------------------------
    if not isDebugMode:
        logger.info("Running after_command_list()")
        yield from after_command_list()
    else:
        logger.info("[DEBUG] Skipping after_command_list()")


# ==============================================================================
# EXAMPLE: STEP-RAMP PLAN SKELETON
# ==============================================================================
# For experiments that visit a list of discrete temperatures, stabilise, then
# collect — without a separate hold loop:
#
# def myPTC10StepPlan_AI_template(pos_X, pos_Y, thickness, scan_title,
#                                  start_T, end_T, step_T, rate, stabilize_min,
#                                  md={}):
#     """Step from start_T to end_T in step_T increments, collecting at each step."""
#     # ... (inner helper functions) ...
#     isDebugMode = ptc10_debug.get()
#     if not isDebugMode:
#         yield from before_command_list()
#     t0 = time.time()
#     appendToMdFile(f"Starting step ramp: {start_T}→{end_T} C, step {step_T} C")
#
#     yield from bps.mv(ptc10.ramp, rate / 60.0)
#     yield from setheaterOn()
#
#     for target_T in range(start_T, end_T + step_T, step_T):
#         logger.info("Step: moving to %s C", target_T)
#         appendToMdFile(f"Moving to {target_T} C")
#         yield from bps.mv(ptc10.temperature.setpoint, target_T)
#         while not ptc10.temperature.inposition:
#             yield from bps.sleep(3)
#         # Optional stabilisation wait at each step:
#         yield from bps.sleep(stabilize_min * MINUTE)
#         appendToMdFile(f"Collecting at {target_T} C")
#         yield from collectAllThree(isDebugMode)
#
#     appendToMdFile(f"Step ramp complete. Cooling to 40 C.")
#     yield from bps.mv(ptc10.ramp, 50 / 60.0)
#     yield from bps.mv(ptc10.temperature.setpoint, 40)
#     while not ptc10.temperature.inposition:
#         yield from bps.sleep(5)
#     yield from setheaterOff()
#     yield from collectAllThree(isDebugMode)
#     appendToMdFile("Plan complete.")
#     if not isDebugMode:
#         yield from after_command_list()
