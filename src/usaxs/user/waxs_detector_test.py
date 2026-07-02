"""
WAXS Detector Calibration Test Plan
====================================
Tests the WAXS detector by scanning the horizontal offset (WAXS_x_in)
and adjusting the beam center Y position accordingly to maintain proper
calibration across the range.

PURPOSE:
    Collect WAXS images of SiC powder at a range of horizontal offsets
    (-420 to -360 mm in 1 mm steps) while automatically adjusting the
    beam center Y position to maintain calibration.

SEQUENCE:
    1. For each WAXS_x_in from -420 to -360 mm (1 mm steps):
       a. Calculate the new BeamCenterY value based on the offset change
       b. Update PV usxLAX:WAXS:BeamCenterY
       c. Collect one WAXS image
       d. Sample name includes the offset distance for easy identification

CALIBRATION:
    Reference: WAXS_x_in = -395 mm → BeamCenterY = 2743.58 pixels
    Pixel size: 0.075 mm/pixel
    Formula: BeamCenterY = reference_Y - (reference_x_in - current_x_in) / 0.075
    
    Example: at -396 mm:
        BeamCenterY = 2743.58 - (-395 - (-396)) / 0.075
                    = 2743.58 - 1 / 0.075
                    = 2743.58 - 13.333
                    = 2730.247 pixels

LOADING:
    %run -im usaxs.user.waxs_detector_test

RUNNING:
    RE(waxsDetectorTest(beam_center_y_ref=2743.58))
    
    Or if the reference has changed after setup:
    RE(waxsDetectorTest(beam_center_y_ref=2750.0))

CHANGE LOG:
    * JIL, 2026-06-07 : Created for WAXS detector horizontal offset test
"""

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

import time

from bluesky import plan_stubs as bps
from ophyd import EpicsSignal

from apsbits.core.instrument_init import oregistry
from usaxs.plans.plans_user_facing import waxsExp
from usaxs.plans.command_list import after_command_list, before_command_list
from usaxs.utils.obsidian import appendToMdFile, recordFunctionRun

# ==============================================================================
# EPICS PVs for WAXS horizontal offset and beam center
# ==============================================================================

waxsx = oregistry["waxsx"]
waxs_x_in = EpicsSignal("usxLAX:WAXS_x_in", name="waxs_x_in")
waxs_beam_center_y = EpicsSignal(
    "usxLAX:WAXS:BeamCenterY", name="waxs_beam_center_y"
)

# ==============================================================================
# Calibration constants
# ==============================================================================

WAXS_X_IN_REFERENCE = -395.0  # mm
BEAM_CENTER_Y_REFERENCE = 2742.52  # pixels
PIXEL_SIZE = 0.075  # mm/pixel

# Scan range
WAXS_X_IN_START = -430  # mm
WAXS_X_IN_END = -360    # mm
WAXS_X_IN_STEP = 1      # mm

SAMPLE_NAME = "SiC"
THICKNESS = 1.0  # mm (placeholder; SiC powder, not critical)


