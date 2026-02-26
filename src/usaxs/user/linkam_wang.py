"""
Wang experiment: Linkam heat-hold-cool plan for USAXS/SAXS/WAXS data collection.

==============================================================================
EXPERIMENT SEQUENCE
==============================================================================

    1. Baseline: ramp to ~40 °C (room temperature), collect USAXS/SAXS/WAXS.
    2. Heat to temp1 at rate1 °C/min — NO data collection during heating.
    3. Hold at temp1 for delay1 minutes, collecting USAXS/SAXS/WAXS repeatedly.
    4. Cool to temp2 at rate2 °C/min — NO data collection during cooling.
    5. Collect USAXS/SAXS/WAXS at temp2 for delay2 minutes.
    6. End (teardown).

==============================================================================
LOADING AND RUNNING
==============================================================================

    Load:
        %run -im usaxs.user.linkam_wang

    Debug mode (no instrument operations):
        linkam_debug.put(True)
        RE(linkam_wang(0, 0, 1.0, "WangSample", 200, 20, 30, 50, 40, 15))

    Real run:
        linkam_debug.put(False)
        RE(linkam_wang(0, 0, 1.0, "WangSample", 200, 20, 30, 50, 40, 15))

==============================================================================
DEBUG MODE
==============================================================================

    linkam_debug.put(True)   → enable debug (no instrument motion, sleeps instead)
    linkam_debug.put(False)  → restore normal data collection

CHANGE LOG:
    * AI-assisted, 2026-02-26 : Initial plan for Wang experiment

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
linkam_tc1 = oregistry["linkam_tc1"]

# Convenient time-unit constants — use these in delay expressions.
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


def linkam_wang(
    pos_X,
    pos_Y,
    thickness,
    scan_title,
    temp1,
    rate1,
    delay1,
    rate2,
    temp2,
    delay2,
    md={},
):
    """
    Wang experiment: heat-hold-cool plan with data collection at baseline, hold, and end.

    Sequence:
        1. Ramp to 40 °C (room temperature baseline), collect USAXS/SAXS/WAXS.
        2. Heat to temp1 at rate1 °C/min — no data collection during heating.
        3. Hold at temp1 for delay1 minutes, collecting USAXS/SAXS/WAXS repeatedly.
        4. Cool to temp2 at rate2 °C/min — no data collection during cooling.
        5. Collect USAXS/SAXS/WAXS at temp2 for delay2 minutes.
        6. End (teardown).

    Parameters
    ----------
    pos_X, pos_Y : float
        Sample stage X/Y position in mm.
    thickness : float
        Sample thickness in mm (used for transmission correction).
    scan_title : str
        Base name for all scans. Temperature and elapsed time are appended automatically.
    temp1 : float
        Target heating temperature in °C.
    rate1 : float
        Heating ramp rate from baseline to temp1 in °C/min.
    delay1 : float
        Hold time at temp1 in minutes. Data are collected throughout.
    rate2 : float
        Cooling ramp rate from temp1 to temp2 in °C/min.
    temp2 : float
        End (terminal) temperature in °C. Data are collected here for delay2 minutes.
    delay2 : float
        Data collection time at temp2 in minutes.
    md : dict, optional
        Extra metadata passed into scan functions.

    Load with:
        %run -im usaxs.user.linkam_wang

    Enable debug mode (no instrument operations):
        linkam_debug.put(True)

    Run:
        RE(linkam_wang(0, 0, 1.0, "WangSample", 200, 20, 30, 50, 40, 15))
    """

    # =========================================================================
    # INNER HELPER FUNCTIONS
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
            False → plan returns immediately; follow with a
                    ``while not linkam.temperature.inposition`` loop to collect
                    data as the temperature changes.
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
    linkam = linkam_tc1

    # Read the debug flag once so behaviour is consistent for the entire plan.
    isDebugMode = linkam_debug.get()
    logger.info(
        "Starting linkam_wang | sample=%s | debug=%s",
        scan_title, isDebugMode,
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
        f"Starting linkam_wang: sample={scan_title}, "
        f"heat to {temp1} °C @ {rate1} °C/min, "
        f"hold {delay1} min, "
        f"cool to {temp2} °C @ {rate2} °C/min, "
        f"collect at {temp2} °C for {delay2} min"
    )
    logger.info(
        "Plan parameters: temp1=%s C, rate1=%s C/min, delay1=%s min, "
        "rate2=%s C/min, temp2=%s C, delay2=%s min",
        temp1, rate1, delay1, rate2, temp2, delay2,
    )

    # -------------------------------------------------------------------------
    # BLOCK 2: Baseline data at room temperature (~40 °C)
    # Ramp quickly (150 °C/min) and wait until stable before collecting.
    # -------------------------------------------------------------------------
    logger.info("Moving to baseline temperature 40 C at 150 C/min")
    yield from change_rate_and_temperature(150, 40, wait=True)

    # t0 marks experiment start — file names show elapsed time from here.
    t0 = time.time()
    logger.info("At 40 C baseline. Collecting initial USAXS/SAXS/WAXS dataset.")
    appendToMdFile("At 40 C baseline. Collecting initial dataset.")
    yield from collectAllThree(isDebugMode)

    # -------------------------------------------------------------------------
    # BLOCK 3: Heat to temp1 — no data collection during ramp
    # wait=True blocks until temp1 is reached before continuing.
    # -------------------------------------------------------------------------
    logger.info("Heating to %s C at %s C/min (no data during heating)", temp1, rate1)
    appendToMdFile(f"Heating to {temp1} C at {rate1} C/min — no data collection during ramp")
    yield from change_rate_and_temperature(rate1, temp1, wait=True)

    # Reset t0 so file names count elapsed time from arrival at temp1.
    t0 = time.time()
    logger.info("Arrived at %s C. Beginning hold phase (%s min).", temp1, delay1)
    appendToMdFile(f"Arrived at {temp1} C. Beginning {delay1} min hold.")

    # -------------------------------------------------------------------------
    # BLOCK 4: Isothermal hold at temp1 — collect USAXS/SAXS/WAXS
    # Repeat full sequences until the hold timer expires.
    # -------------------------------------------------------------------------
    hold_until = time.time() + delay1 * MINUTE
    logger.info("Hold phase: collecting until %s min elapsed.", delay1)
    while time.time() < hold_until:
        logger.debug(
            "Hold loop: %.1f min remaining",
            (hold_until - time.time()) / MINUTE,
        )
        yield from collectAllThree(isDebugMode)

    logger.info("Hold complete (%s min). Cooling to %s C.", delay1, temp2)
    appendToMdFile(f"Hold complete ({delay1} min). Cooling to {temp2} C at {rate2} C/min.")

    # -------------------------------------------------------------------------
    # BLOCK 5: Cool to temp2 — no data collection during cooling
    # wait=True blocks until temp2 is reached before continuing.
    # -------------------------------------------------------------------------
    logger.info("Cooling to %s C at %s C/min (no data during cooling)", temp2, rate2)
    appendToMdFile(f"Cooling to {temp2} C at {rate2} C/min — no data collection during cooling")
    yield from change_rate_and_temperature(rate2, temp2, wait=True)

    # Reset t0 so file names count elapsed time from arrival at temp2.
    t0 = time.time()
    logger.info("Arrived at %s C. Collecting data for %s min.", temp2, delay2)
    appendToMdFile(f"Arrived at {temp2} C. Collecting data for {delay2} min.")

    # -------------------------------------------------------------------------
    # BLOCK 6: Collect data at temp2 for delay2 minutes
    # Repeat full USAXS/SAXS/WAXS sequences until the timer expires.
    # -------------------------------------------------------------------------
    collect_until = time.time() + delay2 * MINUTE
    while time.time() < collect_until:
        logger.debug(
            "Collect loop at %s C: %.1f min remaining",
            temp2, (collect_until - time.time()) / MINUTE,
        )
        yield from collectAllThree(isDebugMode)

    logger.info("Data collection at %s C complete (%s min). Plan finished.", temp2, delay2)
    appendToMdFile(f"Data collection at {temp2} C complete ({delay2} min). Plan finished: {scan_title}")

    # -------------------------------------------------------------------------
    # BLOCK 7: Teardown
    # -------------------------------------------------------------------------
    if not isDebugMode:
        logger.info("Running after_command_list()")
        yield from after_command_list()
    else:
        logger.info("[DEBUG] Skipping after_command_list()")
