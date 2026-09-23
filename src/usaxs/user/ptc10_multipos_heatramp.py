"""
PTC10 multi-position heat-ramp plan with secondary thermocouple.

One sample is measured at multiple vertical positions sequentially.
The loop over all positions repeats continuously while the PTC10 heats
to its target temperature.  A secondary thermocouple (usxLAX:adam2:tc1.VAL)
reports the actual sample temperature; that value is embedded in every
scan name so the recorded temperature reflects what the sample experiences.

==============================================================================
USAGE
==============================================================================

Edit SampleList below to set the vertical stage positions (Y values) and
names for each measurement spot on the sample.  All spots share the same
X position and thickness.

Load:
    %run -im usaxs.user.ptc10_multipos_heatramp

Debug mode (no instrument motion, real PTC10 heating):
    ptc10_debug.put(True)
    RE(ptc10MultiposaHeatRamp("MySample", 1.3, 200, 10))

Real run:
    ptc10_debug.put(False)
    RE(ptc10MultiposaHeatRamp("MySample", 1.3, 200, 10))

==============================================================================
PARAMETERS
==============================================================================

    scan_title   : str   — base name prepended to every scan file name
    thickness    : float — sample thickness in mm
    temp_target  : float — PTC10 target temperature in °C
    rate_heat    : float — ramp rate in °C/min  (stored as °C/s internally)
    pos_X        : float — horizontal stage position in mm (same for all spots)
    temp_final   : float — cool-down target in °C (default 40 °C)
    rate_cool    : float — cooling ramp rate in °C/min (default 50 °C/min)
    md           : dict  — extra metadata

==============================================================================
SAMPLE NAME FORMAT
==============================================================================

    {spot_name}_TC{secondary_temp:.1f}C_PTC{ptc10_temp:.0f}C_{elapsed:.0f}min

    TC  = secondary thermocouple temperature (usxLAX:adam2:tc1.VAL)
    PTC = PTC10 controller temperature readback
    min = minutes elapsed since plan start (t0)

==============================================================================
CHANGE LOG
==============================================================================

    * JIL, 2026-03-31 : Created from usaxs/plan_templates/ptc10_template.py
"""

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

import time

from bluesky import plan_stubs as bps
from apsbits.core.instrument_init import oregistry
from ophyd import EpicsSignalRO, Signal

from usaxs.plans.plans_user_facing import saxsExp
from usaxs.plans.plans_user_facing import waxsExp
from usaxs.plans.plans_usaxs import USAXSscan
from usaxs.plans.command_list import after_command_list, sync_order_numbers
from usaxs.plans.command_list import before_command_list
from usaxs.utils.obsidian import appendToMdFile, recordFunctionRun

# PTC10 temperature controller.
ptc10 = oregistry["ptc10"]

# Secondary thermocouple — measures actual sample temperature.
tc_sample = EpicsSignalRO("usxLAX:adam2:tc1.VAL", name="tc_sample")

# Convenient time constants.
SECOND = 1
MINUTE = 60 * SECOND
HOUR = 60 * MINUTE

# Debug / dry-run flag.  Set before calling RE():
#   ptc10_debug.put(True)   → debug mode (no instrument motion)
#   ptc10_debug.put(False)  → normal operation
ptc10_debug = Signal(name="ptc10_debug", value=False)

# ==============================================================================
# SAMPLE LIST — edit before each run, then reload with %run -im ...
#
# One sample measured at multiple vertical positions.
# Format: [pos_X_mm, pos_Y_mm, thickness_mm, "SpotName"]
# All spots share the same X; only Y changes between positions.
# ==============================================================================

SampleList = [
    [25.0, 15.0, 4, "WaterBlank"],
    [35.0, 16.0, 4, "Sa5g"],
    [35.0, 10.0, 4, "Sa5a"],
    [35.0, 14.0, 4, "Sa5e"],
    [35.0, 11.0, 4, "Sa5b"],
    [35.0, 17.0, 4, "Sa5h"],
    [35.0, 12.0, 4, "Sa5c"],
    [35.0, 15.0, 4, "Sa5f"],
    [35.0, 13.0, 4, "Sa5d"],
]


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