# ==============================================================================
# MAIN PLAN
# ==============================================================================
def waxsDetectorTest(pos_X=20.0, pos_Y=120.0, beam_center_y_ref=BEAM_CENTER_Y_REFERENCE, md={}):
    """
    Scan WAXS horizontal offset and collect WAXS images with calibration.

    Parameters
    ----------
    pos_X, pos_Y : float, optional
        Sample stage position in mm (default 0, 0 — typically fixed for powder).
    beam_center_y_ref : float, optional
        Reference BeamCenterY value in pixels at WAXS_x_in = -395 mm.
        Default is 2743.58. Update this if the detector position has shifted
        after final alignment.
    md : dict, optional
        Extra metadata forwarded to WAXS collection.

    Load:
        %run -im usaxs.user.waxs_detector_test

    Run:
        RE(waxsDetectorTest())

        Or with custom reference (if setup changed):
        RE(waxsDetectorTest(beam_center_y_ref=2750.0))
    """

    # =========================================================================
    # Inner helper function
    # =========================================================================

    def calculate_beam_center_y(waxs_x_in_mm):
        """
        Calculate the required BeamCenterY for a given WAXS_x_in offset.

        Parameters
        ----------
        waxs_x_in_mm : float
            Horizontal offset in mm.

        Returns
        -------
        float
            Calculated BeamCenterY in pixels.

        Formula
        -------
        Larger WAXS_x_in makes BeamCenterY smaller (beam moves down in detector image).
        BeamCenterY = reference_Y - (reference_x - current_x) / pixel_size_mm
        """
        delta_x_mm = WAXS_X_IN_REFERENCE - waxs_x_in_mm
        delta_y_pix = delta_x_mm / PIXEL_SIZE
        beam_center_y = beam_center_y_ref - delta_y_pix
        return beam_center_y

    def get_sample_name(waxs_x_in_mm):
        """
        Return a sample name encoding the WAXS horizontal offset.

        Format: {SAMPLE_NAME}_{offset}mm
        Example: SiC_-395mm
        """
        return f"{SAMPLE_NAME}_{waxs_x_in_mm:.0f}mm"

    # =========================================================================
    # Execution sequence
    # =========================================================================

    recordFunctionRun()
    logger.info(
        "Starting WAXS detector test | sample=%s | "
        "WAXS_x_in: %.0f → %.0f mm (%.0f mm steps) | "
        "BeamCenterY ref: %.2f pixels @ x_in=-395mm",
        SAMPLE_NAME, WAXS_X_IN_START, WAXS_X_IN_END, WAXS_X_IN_STEP,
        beam_center_y_ref,
    )

    # --- Startup ---
    yield from before_command_list()

    appendToMdFile(
        f"## WAXS Detector Test Scan: {SAMPLE_NAME}\n"
        f"- **Sample:** {SAMPLE_NAME} powder (detector calibration test)\n"
        f"- **Detector:** WAXS (Eiger)\n"
        f"- **Scan range:** WAXS_x_in = {WAXS_X_IN_START} to {WAXS_X_IN_END} mm "
        f"({WAXS_X_IN_STEP} mm steps)\n"
        f"- **Total points:** {int((WAXS_X_IN_END - WAXS_X_IN_START) / WAXS_X_IN_STEP) + 1}\n"
        f"- **Calibration:**\n"
        f"  - Reference: WAXS_x_in = -395 mm → BeamCenterY = {beam_center_y_ref:.2f} pixels\n"
        f"  - Pixel size: {PIXEL_SIZE} mm/pixel\n"
        f"  - BeamCenterY adjusted for each offset to maintain calibration\n"
        f"- **Purpose:** Test detector response across beam center range\n"
        f"- **Stage position:** X={pos_X}, Y={pos_Y}\n"
    )

    # Build list of offsets to scan (include both endpoints)
    n_steps = int((WAXS_X_IN_END - WAXS_X_IN_START) / WAXS_X_IN_STEP) + 1
    offsets = [WAXS_X_IN_START + i * WAXS_X_IN_STEP for i in range(n_steps)]

    logger.info(
        "Scanning %d positions: %s", len(offsets),
        ", ".join(f"{x:.0f}mm" for x in offsets[:3]) +
        "..." + ", ".join(f"{x:.0f}mm" for x in offsets[-3:]),
    )

    t0 = time.time()
    position_count = 0

    for waxs_x_in_value in offsets:
        position_count += 1

        # Calculate the required beam center Y for this offset
        beam_center_y_value = calculate_beam_center_y(waxs_x_in_value)

        # Update PVs: set offset first, then beam center
        logger.info(
            "Position %d/%d | WAXS_x_in = %.1f mm → BeamCenterY = %.2f pixels",
            position_count, len(offsets), waxs_x_in_value, beam_center_y_value,
        )

        yield from bps.mv(
            waxsx,                waxs_x_in_value,
            waxs_x_in,            waxs_x_in_value,
            waxs_beam_center_y,   beam_center_y_value,
        )

        # Small stabilisation delay after moving to new position
        yield from bps.sleep(0.5)

        # Collect WAXS image
        sample_name = get_sample_name(waxs_x_in_value)
        yield from waxsExp(pos_X, pos_Y, THICKNESS, sample_name, md={})

        elapsed_min = (time.time() - t0) / 60.0
        logger.info(
            "  Collected: %s | elapsed: %.1f min",
            sample_name, elapsed_min,
        )

    # --- Summary and teardown ---
    elapsed_total = (time.time() - t0) / 60.0
    logger.info(
        "WAXS detector test complete | %d positions | %.1f min total",
        len(offsets), elapsed_total,
    )

    appendToMdFile(
        f"**Test complete:** Collected {len(offsets)} WAXS images in {elapsed_total:.1f} min\n"
        f"- **Range:** WAXS_x_in = {WAXS_X_IN_START} to {WAXS_X_IN_END} mm\n"
        f"- **BeamCenterY adjusted:** from {calculate_beam_center_y(WAXS_X_IN_START):.2f} "
        f"to {calculate_beam_center_y(WAXS_X_IN_END):.2f} pixels\n"
        f"- **Data ready for analysis**"
    )

    yield from after_command_list()