"""
Bluesky plan for time-resolved USAXS/SAXS data collection with rheometer synchronisation.

The plan drives USAXS and SAXS data collection in a continuous loop for a
user-defined duration.  A Galil analogue output (galil_voltage) is set to 5 V
immediately before each acquisition sequence and returned to 0 V afterwards —
this TTL-level signal is used to synchronise the rheometer trigger with each
USAXS/SAXS measurement.

NOTE: WAXS collection is currently disabled (commented out in collectAllThree).
      Re-enable it there if WAXS data are needed.

NOTE: pos_X, pos_Y, and thickness are hardcoded inside rheoLoop (0, 0, 1.0).
      Edit those lines directly if a different sample position or thickness
      is required.

LOADING:
    %run -im usaxs.user.rheometer

DEBUG MODE:
    loop_debug is defined as a module-level Signal but is not currently checked
    inside rheoLoop.  The plan always runs in live mode.  To test without
    collecting data, comment out the instrument calls inside collectAllThree
    and replace them with bps.sleep() calls.

CHANGE LOG:
    * JIL, 2022-11-17 : first release
    * JIL, 2022-11-18 : added different modes
    * JIL, 2025-05-28 : fixes for BITS
    * JIL, 2025-07-09 : user changes
    * JIL, 2026-02-26 : reformatted, documented, removed unused imports,
                        fixed wrong call example in docstring
"""

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

import time

from bluesky import plan_stubs as bps
from usaxs.plans.plans_user_facing import saxsExp
from usaxs.plans.plans_user_facing import waxsExp
from usaxs.plans.plans_usaxs import USAXSscan
from usaxs.plans.plans_tune import preUSAXStune
from usaxs.plans.command_list import after_command_list, sync_order_numbers
from usaxs.plans.command_list import before_command_list
from ophyd import Signal, EpicsSignal
from usaxs.utils.obsidian import appendToMdFile

# Time-unit constants for building delay expressions.
SECOND = 1
MINUTE = 60 * SECOND
HOUR = 60 * MINUTE
DAY = 24 * HOUR
WEEK = 7 * DAY

# Debug mode switch.
# NOTE: loop_debug is defined here for future use but is not currently checked
# inside rheoLoop.  The plan always runs in live mode.
# To activate: loop_debug.put(True)
loop_debug = Signal(name="loop_debug", value=False)

# Galil analogue output used to synchronise the rheometer with each
# USAXS/SAXS measurement.  Set to 5 V before acquisition, 0 V after.
galil_voltage = EpicsSignal("usxRIO:GalilAo1_SP.VAL", name="galil_voltage")


def rheoLoop(scan_title, delay1minutes, md={}):
    """
    Collect USAXS/SAXS data continuously for a fixed duration with rheometer sync.

    Each acquisition cycle:
        1. Sets galil_voltage to 5 V (rheometer trigger signal).
        2. Tunes the USAXS pre-optics (preUSAXStune).
        3. Collects USAXS then SAXS with the sample name stamped at USAXS start.
        4. Returns galil_voltage to 0 V.
        5. Sleeps 1 s before the next cycle.

    The cycle repeats until ``delay1minutes`` minutes have elapsed.

    Sample position (pos_X=0, pos_Y=0) and thickness (1.0 mm) are hardcoded
    inside this function.  Edit those lines directly if different values are
    needed.

    Parameters
    ----------
    scan_title : str
        Base name for all scans.  Elapsed time is appended automatically:
            {scan_title}_{elapsed_minutes:.0f}min
    delay1minutes : float
        Total data-collection duration in minutes.
    md : dict, optional
        Extra metadata passed to scan functions.

    Reload after editing:
        %run -im usaxs.user.rheometer

    Run:
        RE(rheoLoop("Sample", 20))
        — collects USAXS/SAXS for 20 minutes, labelling scans as
          "Sample_0min", "Sample_2min", etc.
    """
    # Sample stage position and thickness — edit here if needed.
    pos_X = 0
    pos_Y = 0
    thickness = 1.0

    def setSampleName():
        """
        Return a scan name encoding scan_title and elapsed time since t0.

        Format: {scan_title}_{elapsed_minutes:.0f}min

        Call immediately before each scan so the time stamp is current.
        """
        return f"{scan_title}_{((time.time() - t0) / 60):.0f}min"

    def collectAllThree():
        """
        Run one USAXS/SAXS acquisition cycle with rheometer synchronisation.

        Sequence:
            1. galil_voltage → 5 V  (trigger rheometer data capture)
            2. preUSAXStune()        (realign USAXS pre-optics)
            3. USAXSscan()           (USAXS measurement, ~1–1.5 min)
            4. saxsExp()             (SAXS measurement, ~2 min)
            5. galil_voltage → 0 V  (end trigger signal)
            6. sleep 1 s

        WAXS is currently disabled.  To re-enable it, uncomment the waxsExp
        block below.

        The sample name is refreshed before USAXS and reused for SAXS so that
        both scans carry the same time stamp (time at USAXS start).
        """
        yield from bps.mv(galil_voltage, 5)
        yield from sync_order_numbers()
        yield from preUSAXStune()
        sampleMod = setSampleName()
        md["title"] = sampleMod
        yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
        # Sample name intentionally NOT refreshed here so SAXS shares the
        # same time-stamp label as the USAXS scan that precedes it.
        md["title"] = sampleMod
        yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
        # WAXS is disabled — uncomment the three lines below to re-enable:
        # sampleMod = setSampleName()
        # md["title"] = sampleMod
        # yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
        yield from bps.mv(galil_voltage, 0)
        yield from bps.sleep(1)

    yield from before_command_list()  # runs standard startup scripts for scans

    t0 = time.time()  # mark start time of data collection

    checkpoint = time.time() + delay1minutes * MINUTE  # time to stop collecting

    logger.info("Collecting data for %s minutes", delay1minutes)
    appendToMdFile(f"Measuring sample {scan_title} for {delay1minutes} minutes")

    while time.time() < checkpoint:
        yield from collectAllThree()

    logger.info("finished")
    appendToMdFile(f"Finished measuring sample {scan_title}")

    yield from after_command_list()  # runs standard after-scan scripts
