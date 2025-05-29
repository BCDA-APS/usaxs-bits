"""
move the parts of the instrument in and out
"""

import logging
from typing import Any
from typing import Dict
from typing import Optional

from apsbits.core.instrument_init import oregistry
from apsbits.utils.config_loaders import get_config
from bluesky import plan_stubs as bps
from bluesky import preprocessors as bpp
from ophyd.scaler import ScalerCH

logger = logging.getLogger(__name__)


# # Device instances
terms = oregistry["terms"]
usaxs_shutter = oregistry["usaxs_shutter"]
guard_slit = oregistry["guard_slit"]
usaxs_slit = oregistry["usaxs_slit"]
waxsx = oregistry["waxsx"]
saxs_stage = oregistry["saxs_stage"]
user_data = oregistry["user_device"]
a_stage = oregistry["a_stage"]
d_stage = oregistry["d_stage"]
gslit_stage = oregistry["gslit_stage"]

iconfig = get_config()
scaler0_name = iconfig.get("SCALER_PV_NAMES", {}).get("SCALER0_NAME")

scaler0 = ScalerCH(scaler0_name, name="scaler0")
scaler0.stage_sigs["count_mode"] = "OneShot"
scaler0.select_channels()

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
        usaxs_shutter,
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
        usaxs_shutter,
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
        usaxs_shutter,
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
        usaxs_shutter,
        "close",
    )

    logger.info("Moving to Pinhole SAXS mode")

    confirmUsaxsSaxsOutOfBeam()

    # in case there is an error in moving, it is NOT SAFE to start a scan
    yield from bps.mv(terms.SAXS.UsaxsSaxsMode, UsaxsSaxsModes["dirty"])

    # move SAXS in place, in two steps to prevent possible damage to snout
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

    yield from bps.mv(
        saxs_stage.z,
        terms.SAXS.z_in.get(),
    )
    logger.info("SAXS is in position")
    yield from bps.mv(terms.SAXS.UsaxsSaxsMode, UsaxsSaxsModes["SAXS in beam"])


def move_USAXSOut():
    """
    Move USAXS out of beam.
    """
    yield from bps.mv(
        usaxs_shutter,
        "close",
    )

    logger.info("Moving USAXS out of beam")
    # in case there is an error in moving, it is NOT SAFE to start a scan
    yield from bps.mv(terms.SAXS.UsaxsSaxsMode, UsaxsSaxsModes["dirty"])

    # move the USAXS X away from sample
    yield from bps.mv(
        a_stage.x,
        terms.SAXS.ax_out.get(),
        d_stage.x,
        terms.SAXS.dx_out.get(),
    )

    logger.info("Removed USAXS from beam position")
    yield from bps.mv(terms.SAXS.UsaxsSaxsMode, UsaxsSaxsModes["out of beam"])


def move_USAXSIn():
    """
    Move USAXS into beam.
    """
    yield from bps.mv(
        usaxs_shutter,
        "close",
    )

    logger.info("Moving to USAXS mode")

    confirmUsaxsSaxsOutOfBeam()

    # in case there is an error in moving, it is NOT SAFE to start a scan
    yield from bps.mv(terms.SAXS.UsaxsSaxsMode, UsaxsSaxsModes["dirty"])

    # move to USAXS size
    yield from bps.mv(
        guard_slit.h_size,
        terms.USAXS.guard_h_size.get(),
        guard_slit.v_size,
        terms.USAXS.guard_v_size.get(),
        usaxs_slit.h_size,
        terms.USAXS.usaxs_h_size.get(),
        usaxs_slit.v_size,
        terms.USAXS.usaxs_v_size.get(),
        a_stage.y,
        terms.USAXS.ay_in.get(),
        a_stage.x,
        terms.USAXS.AX0.get(),
        d_stage.y,
        terms.USAXS.dy_in.get(),
        d_stage.x,
        terms.USAXS.DX0.get(),  # same as: terms.USAXS:Diode_dx.get(),
        gslit_stage.x,
        terms.USAXS.AX0.get(),  # this requires AX0 and Gslits.X be the same.
    )

    logger.info("USAXS is in position")
    yield from bps.mv(terms.SAXS.UsaxsSaxsMode, UsaxsSaxsModes["USAXS in beam"])


def move_instrument(
    target_position: float,
    md: Optional[Dict[str, Any]] = None,
):
    """Move instrument to a target position.

    This function moves the instrument to a specified position and
    optionally measures the intensity at that position.

    Parameters
    ----------
    target_position : float
        Target position in mm
    md : Optional[Dict[str, Any]], optional
        Metadata dictionary, by default None
    RE : Optional[Any], optional
        Bluesky RunEngine instance, by default None
    bec : Optional[Any], optional
        Bluesky Live Callbacks instance, by default None
    specwriter : Optional[Any], optional
        SPEC file writer instance, by default None

    Returns
    -------
    Generator[Any, None, Any]
        A sequence of plan messages

    USAGE:  ``RE(move_instrument(target_position=10.0))``
    """
    if md is None:
        md = {}

    _md = {}
    _md.update(md or {})

    @bpp.run_decorator(md=_md)
    def _inner():
        yield from user_data.set_state_plan(
            f"moving instrument to {target_position} mm"
        )
        yield from bps.mv(scaler0.count_mode, "OneShot")
        yield from bps.trigger(scaler0, group="movement")
        yield from bps.wait(group="movement")

    return (yield from _inner())
