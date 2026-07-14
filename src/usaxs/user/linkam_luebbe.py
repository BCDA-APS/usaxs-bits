"""
Linkam 600 plan for user Luebbe — cool to -40 °C then step-heat to Tmax.

Sequence:
    1. Collect USAXS/SAXS/WAXS at current (room) temperature — 1×.
    2. Cool to -40 °C at 100 °C/min; wait for arrival.
    3. Reset t0 at -40 °C; collect 2×.
    4. Step-heat by StepInTemperature at 100 °C/min up to Tmax:
           a. Heat to next step (or Tmax if overshoot) at 100 °C/min; wait.
           b. Collect 2×.
       Repeat until Tmax is reached.
    5. Cool to 40 °C at 100 °C/min; wait for arrival.
    6. Collect 1× at 40 °C.
    7. Turn off Linkam heater (STARTHEAT → Off).
    8. Teardown (after_command_list).

Parameters:
    sample_name       : str   — base scan title (temperature and time are appended)
    thickness         : float — sample thickness in mm
    Tmax              : float — maximum temperature to reach in °C
    StepInTemperature : float — temperature increment per heating step in °C
    pos_X, pos_Y are fixed at 0 for all samples.

Sample name format:
    {sample_name}_{linkam_temp:.0f}C_{elapsed:.0f}min
    Elapsed time is measured from when -40 °C is first reached.

Reload:
    %run -im usaxs.user.linkam_luebbe

Debug mode (no instrument motion; full thermal cycle runs normally):
    linkam_debug.put(True)
    linkam_debug.put(False)

Usage:
    RE(linkam_luebbe("MySample", 1.0, 200.0, 20.0))

Change log:
    * JIL, 2026-07-10 : Created for user Luebbe (AI-assisted)
"""

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

import time

from bluesky import plan_stubs as bps
from apsbits.core.instrument_init import oregistry
from ophyd import Signal

from usaxs.plans.plans_user_facing import saxsExp, waxsExp
from usaxs.plans.plans_usaxs import USAXSscan
from usaxs.plans.command_list import after_command_list, before_command_list, sync_order_numbers
from usaxs.utils.obsidian import appendToMdFile, recordFunctionRun

logger = logging.getLogger(__name__)
logger.info(__file__)

linkam_tc1 = oregistry["linkam_tc1"]

SECOND = 1
MINUTE = 60 * SECOND
HOUR = 60 * MINUTE

RATE = 100.0        # °C/min — used for all heating and cooling steps
TEMP_COLD = -40.0   # °C — starting temperature after initial RT collection
TEMP_FINAL = 40.0   # °C — final temperature before shutting off heater

# Debug / dry-run flag.  Set at the IPython prompt before calling RE():
#   linkam_debug.put(True)   → debug mode (no instrument motion, thermal cycle runs)
#   linkam_debug.put(False)  → normal operation (default)
linkam_debug = Signal(name="linkam_debug", value=False)


