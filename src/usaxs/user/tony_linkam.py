"""
Linkam plan for user Tony — melt-then-step-cool/heat experiment.

Sequence
--------
    1. Collect USAXS/SAXS/WAXS at RT (~40 °C baseline).
    2. Heat to melting temperature *Tm* at 30 °C/min; wait for arrival.
    3. Reset elapsed-time counter (t0) at Tm.
    4. Collect USAXS/SAXS/WAXS 5× at Tm.
    5. For each temperature in *temp_list* (in order):
           a. Change Linkam to that temperature at 10 °C/min; wait for arrival.
           b. Collect USAXS/SAXS/WAXS 3×.
    6. Teardown (after_command_list).

==============================================================================
USAGE
==============================================================================

Edit *temp_list* and the call arguments below, then:

Load:
    %run -im usaxs.user.tony_linkam

Debug mode (no instrument motion, full thermal cycle runs normally):
    linkam_debug.put(True)
    RE(tonyLinkam(0.0, 0.0, 1.0, "MySample", 180.0, [160, 140, 120, 100, 80]))

Real run:
    linkam_debug.put(False)
    RE(tonyLinkam(0.0, 0.0, 1.0, "MySample", 180.0, [160, 140, 120, 100, 80]))

Stop:
    RE.abort()

    NOTE: after_command_list() does NOT run automatically on abort.
    Run it manually once the plan has stopped:
        RE(after_command_list())

==============================================================================
PARAMETERS
==============================================================================

    pos_X     : float      — horizontal stage position in mm
    pos_Y     : float      — vertical stage position in mm
    thickness : float      — sample thickness in mm
    scan_title: str        — base name prepended to every scan file name
    Tm        : float      — melting temperature in °C (heat at 30 °C/min)
    temp_list : list[float]— temperatures to visit after Tm, in order (°C)
                             each step uses 10 °C/min; can heat or cool
    md        : dict       — extra metadata (optional)

==============================================================================
SAMPLE NAME FORMAT
==============================================================================

    {scan_title}_{linkam_temp:.0f}C_{elapsed:.0f}min

    linkam_temp = Linkam temperature readback at scan time
    elapsed     = minutes since t0 was last reset
                  (reset at experiment start, then again when Tm is reached)

==============================================================================
CHANGE LOG
==============================================================================

    * JIL, 2026-04-03 : Created for user Tony
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

# Linkam TC-1 device registered in the ophyd device registry.
linkam_tc1 = oregistry["linkam_tc1"]

# Convenient time-unit constants.
SECOND = 1
MINUTE = 60 * SECOND
HOUR = 60 * MINUTE

# Debug / dry-run flag.  Set at the IPython prompt before calling RE():
#   linkam_debug.put(True)   → debug mode (no instrument motion, thermal cycle runs)
#   linkam_debug.put(False)  → normal operation (default)
linkam_debug = Signal(name="linkam_debug", value=False)

# Fixed ramp rates for this plan.
RATE_TO_TM = 30.0  # °C/min — heating rate to melting temperature
RATE_STEPS = 10.0  # °C/min — rate between each step in temp_list
RATE_BASELINE = 150.0  # °C/min — fast move to initial 40 °C baseline

# Number of datasets to collect at each stage.
N_AT_TM = 5  # datasets collected at Tm
N_AT_STEPS = 3  # datasets collected at each temp_list entry


# ==============================================================================
# MAIN PLAN
# ==============================================================================


def tonyLinkam(pos_X, pos_Y, thickness, scan_title, Tm, temp_list, md={}):
    """
    RT baseline → heat to Tm (5× collect) → step through temp_list (3× each).

    Parameters
    ----------
    pos_X, pos_Y : float
        Sample stage X/Y position in mm.
    thickness : float
        Sample thickness in mm.
    scan_title : str
        Base name for all scans.
    Tm : float
        Melting temperature in °C.  Heated to at 30 °C/min.
    temp_list : list of float
        Temperatures to visit after Tm, in the order given.  Each transition
        uses 10 °C/min regardless of heating or cooling direction.
    md : dict, optional
        Extra metadata attached to every scan.

    Load:
        %run -im usaxs.user.tony_linkam

    Debug:
        linkam_debug.put(True)
        RE(tonyLinkam(0.0, 0.0, 1.0, "MySample", 180.0, [160, 140, 120, 80]))

    Real run:
        linkam_debug.put(False)
        RE(tonyLinkam(0.0, 0.0, 1.0, "MySample", 180.0, [160, 140, 120, 80]))
    """

    # =========================================================================
    # INNER HELPERS  (copied verbatim pattern from linkam_template_AI.py)
    # =========================================================================

    def setSampleName():
        """Return scan name encoding Linkam temp and elapsed minutes since t0."""
        return (
            f"{scan_title}"
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

    linkam = linkam_tc1
    isDebugMode = linkam_debug.get()
    recordFunctionRun()
    logger.info(
        "Starting tonyLinkam | sample=%s | Tm=%.0f C | %d temp steps | debug=%s",
        scan_title,
        Tm,
        len(temp_list),
        isDebugMode,
    )

    # --- Block 1: Startup ---------------------------------------------------
    if not isDebugMode:
        yield from before_command_list()
    else:
        logger.info("[DEBUG] Skipping before_command_list()")

    appendToMdFile(
        f"## Tony Linkam plan: {scan_title}\n"
        f"- **Tm:** {Tm} °C @ {RATE_TO_TM} °C/min\n"
        f"- **Datasets at Tm:** {N_AT_TM}×\n"
        f"- **Step list ({len(temp_list)} steps):** {temp_list}\n"
        f"- **Step rate:** {RATE_STEPS} °C/min, {N_AT_STEPS}× per step\n"
        f"- **Name format:** {scan_title}_<T>C_<min>min  (t0 reset at Tm)"
    )

    # --- Block 2: Baseline at RT (~40 °C) -----------------------------------
    logger.info("Moving to 30 C baseline at %.0f C/min", RATE_BASELINE)
    yield from change_rate_and_temperature(RATE_BASELINE, 30, wait=True)

    t0 = time.time()  # experiment start
    logger.info("At 30 C. Collecting RT baseline dataset.")
    appendToMdFile(
        f"RT baseline at {linkam.temperature.position:.0f} °C — collecting 1×"
    )
    yield from collectAllThree(isDebugMode)

    # --- Block 3: Heat to Tm ------------------------------------------------
    logger.info("Heating to Tm=%.0f C at %.0f C/min", Tm, RATE_TO_TM)
    appendToMdFile(f"Heating to Tm={Tm:.0f} °C at {RATE_TO_TM:.0f} °C/min")
    yield from change_rate_and_temperature(RATE_TO_TM, Tm, wait=True)

    # Reset t0 at Tm — elapsed time in names now means "time since melt".
    t0 = time.time()
    logger.info("Arrived at Tm=%.0f C. Collecting %d× datasets.", Tm, N_AT_TM)
    appendToMdFile(f"Arrived at Tm={Tm:.0f} °C — collecting {N_AT_TM}× (t0 reset)")

    # --- Block 4: Collect N_AT_TM datasets at Tm ----------------------------
    for i in range(N_AT_TM):
        logger.info(
            "Tm dataset %d/%d | T=%.1f C", i + 1, N_AT_TM, linkam.temperature.position
        )
        yield from collectAllThree(isDebugMode)

    appendToMdFile(f"Tm hold complete ({N_AT_TM} datasets)")

    # --- Block 5: Step through temp_list ------------------------------------
    for step_i, step_temp in enumerate(temp_list):
        logger.info(
            "Step %d/%d: moving to %.0f C at %.0f C/min",
            step_i + 1,
            len(temp_list),
            step_temp,
            RATE_STEPS,
        )
        appendToMdFile(
            f"Step {step_i + 1}/{len(temp_list)}: "
            f"{'heating' if step_temp > linkam.temperature.position else 'cooling'} "
            f"to {step_temp:.0f} °C at {RATE_STEPS:.0f} °C/min"
        )
        yield from change_rate_and_temperature(RATE_STEPS, step_temp, wait=True)

        logger.info(
            "Step %d/%d: at %.1f C — collecting %d× datasets",
            step_i + 1,
            len(temp_list),
            linkam.temperature.position,
            N_AT_STEPS,
        )
        appendToMdFile(
            f"Step {step_i + 1}: at {linkam.temperature.position:.0f} °C — collecting {N_AT_STEPS}×"
        )

        for j in range(N_AT_STEPS):
            logger.info(
                "Step %d dataset %d/%d | T=%.1f C",
                step_i + 1,
                j + 1,
                N_AT_STEPS,
                linkam.temperature.position,
            )
            yield from collectAllThree(isDebugMode)

    logger.info("All %d steps complete.", len(temp_list))
    appendToMdFile(f"All steps complete. Plan ending.")

    # --- Block 6: Teardown --------------------------------------------------
    logger.info("Plan complete: %s", scan_title)
    appendToMdFile(f"Plan complete: {scan_title}")

    if not isDebugMode:
        yield from after_command_list()
    else:
        logger.info("[DEBUG] Skipping after_command_list()")