def ptc10MultiposaHeatRamp(
    scan_title,
    thickness,
    temp_target,
    rate_heat,
    pos_X=0.0,
    temp_final=40,
    rate_cool=50,
    md={},
):
    """
    Heat to temp_target while cycling through all vertical positions in SampleList.

    Sequence:
        1. Startup (before_command_list).
        2. Baseline: collect USAXS/SAXS/WAXS at all positions at ambient T.
        3. Start PTC10 ramp to temp_target.
        4. LOOP: scan all positions repeatedly until PTC10 reaches temp_target.
        5. Cool to temp_final at rate_cool °C/min (silent).
        6. Final dataset: collect USAXS/SAXS/WAXS at all positions at temp_final.
        7. Teardown (after_command_list).

    Every scan name encodes the secondary thermocouple temperature, the PTC10
    readback, and elapsed time so data can be time-resolved post-experiment.

    Parameters
    ----------
    scan_title : str
        Base name prepended to every scan file name.
    thickness : float
        Sample thickness in mm (same for all positions).
    temp_target : float
        PTC10 target (final) temperature in °C.
    rate_heat : float
        Ramp rate to temp_target in °C/min.
    pos_X : float, optional
        Horizontal stage position in mm shared by all SampleList entries
        (default 0.0 — override SampleList X values if needed).
        Set to None to use each entry's own X from SampleList.
    temp_final : float, optional
        Cool-down target in °C (default 40 °C).
    rate_cool : float, optional
        Cooling ramp rate in °C/min (default 50 °C/min).
    md : dict, optional
        Extra metadata attached to every scan.

    Load:
        %run -im usaxs.user.ptc10_multipos_heatramp

    Debug:
        ptc10_debug.put(True)
        RE(ptc10MultiposaHeatRamp("MySample", 1.3, 200, 10))

    Real run:
        ptc10_debug.put(False)
        RE(ptc10MultiposaHeatRamp("MySample", 1.3, 200, 10))
    """

    # =========================================================================
    # INNER HELPERS
    # =========================================================================

    def getSampleName(spot_title):
        """
        Build a scan name that encodes secondary TC temp, PTC10 temp, and elapsed time.

        Format: {spot_title}_TC{secondary:.1f}C_PTC{ptc10:.0f}C_{elapsed:.0f}min
        """
        tc_temp = tc_sample.get()
        ptc_temp = ptc10.position
        elapsed = (time.time() - t0) / MINUTE
        return f"{spot_title}_TC{tc_temp:.1f}C_PTC{ptc_temp:.0f}C_{elapsed:.0f}min"

    def _x(entry_x):
        """Return pos_X override if set, else use the entry's own X."""
        return pos_X if pos_X is not None else entry_x

    def collectAllThree(entry_x, pos_Y, entry_thickness, spot_title, debug=False):
        """
        Run USAXS → SAXS → WAXS for one vertical position.

        Parameters
        ----------
        entry_x, pos_Y : float   — stage position (X may be overridden by pos_X)
        entry_thickness : float  — sample thickness
        spot_title : str         — spot identifier from SampleList
        debug : bool             — True → print + sleep, no real instrument motion
        """
        x = entry_x
        sampleMod = getSampleName(spot_title)
        logger.debug("collectAllThree [%s]: %s", spot_title, sampleMod)
        if debug:
            print(f"[DEBUG] collectAllThree [{spot_title}]: {sampleMod}")
            yield from bps.sleep(20)
        else:
            yield from sync_order_numbers()
            sampleMod = getSampleName(spot_title)
            md["title"] = sampleMod
            logger.info("USAXSscan: %s", sampleMod)
            yield from USAXSscan(x, pos_Y, entry_thickness, sampleMod, md={})
            sampleMod = getSampleName(spot_title)
            md["title"] = sampleMod
            logger.info("saxsExp: %s", sampleMod)
            yield from saxsExp(x, pos_Y, entry_thickness, sampleMod, md={})
            sampleMod = getSampleName(spot_title)
            md["title"] = sampleMod
            logger.info("waxsExp: %s", sampleMod)
            yield from waxsExp(x, pos_Y, entry_thickness, sampleMod, md={})

    def collectAllPositions(debug=False):
        """Cycle through every entry in SampleList, collecting full USAXS/SAXS/WAXS."""
        for entry_x, pos_Y, entry_thickness, spot_title in SampleList:
            yield from collectAllThree(
                entry_x, pos_Y, entry_thickness, spot_title, debug
            )
            yield from bps.sleep(600)

    # =========================================================================
    # EXECUTION SEQUENCE
    # =========================================================================

    isDebugMode = ptc10_debug.get()
    recordFunctionRun()
    logger.info(
        "Starting ptc10MultiposaHeatRamp | sample=%s | %d positions | "
        "target=%s C @ %s C/min | debug=%s",
        scan_title,
        len(SampleList),
        temp_target,
        rate_heat,
        isDebugMode,
    )

    # --- Block 1: Startup ---------------------------------------------------
    if not isDebugMode:
        logger.info("Running before_command_list()")
        yield from before_command_list()
    else:
        logger.info("[DEBUG] Skipping before_command_list()")

    appendToMdFile(
        f"## PTC10 multi-position heat-ramp: {scan_title}\n"
        f"- **Positions:** {len(SampleList)}\n"
        f"- **Target temperature:** {temp_target} °C @ {rate_heat} °C/min\n"
        f"- **Secondary TC PV:** usxLAX:adam2:tc1.VAL\n"
        f"- **Cool-down target:** {temp_final} °C @ {rate_cool} °C/min"
    )

    # --- Block 2: Baseline at ambient temperature ---------------------------
    t0 = time.time()
    tc_now = tc_sample.get()
    # logger.info(
    #    "Collecting baseline at ambient T (TC=%.1f C, PTC10=%.1f C)",
    #    tc_now, ptc10.position,
    # )
    # appendToMdFile(
    #    f"Baseline: TC={tc_now:.1f} °C, PTC10={ptc10.position:.1f} °C — "
    #    f"collecting all {len(SampleList)} positions"
    # )
    # yield from collectAllPositions(isDebugMode)

    # --- Block 3: Start heating ramp ----------------------------------------
    # Ensure tolerance is at least 1 °C — this heater typically oscillates
    # ±1–2 °C at steady state; a tighter value causes inposition to never fire.
    ptc10.tolerance.put(2.0)
    logger.info("Heating to %s C at %s C/min", temp_target, rate_heat)
    appendToMdFile(
        f"Heating to {temp_target} °C at {rate_heat} °C/min — "
        f"collecting all positions until arrival"
    )
    yield from bps.mv(ptc10.ramp, rate_heat / 60.0)  # °C/min → °C/s
    yield from bps.mv(ptc10.temperature.setpoint, temp_target)
    yield from setheaterOn()

    # --- Block 4: Data collection loop during heat ramp ---------------------
    # Scan all positions repeatedly while PTC10 has not yet reached target.
    loop_count = 0
    while not ptc10.temperature.inposition:
        loop_count += 1
        tc_now = tc_sample.get()
        logger.info(
            "Ramp loop %d | TC=%.1f C | PTC10=%.1f C → %s C",
            loop_count,
            tc_now,
            ptc10.position,
            temp_target,
        )
        yield from collectAllPositions(isDebugMode)

    logger.info(
        "PTC10 reached %s C after %d position-sweep(s). TC=%.1f C",
        temp_target,
        loop_count,
        tc_sample.get(),
    )
    appendToMdFile(
        f"PTC10 arrived at {temp_target} °C after {loop_count} sweep(s). "
        f"TC={tc_sample.get():.1f} °C"
    )

    # --- Block 5: Cool to temp_final ----------------------------------------
    logger.info("Cooling to %s C at %s C/min (silent)", temp_final, rate_cool)
    appendToMdFile(f"Cooling to {temp_final} °C at {rate_cool} °C/min")
    yield from bps.mv(ptc10.ramp, rate_cool / 60.0)
    yield from bps.mv(ptc10.temperature.setpoint, temp_final)
    # Heater stays on for controlled cooling.
    while not ptc10.temperature.inposition:
        logger.debug("Cooling: PTC10=%.1f C", ptc10.position)
        yield from bps.sleep(5)

    yield from setheaterOff()

    # --- Block 6: Final dataset at temp_final -------------------------------
    t0 = time.time()  # reset so "elapsed" resets to 0 at final temp
    tc_now = tc_sample.get()
    logger.info("At %s C. Collecting final dataset. TC=%.1f C", temp_final, tc_now)
    appendToMdFile(f"Final dataset: PTC10={ptc10.position:.1f} °C, TC={tc_now:.1f} °C")
    yield from collectAllPositions(isDebugMode)

    logger.info("Plan complete: %s", scan_title)
    appendToMdFile(f"Plan complete: {scan_title}")

    # --- Block 7: Teardown --------------------------------------------------
    if not isDebugMode:
        logger.info("Running after_command_list()")
        yield from after_command_list()
    else:
        logger.info("[DEBUG] Skipping after_command_list()")
