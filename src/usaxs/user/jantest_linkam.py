"""
Linkam TC-1 two-segment heating plan for user Jantest.

EXPERIMENT SEQUENCE
    1. Go to 30 C (baseline), collect USAXS/SAXS/WAXS.
    2. Heat to temp1 at rate1 C/min, hold there for time1_min minutes,
       collecting USAXS/SAXS/WAXS repeatedly.
    3. Change temperature to temp2 at rate2 C/min, hold there for time2_min
       minutes, collecting USAXS/SAXS/WAXS repeatedly.
    4. Cool to 40 C at rate2 C/min, collect a final USAXS/SAXS/WAXS dataset,
       then end the run (teardown / "switch off").

Note: the Linkam TC-1 has no explicit heater-off command like the PTC10 —
"switch off" here means the plan ends and after_command_list() returns the
instrument to its safe idle state. The Linkam controller itself is left
sitting at the 40 C setpoint; turn it off from the Linkam control software
if you want the physical heater element de-energised.

LOADING
    %run -im usaxs.user.jantest_linkam

DEBUG / DRY-RUN (exercises the full thermal profile and timing, but skips
before_command_list/after_command_list and does not touch USAXS/SAXS/WAXS
detectors):
    linkam_debug.put(True)
    RE(jantestLinkamPlan(0, 0, 1.0, "Jantest", 150, 20, 30, 250, 10, 30))

REAL RUN
    linkam_debug.put(False)
    RE(jantestLinkamPlan(0, 0, 1.0, "Jantest", 150, 20, 30, 250, 10, 30))

CHANGE LOG:
    * Aida, 2026 : initial plan for Jantest, from linkam_template.py
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

# Linkam TC-1 device from the ophyd device registry.
linkam_tc1 = oregistry["linkam_tc1"]

SECOND = 1
MINUTE = 60 * SECOND
HOUR = 60 * MINUTE

# Debug / dry-run flag for this file.
#   linkam_debug.put(True)   -> dry run: no before/after_command_list, no
#                                USAXS/SAXS/WAXS data collection (prints
#                                sample name + sleeps instead). Linkam
#                                temperature ramps/holds still run for real.
#   linkam_debug.put(False)  -> normal, real data collection (default)
linkam_debug = Signal(name="linkam_debug", value=False)


def jantestLinkamPlan(
    pos_X,
    pos_Y,
    thickness,
    scan_title,
    temp1,
    rate1,
    time1_min,
    temp2,
    rate2,
    time2_min,
    temp_final=40,
    md={},
):
    """
    Two-segment Linkam TC-1 heating plan for user Jantest.

    Sequence:
        1. Go to 30 C baseline (fast ramp, no data during move), collect
           USAXS/SAXS/WAXS.
        2. Heat to temp1 at rate1 C/min (no data during ramp), then hold at
           temp1 for time1_min minutes, collecting USAXS/SAXS/WAXS repeatedly.
        3. Change temperature to temp2 at rate2 C/min (no data during ramp),
           then hold at temp2 for time2_min minutes, collecting
           USAXS/SAXS/WAXS repeatedly.
        4. Cool to temp_final (default 40 C) at rate2 C/min, collect a final
           USAXS/SAXS/WAXS dataset, then end ("switch off").

    Parameters
    ----------
    pos_X, pos_Y : float
        Sample stage X/Y position in mm.
    thickness : float
        Sample thickness in mm (used for transmission correction).
    scan_title : str
        Base name for all scans (e.g. "Jantest"). Temperature and elapsed
        time are appended automatically.
    temp1 : float
        First target (hold) temperature in C.
    rate1 : float
        Ramp rate from 30 C baseline to temp1, in C/min.
    time1_min : float
        Hold time at temp1, in minutes.
    temp2 : float
        Second target (hold) temperature in C.
    rate2 : float
        Ramp rate from temp1 to temp2, in C/min. Also used for the final
        cool-down to temp_final.
    time2_min : float
        Hold time at temp2, in minutes.
    temp_final : float, optional
        Terminal temperature in C after the temp2 hold (default 40 C).
    md : dict, optional
        Extra metadata passed to the scan functions.

    Load with:
        %run -im usaxs.user.jantest_linkam

    Dry run (no instrument motion for USAXS/SAXS/WAXS, real Linkam timing):
        linkam_debug.put(True)
        RE(jantestLinkamPlan(0, 0, 1.0, "Jantest", 150, 20, 30, 250, 10, 30))

    Real run:
        linkam_debug.put(False)
        RE(jantestLinkamPlan(0, 0, 1.0, "Jantest", 150, 20, 30, 250, 10, 30))
    """

    # ------------------------------------------------------------------
    # Inner helper functions
    # ------------------------------------------------------------------

    def setSampleName():
        """Sample name: {scan_title}_{temperature:.0f}C_{elapsed_minutes:.0f}min."""
        return (
            f"{scan_title}"
            f"_{linkam.temperature.position:.0f}C"
            f"_{(time.time() - t0) / 60:.0f}min"
        )

    def collectAllThree(debug=False):
        """Collect one USAXS -> SAXS -> WAXS sequence with fresh sample names."""
        sampleMod = setSampleName()
        logger.debug("collectAllThree: sample name = %s", sampleMod)
        if debug:
            print(f"[DEBUG] collectAllThree: {sampleMod}")
            yield from bps.sleep(20)
        else:
            yield from sync_order_numbers()
            md["title"] = sampleMod
            yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = setSampleName()
            md["title"] = sampleMod
            yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = setSampleName()
            md["title"] = sampleMod
            yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    def change_rate_and_temperature(rate, t, wait=False):
        """Set the Linkam ramp rate and move to a new target temperature."""
        logger.debug(
            "change_rate_and_temperature: rate=%s C/min, target=%s C, wait=%s",
            rate,
            t,
            wait,
        )
        yield from bps.mv(linkam.ramprate.setpoint, rate)
        yield from linkam.set_target(t, wait=wait)

    # ------------------------------------------------------------------
    # Execution sequence
    # ------------------------------------------------------------------
    linkam = linkam_tc1

    isDebugMode = linkam_debug.get()
    recordFunctionRun()
    logger.info(
        "Starting jantestLinkamPlan | sample=%s | debug=%s", scan_title, isDebugMode
    )

    # --- Block 1: Startup -------------------------------------------------
    if not isDebugMode:
        yield from before_command_list()

    appendToMdFile(
        f"Starting jantestLinkamPlan: sample={scan_title}, "
        f"temp1={temp1} C @ {rate1} C/min (hold {time1_min} min), "
        f"temp2={temp2} C @ {rate2} C/min (hold {time2_min} min), "
        f"cool to {temp_final} C @ {rate2} C/min"
    )

    # --- Block 2: Baseline at 30 C -----------------------------------------
    logger.info("Moving to 30 C baseline")
    yield from change_rate_and_temperature(150, 30, wait=True)
    t0 = time.time()
    appendToMdFile("At 30 C baseline. Collecting initial dataset.")
    yield from collectAllThree(isDebugMode)

    # --- Block 3: Heat to temp1, hold and collect for time1_min -----------
    logger.info("Heating to %s C at %s C/min", temp1, rate1)
    appendToMdFile(f"Heating to {temp1} C at {rate1} C/min")
    yield from change_rate_and_temperature(rate1, temp1, wait=True)

    # Reset t0 so file names show time elapsed since arriving at temp1.
    t0 = time.time()
    logger.info("Reached %s C, collecting data for %s minutes", temp1, time1_min)
    appendToMdFile(f"Reached {temp1} C, collecting data for {time1_min} minutes")
    hold_until = time.time() + time1_min * MINUTE
    while time.time() < hold_until:
        yield from collectAllThree(isDebugMode)

    # --- Block 4: Change to temp2, hold and collect for time2_min ---------
    logger.info("Changing temperature to %s C at %s C/min", temp2, rate2)
    appendToMdFile(f"Changing temperature to {temp2} C at {rate2} C/min")
    yield from change_rate_and_temperature(rate2, temp2, wait=True)

    # Reset t0 so file names show time elapsed since arriving at temp2.
    t0 = time.time()
    logger.info("Reached %s C, collecting data for %s minutes", temp2, time2_min)
    appendToMdFile(f"Reached {temp2} C, collecting data for {time2_min} minutes")
    hold_until = time.time() + time2_min * MINUTE
    while time.time() < hold_until:
        yield from collectAllThree(isDebugMode)

    # --- Block 5: Cool to temp_final, collect final dataset, and end ------
    logger.info("Cooling to %s C at %s C/min", temp_final, rate2)
    appendToMdFile(f"Cooling to {temp_final} C at {rate2} C/min")
    yield from change_rate_and_temperature(rate2, temp_final, wait=True)

    t0 = time.time()
    logger.info("Reached %s C. Collecting final dataset.", temp_final)
    appendToMdFile(f"Reached {temp_final} C. Collecting final dataset.")
    yield from collectAllThree(isDebugMode)

    logger.info("Plan complete: %s", scan_title)
    appendToMdFile(f"Plan complete: {scan_title}. Ending run (switching off).")

    # --- Block 6: Teardown ---------------------------------------------------
    if not isDebugMode:
        yield from after_command_list()