def linkam_luebbe(sample_name, thickness, Tmax, StepInTemperature, md={}):
    """
    Linkam cool-then-step-heat plan for user Luebbe.

    Sequence:
        1. Startup (before_command_list).
        2. Collect 1× at current (room) temperature.
        3. Cool to -40 °C at 100 °C/min; collect 2× (t0 reset on arrival).
        4. Step-heat by StepInTemperature at 100 °C/min up to Tmax:
               heat → wait → collect 2×  (last step target capped at Tmax).
        5. Cool to 40 °C at 100 °C/min; collect 1×.
        6. Turn off heater.
        7. Teardown (after_command_list).

    Parameters
    ----------
    sample_name : str
        Base name prepended to every scan title.
    thickness : float
        Sample thickness in mm.
    Tmax : float
        Maximum temperature to reach in °C.
    StepInTemperature : float
        Temperature increment for each heating step in °C.
    md : dict, optional
        Extra metadata attached to every scan.

    Examples
    --------
    RE(linkam_luebbe("MySample", 1.0, 200.0, 20.0))
    """

    # =========================================================================
    # INNER HELPERS
    # =========================================================================

    pos_X = 0.0
    pos_Y = 0.0
    linkam = linkam_tc1

    def setSampleName():
        """Return scan name encoding Linkam temperature and elapsed minutes since t0."""
        return (
            f"{sample_name}"
            f"_{linkam.temperature.position:.0f}C"
            f"_{(time.time() - t0) / MINUTE:.0f}min"
        )

    def collectAllThree(debug=False):
        """Collect USAXS → SAXS → WAXS.  In debug mode: print + sleep 20 s."""
        sampleMod = setSampleName()
        if debug:
            print(f"[DEBUG] collectAllThree: {sampleMod}")
            yield from bps.sleep(20)
        else:
            yield from sync_order_numbers()
            sampleMod = setSampleName()
            md["title"] = sampleMod
            logger.info("USAXSscan: %s", sampleMod)
            yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = setSampleName()
            md["title"] = sampleMod
            logger.info("saxsExp:   %s", sampleMod)
            yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = setSampleName()
            md["title"] = sampleMod
            logger.info("waxsExp:   %s", sampleMod)
            yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    def change_rate_and_temperature(rate, t, wait=True):
        """Set ramp rate (°C/min) and move Linkam to t °C."""
        logger.debug(
            "change_rate_and_temperature: %.0f C/min → %.0f C (wait=%s)", rate, t, wait
        )
        yield from bps.mv(linkam.ramprate.setpoint, rate)
        yield from linkam.set_target(t, wait=wait)

    # =========================================================================
    # EXECUTION SEQUENCE
    # =========================================================================

    isDebugMode = linkam_debug.get()
    recordFunctionRun()
    logger.info(
        "Starting linkam_luebbe | sample=%s | thickness=%.2f mm"
        " | Tmax=%.0f C | step=%.0f C | debug=%s",
        sample_name, thickness, Tmax, StepInTemperature, isDebugMode,
    )

    # --- Block 1: Startup ---------------------------------------------------
    if not isDebugMode:
        yield from before_command_list()
    else:
        logger.info("[DEBUG] Skipping before_command_list()")

    appendToMdFile(
        f"## linkam_luebbe: {sample_name}\n"
        f"- thickness={thickness} mm, pos=(0, 0)\n"
        f"- Cool to {TEMP_COLD:.0f} °C at {RATE:.0f} °C/min\n"
        f"- Step-heat by {StepInTemperature:.0f} °C increments at {RATE:.0f} °C/min up to {Tmax:.0f} °C\n"
        f"- Cool to {TEMP_FINAL:.0f} °C, collect 1×, then heater off"
    )

    # --- Block 2: Room-temperature baseline ---------------------------------
    # Collect at whatever temperature the Linkam is currently at.
    # Do NOT change the temperature — just record a starting dataset.
    t0 = time.time()
    logger.info(
        "Block 2: RT baseline at %.1f °C — collecting 1×",
        linkam.temperature.position,
    )
    appendToMdFile(
        f"RT baseline at {linkam.temperature.position:.0f} °C — collecting 1×"
    )
    yield from collectAllThree(isDebugMode)

    # --- Block 3: Cool to -40 °C -------------------------------------------
    logger.info(
        "Block 3: cooling to %.0f °C at %.0f °C/min",
        TEMP_COLD, RATE,
    )
    appendToMdFile(f"Cooling to {TEMP_COLD:.0f} °C at {RATE:.0f} °C/min")
    yield from change_rate_and_temperature(RATE, TEMP_COLD, wait=True)

    # t0 reset — elapsed time in names now counts from -40 °C arrival (time = 0).
    t0 = time.time()
    logger.info(
        "Arrived at %.0f °C — collecting 2× (t0 reset)", TEMP_COLD
    )
    appendToMdFile(f"Arrived at {TEMP_COLD:.0f} °C — collecting 2× (t0 reset)")

    for i in range(2):
        logger.info(
            "Cold dataset %d/2 | T=%.1f °C", i + 1, linkam.temperature.position
        )
        yield from collectAllThree(isDebugMode)

    appendToMdFile(f"Cold baseline complete (2 datasets at {TEMP_COLD:.0f} °C)")

    # --- Block 4: Step-heat from TEMP_COLD to Tmax --------------------------
    # Each iteration: heat by StepInTemperature (or to Tmax if near the end),
    # wait for arrival, then collect 2×.
    current_temp = TEMP_COLD
    step_number = 0

    while current_temp < Tmax:
        next_temp = min(current_temp + StepInTemperature, Tmax)
        step_number += 1

        logger.info(
            "Step %d: heating %.0f → %.0f °C at %.0f °C/min",
            step_number, current_temp, next_temp, RATE,
        )
        appendToMdFile(
            f"Step {step_number}: heating {current_temp:.0f} → {next_temp:.0f} °C"
            f" at {RATE:.0f} °C/min"
        )
        yield from change_rate_and_temperature(RATE, next_temp, wait=True)

        logger.info(
            "Step %d: arrived at %.0f °C — collecting 2×",
            step_number, linkam.temperature.position,
        )
        appendToMdFile(
            f"Step {step_number}: at {linkam.temperature.position:.0f} °C — collecting 2×"
        )

        for j in range(2):
            logger.info(
                "Step %d dataset %d/2 | T=%.1f °C",
                step_number, j + 1, linkam.temperature.position,
            )
            yield from collectAllThree(isDebugMode)

        current_temp = next_temp

    logger.info(
        "Reached Tmax=%.0f °C after %d step(s).", Tmax, step_number
    )
    appendToMdFile(f"Tmax={Tmax:.0f} °C reached after {step_number} step(s)")

    # --- Block 5: Cool to 40 °C, collect 1× --------------------------------
    logger.info(
        "Block 5: cooling to %.0f °C at %.0f °C/min",
        TEMP_FINAL, RATE,
    )
    appendToMdFile(f"Cooling to {TEMP_FINAL:.0f} °C at {RATE:.0f} °C/min")
    yield from change_rate_and_temperature(RATE, TEMP_FINAL, wait=True)

    t0 = time.time()
    logger.info(
        "Arrived at %.0f °C — collecting 1×", TEMP_FINAL
    )
    appendToMdFile(f"Arrived at {TEMP_FINAL:.0f} °C — collecting 1×")
    yield from collectAllThree(isDebugMode)

    # --- Block 6: Turn off Linkam heater ------------------------------------
    logger.info("Turning off Linkam heater (STARTHEAT → Off)")
    appendToMdFile("Turning off Linkam heater")
    yield from bps.mv(linkam.temperature.actuate, "Off")

    # --- Block 7: Teardown --------------------------------------------------
    if not isDebugMode:
        yield from after_command_list()
    else:
        logger.info("[DEBUG] Skipping after_command_list()")

    appendToMdFile(f"linkam_luebbe complete: {sample_name}")
    logger.info("Plan complete: %s", sample_name)
