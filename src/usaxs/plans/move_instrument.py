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

from bluesky import plan_stubs as bps

logger = logging.getLogger(__name__)
logger.info(__file__)

UsaxsSaxsModes = {
    "dirty": -1,  # moving or prior move did not finish correctly
    "out of beam": 1,  # SAXS, WAXS, and USAXS out of beam
    "USAXS in beam": 2,
    "SAXS in beam": 3,
    "WAXS in beam": 4,
    "Imaging in": 5,
    "Imaging tuning": 6,
}


def confirmUsaxsSaxsOutOfBeam(oregistry: Optional[Dict[str, Any]] = None):
    """
    Raise ValueError if not out of beam.

    Parameters
    ----------
    oregistry : Dict[str, Any], optional
        The ophyd registry containing device instances, by default None
    """
    terms = oregistry["terms"]
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


def move_WAXSOut(oregistry: Optional[Dict[str, Any]] = None):
    """
    Move WAXS out of beam.

    Parameters
    ----------
    oregistry : Dict[str, Any], optional
        The ophyd registry containing device instances, by default None
    """
    terms = oregistry["terms"]
    ti_filter_shutter = oregistry["ti_filter_shutter"]
    waxsx = oregistry["waxsx"]

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


def move_WAXSIn(oregistry: Optional[Dict[str, Any]] = None):
    """
    Move WAXS into beam.

    Parameters
    ----------
    oregistry : Dict[str, Any], optional
        The ophyd registry containing device instances, by default None
    """
    terms = oregistry["terms"]
    ti_filter_shutter = oregistry["ti_filter_shutter"]
    guard_slit = oregistry["guard_slit"]
    waxsx = oregistry["waxsx"]
    usaxs_slit = oregistry["usaxs_slit"]

    yield from bps.mv(
        ti_filter_shutter,
        "close",
    )

    logger.info("Moving to WAXS mode")

    confirmUsaxsSaxsOutOfBeam(oregistry)

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


def move_SAXSOut(oregistry: Optional[Dict[str, Any]] = None):
    """
    Move SAXS out of beam.

    Parameters
    ----------
    oregistry : Dict[str, Any], optional
        The ophyd registry containing device instances, by default None
    """
    terms = oregistry["terms"]
    ti_filter_shutter = oregistry["ti_filter_shutter"]
    saxs_stage = oregistry["saxs_stage"]

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


def move_SAXSIn(oregistry: Optional[Dict[str, Any]] = None):
    """
    Move SAXS into beam.

    Parameters
    ----------
    oregistry : Dict[str, Any], optional
        The ophyd registry containing device instances, by default None
    """
    terms = oregistry["terms"]
    ti_filter_shutter = oregistry["ti_filter_shutter"]
    guard_slit = oregistry["guard_slit"]
    saxs_stage = oregistry["saxs_stage"]
    usaxs_slit = oregistry["usaxs_slit"]

    yield from bps.mv(
        ti_filter_shutter,
        "close",
    )

    logger.info("Moving to Pinhole SAXS mode")

    confirmUsaxsSaxsOutOfBeam(oregistry)

    # in case there is an error in moving, it is NOT SAFE to start a scan
    yield from bps.mv(terms.SAXS.UsaxsSaxsMode, UsaxsSaxsModes["dirty"])

    yield from bps.mv(
        guard_slit.v_size,
        terms.SAXS.guard_v_size.get(),
        guard_slit.h_size,
        terms.SAXS.guard_h_size.get(),
        saxs_stage.y,
        terms.SAXS.y_in.get(),
        usaxs_slit.v_size,
        terms.SAXS.v_size.get(),
        usaxs_slit.h_size,
        terms.SAXS.h_size.get(),
    )

    # move Z _AFTER_ the others finish moving
    yield from bps.mv(saxs_stage.z, terms.SAXS.z_in.get())

    logger.info("Pinhole SAXS is in position")
    yield from bps.mv(terms.SAXS.UsaxsSaxsMode, UsaxsSaxsModes["SAXS in beam"])


def move_USAXSOut(oregistry: Optional[Dict[str, Any]] = None):
    """
    Move USAXS out of beam.

    Parameters
    ----------
    oregistry : Dict[str, Any], optional
        The ophyd registry containing device instances, by default None
    """
    terms = oregistry["terms"]
    ti_filter_shutter = oregistry["ti_filter_shutter"]
    a_stage = oregistry["a_stage"]
    d_stage = oregistry["d_stage"]

    yield from bps.mv(
        ti_filter_shutter,
        "close",
    )

    logger.info("Moving USAXS out of beam")
    # in case there is an error in moving, it is NOT SAFE to start a scan
    yield from bps.mv(terms.SAXS.UsaxsSaxsMode, UsaxsSaxsModes["dirty"])

    yield from bps.mv(
        a_stage.x,
        terms.SAXS.ax_out.get(),
        d_stage.x,
        terms.SAXS.dx_out.get(),
    )

    logger.info("Removed USAXS from beam position")
    yield from bps.mv(terms.SAXS.UsaxsSaxsMode, UsaxsSaxsModes["out of beam"])


def move_USAXSIn(oregistry: Optional[Dict[str, Any]] = None):
    """
    Move USAXS into beam.

    Parameters
    ----------
    oregistry : Dict[str, Any], optional
        The ophyd registry containing device instances, by default None
    """
    terms = oregistry["terms"]
    ti_filter_shutter = oregistry["ti_filter_shutter"]
    guard_slit = oregistry["guard_slit"]
    usaxs_slit = oregistry["usaxs_slit"]
    a_stage = oregistry["a_stage"]
    d_stage = oregistry["d_stage"]

    yield from bps.mv(
        ti_filter_shutter,
        "close",
    )

    logger.info("Moving to USAXS mode")

    confirmUsaxsSaxsOutOfBeam(oregistry)

    # in case there is an error in moving, it is NOT SAFE to start a scan
    yield from bps.mv(terms.SAXS.UsaxsSaxsMode, UsaxsSaxsModes["dirty"])

    # move USAXS in the beam

    yield from bps.mv(
        guard_slit.h_size,
        terms.SAXS.usaxs_guard_h_size.get(),
        guard_slit.v_size,
        terms.SAXS.usaxs_guard_v_size.get(),
        usaxs_slit.h_size,
        terms.SAXS.usaxs_h_size.get(),
        usaxs_slit.v_size,
        terms.SAXS.usaxs_v_size.get(),
        a_stage.y,
        terms.SAXS.ay_in.get(),
        a_stage.x,
        terms.SAXS.ax_in.get(),
        d_stage.y,
        terms.SAXS.dy_in.get(),
        d_stage.x,
        terms.USAXS.DX0.get(),  # same as: terms.USAXS:Diode_dx.get(),
    )

    logger.info("USAXS is in position")
    yield from bps.mv(terms.SAXS.UsaxsSaxsMode, UsaxsSaxsModes["USAXS in beam"])
