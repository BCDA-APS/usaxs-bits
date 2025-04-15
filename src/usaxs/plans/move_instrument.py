"""
move the parts of the instrument in and out
"""

__all__ = """
    move_SAXSIn
    move_USAXSIn
    move_WAXSIn

    move_SAXSOut
    move_USAXSOut
    move_WAXSOut

    UsaxsSaxsModes
""".split()

import logging
from typing import Any
from typing import Dict
from typing import Optional

from apsbits.utils.controls_setup import oregistry
from bluesky import plan_stubs as bps

logger = logging.getLogger(__name__)
logger.info(__file__)

# Device instances
terms = oregistry["terms"]
saxs_det = oregistry["saxs_det"]
waxs_det = oregistry["waxs_det"]
usaxs_det = oregistry["usaxs_det"]
ti_filter_shutter = oregistry["ti_filter_shutter"]
guard_slit = oregistry["guard_slit"]
usaxs_slit = oregistry["usaxs_slit"]
waxsx = oregistry["waxsx"]
saxs_stage = oregistry["saxs_stage"]

UsaxsSaxsModes = {
    "dirty": -1,  # moving or prior move did not finish correctly
    "out of beam": 1,  # SAXS, WAXS, and USAXS out of beam
    "USAXS in beam": 2,
    "SAXS in beam": 3,
    "WAXS in beam": 4,
    "Imaging in": 5,
    "Imaging tuning": 6,
}


def confirmUsaxsSaxsOutOfBeam():
    """
    Raise ValueError if not out of beam.
    """
    actual = terms.SAXS.UsaxsSaxsMode.get(
        timeout=60, as_string=False, use_monitor=False
    )
    expected = UsaxsSaxsModes["out of beam"]
    if actual != expected:
        xref = {v: k for k, v in UsaxsSaxsModes.items()}
        actual_str = xref.get(actual, "undefined")
        logger.warning("Found UsaxsSaxsMode = %s (%s)", actual, actual_str)
        raise ValueError(
            f"Incorrect UsaxsSaxsMode mode found ({actual}, {actual_str})."
            "  If SAXS, WAXS, and USAXS really are out of beam, type: "
            f" terms.SAXS.UsaxsSaxsMode.put({expected})"
        )


def move_WAXSOut():
    """
    Move WAXS out of beam.
    """
    yield from bps.mv(
        ti_filter_shutter,
        "close",
    )

    logger.info("Moving WAXS out of beam")
    # in case there is an error in moving, it is NOT SAFE to start a scan
    yield from bps.mv(terms.SAXS.UsaxsSaxsMode, UsaxsSaxsModes["dirty"])

    # move the WAXS X away from sample
    yield from bps.mv(waxsx, terms.WAXS.x_out.get())

    logger.info("Removed WAXS from beam position")
    yield from bps.mv(terms.SAXS.UsaxsSaxsMode, UsaxsSaxsModes["out of beam"])


def move_WAXSIn():
    """
    Move WAXS into beam.
    """
    yield from bps.mv(
        ti_filter_shutter,
        "close",
    )

    logger.info("Moving to WAXS mode")

    confirmUsaxsSaxsOutOfBeam()

    # in case there is an error in moving, it is NOT SAFE to start a scan
    yield from bps.mv(terms.SAXS.UsaxsSaxsMode, UsaxsSaxsModes["dirty"])

    # first move USAXS out of way
    yield from bps.mv(
        guard_slit.v_size,
        terms.SAXS.guard_v_size.get(),
        guard_slit.h_size,
        terms.SAXS.guard_h_size.get(),
        waxsx,
        terms.WAXS.x_in.get(),
        usaxs_slit.v_size,
        terms.SAXS.v_size.get(),
        usaxs_slit.h_size,
        terms.SAXS.h_size.get(),
    )

    logger.info("WAXS is in position")
    yield from bps.mv(terms.SAXS.UsaxsSaxsMode, UsaxsSaxsModes["WAXS in beam"])


def move_SAXSOut():
    """
    Move SAXS out of beam.
    """
    yield from bps.mv(
        ti_filter_shutter,
        "close",
    )

    logger.info("Moving SAXS out of beam")
    # in case there is an error in moving, it is NOT SAFE to start a scan
    yield from bps.mv(terms.SAXS.UsaxsSaxsMode, UsaxsSaxsModes["dirty"])

    # move the pin_z away from sample
    yield from bps.mv(saxs_stage.z, terms.SAXS.z_out.get())

    # move pinhole up to out of beam position
    yield from bps.mv(saxs_stage.y, terms.SAXS.y_out.get())

    logger.info("Removed SAXS from beam position")
    yield from bps.mv(terms.SAXS.UsaxsSaxsMode, UsaxsSaxsModes["out of beam"])


def move_SAXSIn():
    """
    Move SAXS into beam.
    """
    yield from bps.mv(
        ti_filter_shutter,
        "close",
    )

    logger.info("Moving to Pinhole SAXS mode")

    confirmUsaxsSaxsOutOfBeam()

    # in case there is an error in moving, it is NOT SAFE to start a scan
    yield from bps.mv(terms.SAXS.UsaxsSaxsMode, UsaxsSaxsModes["dirty"])

    # first move USAXS out of way
    yield from bps.mv(
        guard_slit.v_size,
        terms.SAXS.guard_v_size.get(),
        guard_slit.h_size,
        terms.SAXS.guard_h_size.get(),
        saxs_stage.z,
        terms.SAXS.z_in.get(),
        saxs_stage.y,
        terms.SAXS.y_in.get(),
        usaxs_slit.v_size,
        terms.SAXS.v_size.get(),
        usaxs_slit.h_size,
        terms.SAXS.h_size.get(),
    )

    logger.info("SAXS is in position")
    yield from bps.mv(terms.SAXS.UsaxsSaxsMode, UsaxsSaxsModes["SAXS in beam"])


def move_USAXSOut():
    """
    Move USAXS out of beam.
    """
    yield from bps.mv(
        ti_filter_shutter,
        "close",
    )

    logger.info("Moving USAXS out of beam")
    # in case there is an error in moving, it is NOT SAFE to start a scan
    yield from bps.mv(terms.SAXS.UsaxsSaxsMode, UsaxsSaxsModes["dirty"])

    # move the USAXS X away from sample
    yield from bps.mv(usaxs_slit.x, terms.USAXS.x_out.get())

    logger.info("Removed USAXS from beam position")
    yield from bps.mv(terms.SAXS.UsaxsSaxsMode, UsaxsSaxsModes["out of beam"])


def move_USAXSIn():
    """
    Move USAXS into beam.
    """
    yield from bps.mv(
        ti_filter_shutter,
        "close",
    )

    logger.info("Moving to USAXS mode")

    confirmUsaxsSaxsOutOfBeam()

    # in case there is an error in moving, it is NOT SAFE to start a scan
    yield from bps.mv(terms.SAXS.UsaxsSaxsMode, UsaxsSaxsModes["dirty"])

    # first move SAXS and WAXS out of way
    yield from bps.mv(
        guard_slit.v_size,
        terms.USAXS.guard_v_size.get(),
        guard_slit.h_size,
        terms.USAXS.guard_h_size.get(),
        usaxs_slit.x,
        terms.USAXS.x_in.get(),
        usaxs_slit.v_size,
        terms.USAXS.v_size.get(),
        usaxs_slit.h_size,
        terms.USAXS.h_size.get(),
    )

    logger.info("USAXS is in position")
    yield from bps.mv(terms.SAXS.UsaxsSaxsMode, UsaxsSaxsModes["USAXS in beam"])
