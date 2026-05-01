"""
PTC10 simple heat-and-hold plan for user Patra.

Sequence
--------
    1. Collect USAXS/SAXS/WAXS at room temperature (baseline).
    2. Stepwise heating: increase PTC10 by *temp_step* °C at a time at *rate_heat* °C/min.
       At each intermediate step: wait for arrival, wait *step_wait* min, collect data once.
       The final step goes to *temp_target* (whatever remains in the last cycle).
    3. Hold at *temp_target*: collect USAXS/SAXS/WAXS repeatedly for *hold_time* minutes.
    4. Turn heater off; set setpoint to 100 °C.
    5. Wait (passive cooling) until PTC10 reads ≤ 102 °C.
    6. Collect final USAXS/SAXS/WAXS dataset at ~100 °C.
    7. Teardown (after_command_list).

==============================================================================
USAGE
==============================================================================

Load:
    %run -im usaxs.user.ptc10_patra

Debug mode (no instrument motion, real PTC10 heating):
    ptc10_debug.put(True)
    RE(ptc10Patra("MySample", 25.0, 10.0, 1.0, 200.0, 10.0, 60.0))

Real run:
    ptc10_debug.put(False)
    RE(ptc10Patra("MySample", 25.0, 10.0, 1.0, 200.0, 10.0, 60.0))

Stop:
    RE.abort()

    NOTE: after_command_list() does NOT run automatically on abort.
    Run it manually once the plan has stopped:
        RE(after_command_list())

==============================================================================
PARAMETERS
==============================================================================

    sample_name : str   — base name prepended to every scan file name
    sx          : float — horizontal stage position in mm
    sy          : float — vertical stage position in mm
    thickness   : float — sample thickness in mm
    temp_target : float — PTC10 final target temperature in °C
    rate_heat   : float — ramp rate in °C/min (applied at every step)
    hold_time   : float — how long to hold at temp_target in minutes
    temp_step   : float — temperature increment per step in °C (default 50)
    step_wait   : float — minutes to wait at each step before collecting (default 3)
    md          : dict  — extra metadata (optional)

==============================================================================
SAMPLE NAME FORMAT
==============================================================================

    {sample_name}_{ptc_temp:.0f}C_{elapsed:.0f}min

    PTC     = PTC10 controller temperature readback
    elapsed = minutes since heater was switched on

==============================================================================
CHANGE LOG
==============================================================================

    * JIL, 2026-04-03 : Created for user Patra
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
from usaxs.utils.obsidian import appendToMdFile, recordFunctionRun

# PTC10 temperature controller.
ptc10 = oregistry["ptc10"]

# Convenient time-unit constants.
SECOND = 1
MINUTE = 60 * SECOND
HOUR = 60 * MINUTE

# Debug / dry-run flag.  Set at the IPython prompt before calling RE():
#   ptc10_debug.put(True)   → debug mode (no instrument motion, 20 s sleep per collection)
#   ptc10_debug.put(False)  → normal operation (default)
ptc10_debug = Signal(name="ptc10_debug", value=False)

# Temperature at which the final dataset is collected after cooling.
COOL_TARGET = 100.0  # °C
COOL_TOLERANCE = 2.0  # °C — arrival band


# ==============================================================================
# HEATER UTILITIES
# ==============================================================================


def setheaterOff():
    """Power down the PTC10 heater and stop the PID control loop."""
    yield from bps.mv(
        ptc10.enable,
        "Off",
        ptc10.pid.pidmode,
        "Off",
    )


def setheaterOn():
    """
    Power up the PTC10 heater and start the PID control loop.

    Always call AFTER setting ptc10.ramp and ptc10.temperature.setpoint.
    """
    yield from bps.mv(
        ptc10.enable,
        "On",
        ptc10.pid.pidmode,
        "On",
    )


# ==============================================================================
# MAIN PLAN
# ==============================================================================


def ptc10Patra(
    sample_name,
    sx,
    sy,
    thickness,
    temp_target,
    rate_heat,
    hold_time,
    temp_step=50.0,
    step_wait=3.0,
    waxs_only=False,
    md={},
):
    """
    Collect RT baseline, step-heat to temp_target, hold and collect, then cool and collect final.

    Parameters
    ----------
    sample_name : str
        Base name for all scans.
    sx : float
        Horizontal stage position in mm.
    sy : float
        Vertical stage position in mm.
    thickness : float
        Sample thickness in mm.
    temp_target : float
        PTC10 final target temperature in °C.
    rate_heat : float
        Ramp rate applied at every heating step in °C/min.
    hold_time : float
        How long to collect data continuously at temp_target in minutes.
    temp_step : float, optional
        Temperature increment per heating step in °C (default 50).
    step_wait : float, optional
        Minutes to wait at each intermediate step before collecting (default 3).
    waxs_only : bool, optional
        When True, collect only WAXS at every point (skips USAXS and SAXS).
        Useful for calibration runs (default False).
    md : dict, optional
        Extra metadata attached to every scan.

    Load:
        %run -im usaxs.user.ptc10_patra

    Debug:
        ptc10_debug.put(True)
        RE(ptc10Patra("MySample", 25.0, 10.0, 1.0, 200.0, 10.0, 60.0))

    Real run:
        ptc10_debug.put(False)
        RE(ptc10Patra("MySample", 25.0, 10.0, 1.0, 200.0, 10.0, 60.0))
    """

    # =========================================================================
    # INNER HELPERS
    # =========================================================================

    def getSampleName():
        """Build scan name encoding PTC10 temp and elapsed time."""
        ptc_temp = ptc10.position
        elapsed = (time.time() - t0) / MINUTE
        return f"{sample_name}_{ptc_temp:.0f}C_{elapsed:.0f}min"

    def collectData(debug=False):
        """Collect USAXS → SAXS → WAXS at (sx, sy), or only WAXS if waxs_only=True."""
        if debug:
            sampleMod = getSampleName()
            mode = "WAXS only" if waxs_only else "USAXS/SAXS/WAXS"
            print(f"[DEBUG] collectData ({mode}): {sampleMod}  pos=({sx}, {sy})")
            yield from bps.sleep(20)
        else:
            yield from sync_order_numbers()
            if not waxs_only:
                sampleMod = getSampleName()
                md["title"] = sampleMod
                logger.info("USAXSscan: %s", sampleMod)
                yield from USAXSscan(sx, sy, thickness, sampleMod, md={})
                sampleMod = getSampleName()
                md["title"] = sampleMod
                logger.info("saxsExp:   %s", sampleMod)
                yield from saxsExp(sx, sy, thickness, sampleMod, md={})
            sampleMod = getSampleName()
            md["title"] = sampleMod
            logger.info("waxsExp:   %s", sampleMod)
            yield from waxsExp(sx, sy, thickness, sampleMod, md={})

    # =========================================================================
    # EXECUTION SEQUENCE
    # =========================================================================

    t0 = time.time()
    isDebugMode = ptc10_debug.get()
    recordFunctionRun()
    logger.info(
        "Starting ptc10Patra | sample=%s | pos=(%.2f, %.2f) | thickness=%.2f mm | "
        "target=%.0f C @ %.0f C/min | step=%.0f C | step_wait=%.0f min | hold=%.0f min | debug=%s",
        sample_name,
        sx,
        sy,
        thickness,
        temp_target,
        rate_heat,
        temp_step,
        step_wait,
        hold_time,
        isDebugMode,
    )

    # --- Block 1: Startup ---------------------------------------------------
    if not isDebugMode:
        yield from before_command_list()
    else:
        logger.info("[DEBUG] Skipping before_command_list()")

    appendToMdFile(
        f"## PTC10 Patra plan: {sample_name}\n"
        f"- **Position:** sx={sx} mm, sy={sy} mm, thickness={thickness} mm\n"
        f"- **Target temperature:** {temp_target} °C @ {rate_heat} °C/min\n"
        f"- **Step size / wait:** {temp_step} °C / {step_wait} min\n"
        f"- **Hold time:** {hold_time} min\n"
        f"- **Cool-down target:** {COOL_TARGET} °C (passive, heater off)\n"
        f"- **Name format:** {sample_name}_<PTC>C_<min>min"
    )

    # --- Block 2: Baseline at room temperature ------------------------------
    logger.info("Collecting baseline at RT | PTC10=%.1f C", ptc10.position)
    appendToMdFile(f"Baseline at RT: PTC10={ptc10.position:.1f} °C")
    yield from collectData(isDebugMode)

    # --- Block 3: Stepwise heating to temp_target ---------------------------
    ptc10.tolerance.put(COOL_TOLERANCE)

    # Build step list: RT+step, RT+2*step, …, temp_target (always the last entry).
    start_temp = ptc10.position
    step_temps = []
    t = start_temp + temp_step
    while t < temp_target:
        step_temps.append(round(t, 1))
        t += temp_step
    step_temps.append(temp_target)

    logger.info(
        "Stepwise heating: %d steps to %.0f C | +%.0f C/step | %.0f min wait | %.0f C/min",
        len(step_temps),
        temp_target,
        temp_step,
        step_wait,
        rate_heat,
    )
    appendToMdFile(
        f"Stepwise heating: {len(step_temps)} steps → {temp_target} °C "
        f"(+{temp_step:.0f} °C/step, {step_wait:.0f} min wait, {rate_heat:.0f} °C/min)"
    )

    # Set ramp rate and turn heater on for the first step.
    yield from bps.mv(ptc10.ramp, rate_heat / 60.0)  # °C/min → °C/s
    yield from bps.mv(ptc10.temperature.setpoint, step_temps[0])
    yield from setheaterOn()
    t0 = time.time()  # reset: elapsed time counted from heater-on

    for i, step_temp in enumerate(step_temps):
        if i > 0:
            yield from bps.mv(ptc10.temperature.setpoint, step_temp)

        logger.info("Step %d/%d: heating to %.0f C", i + 1, len(step_temps), step_temp)
        appendToMdFile(f"Step {i + 1}/{len(step_temps)}: heating to {step_temp:.0f} °C")

        while not ptc10.temperature.inposition:
            logger.debug(
                "Step %d: PTC10=%.1f C → %.0f C", i + 1, ptc10.position, step_temp
            )
            yield from bps.sleep(15)

        logger.info(
            "Step %d: at %.0f C — waiting %.0f min before collecting",
            i + 1,
            step_temp,
            step_wait,
        )
        yield from bps.sleep(step_wait * MINUTE)

        logger.info("Step %d: collecting data at PTC10=%.1f C", i + 1, ptc10.position)
        yield from collectData(isDebugMode)
        appendToMdFile(f"Step {i + 1}: collected at PTC10={ptc10.position:.1f} °C")

    logger.info("All steps complete — at %.0f C", temp_target)

    # --- Block 4: Hold at temp_target and collect ---------------------------
    hold_end = time.time() + hold_time * MINUTE
    sweep = 0
    logger.info(
        "Holding at %.0f C for %.0f min — collecting data", temp_target, hold_time
    )
    appendToMdFile(f"Hold at {temp_target} °C for {hold_time} min — collecting data")

    while time.time() < hold_end:
        sweep += 1
        remaining = (hold_end - time.time()) / MINUTE
        logger.info(
            "Hold sweep %d | PTC10=%.1f C | %.1f min remaining",
            sweep,
            ptc10.position,
            remaining,
        )
        yield from collectData(isDebugMode)

    logger.info("Hold complete after %d sweep(s)", sweep)
    appendToMdFile(f"Hold complete after {sweep} sweep(s)")

    # --- Block 5: Turn heater off and cool to COOL_TARGET -------------------
    logger.info("Turning heater off — cooling to %.0f C (passive)", COOL_TARGET)
    appendToMdFile(f"Heater off — cooling passively to {COOL_TARGET} °C")
    yield from setheaterOff()
    yield from bps.mv(ptc10.temperature.setpoint, COOL_TARGET)

    while ptc10.position > COOL_TARGET + COOL_TOLERANCE:
        logger.debug("Cooling: PTC10=%.1f C", ptc10.position)
        yield from bps.sleep(30)

    logger.info("Cooled to %.1f C — collecting final dataset", ptc10.position)
    appendToMdFile(f"Cooled to {COOL_TARGET} °C: PTC10={ptc10.position:.1f} °C")

    # --- Block 6: Final dataset at ~COOL_TARGET -----------------------------
    yield from collectData(isDebugMode)

    logger.info("Plan complete: %s", sample_name)
    appendToMdFile(f"Plan complete: {sample_name}")

    # --- Block 7: Teardown --------------------------------------------------
    if not isDebugMode:
        yield from after_command_list()
    else:
        logger.info("[DEBUG] Skipping after_command_list()")
