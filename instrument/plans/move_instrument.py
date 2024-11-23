
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

logger = logging.getLogger(__name__)
logger.info(__file__)

from bluesky import plan_stubs as bps

from ..devices.stages import a_stage, d_stage, saxs_stage
from ..devices.shutters import ccd_shutter, ti_filter_shutter
from ..devices.slits import guard_slit, usaxs_slit
# from ..devices.protection_plc import plc_protect
from ..devices.general_terms import terms
from ..devices.user_data import user_data
from ..devices import waxsx
from ..utils.a2q_q2a import angle2q, q2angle


UsaxsSaxsModes = {
    "dirty": -1,        # moving or prior move did not finish correctly
    "out of beam": 1,   # SAXS, WAXS, and USAXS out of beam
    "USAXS in beam": 2,
    "SAXS in beam": 3,
    "WAXS in beam": 4,
    "Imaging in": 5,
    "Imaging tuning": 6,
}

def confirmUsaxsSaxsOutOfBeam():
    """raise ValueError if not"""
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
    # yield from plc_protect.stop_if_tripped()
    yield from bps.mv(
        ccd_shutter,        "close",
        ti_filter_shutter,  "close",
    )

    logger.info("Moving WAXS out of beam")
    # in case there is an error in moving, it is NOT SAFE to start a scan
    yield from bps.mv(terms.SAXS.UsaxsSaxsMode, UsaxsSaxsModes["dirty"])

    # move the WAXS X away from sample
    yield from bps.mv(waxsx, terms.WAXS.x_out.get())

    # removed 12-21-2021, JIL. Not needed. Hard interlocks are better anyway
    #waxsx.set_lim(
    #    waxsx.low_limit_travel.get(),
    #    terms.WAXS.x_out.get() + terms.WAXS.x_limit_offset.get())

    logger.info("Removed WAXS from beam position")
    yield from bps.mv(terms.SAXS.UsaxsSaxsMode, UsaxsSaxsModes["out of beam"])


def move_WAXSIn():
    # yield from plc_protect.stop_if_tripped()
    yield from bps.mv(
        ccd_shutter,        "close",
        ti_filter_shutter,  "close",
    )

    logger.info("Moving to WAXS mode")

    confirmUsaxsSaxsOutOfBeam()
    # yield from plc_protect.wait_for_interlock()

    # in case there is an error in moving, it is NOT SAFE to start a scan
    yield from bps.mv(terms.SAXS.UsaxsSaxsMode, UsaxsSaxsModes["dirty"])

    # first move USAXS out of way
    # removed 12-21-2021, JIL. Not needed. Hard interlocks are better anyway
    #waxsx.set_lim(
    #    waxsx.low_limit_travel.get(),
    #    terms.WAXS.x_in.get() + terms.WAXS.x_limit_offset.get())

    yield from bps.mv(
        guard_slit.v_size, terms.SAXS.guard_v_size.get(),
        guard_slit.h_size, terms.SAXS.guard_h_size.get(),
        waxsx,             terms.WAXS.x_in.get(),
        usaxs_slit.v_size, terms.SAXS.v_size.get(),
        usaxs_slit.h_size, terms.SAXS.h_size.get(),
    )

    logger.info("WAXS is in position")
    yield from bps.mv(terms.SAXS.UsaxsSaxsMode, UsaxsSaxsModes["WAXS in beam"])


def move_SAXSOut():
    # yield from plc_protect.stop_if_tripped()
    yield from bps.mv(
        ccd_shutter,        "close",
        ti_filter_shutter,  "close",
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
    # yield from plc_protect.stop_if_tripped()
    yield from bps.mv(
        ccd_shutter,        "close",
        ti_filter_shutter,  "close",
    )

    logger.info("Moving to Pinhole SAXS mode")

    confirmUsaxsSaxsOutOfBeam()
    # yield from plc_protect.wait_for_interlock()

    # in case there is an error in moving, it is NOT SAFE to start a scan
    yield from bps.mv(terms.SAXS.UsaxsSaxsMode, UsaxsSaxsModes["dirty"])

    # first move USAXS out of way
    # removed 12-21-2021, JIL. Not needed. Hard interlocks are better anyway
    # saxs_stage.y.set_lim(
    #    terms.SAXS.y_in.get() - terms.SAXS.y_limit_offset.get(),
    #    saxs_stage.y.high_limit_travel.get(),
    #    )

    yield from bps.mv(
        guard_slit.v_size, terms.SAXS.guard_v_size.get(),
        guard_slit.h_size, terms.SAXS.guard_h_size.get(),
        saxs_stage.y,      terms.SAXS.y_in.get(),
        usaxs_slit.v_size, terms.SAXS.v_size.get(),
        usaxs_slit.h_size, terms.SAXS.h_size.get(),
    )

    #saxs_stage.z.set_lim(
    # removed 12-21-2021, JIL. Not needed. Hard interlocks are better anyway
    #    terms.SAXS.z_in.get() - terms.SAXS.z_limit_offset.get(),
    #    saxs_stage.z.high_limit_travel.get()   # do NOT change the hi value
    #    )

    # move Z _AFTER_ the others finish moving
    yield from bps.mv(saxs_stage.z, terms.SAXS.z_in.get())

    logger.info("Pinhole SAXS is in position")
    yield from bps.mv(terms.SAXS.UsaxsSaxsMode, UsaxsSaxsModes["SAXS in beam"])


def move_USAXSOut():
    # yield from plc_protect.stop_if_tripped()
    yield from bps.mv(
        ccd_shutter,        "close",
        ti_filter_shutter,  "close",
    )

    logger.info("Moving USAXS out of beam")
    # in case there is an error in moving, it is NOT SAFE to start a scan
    yield from bps.mv(terms.SAXS.UsaxsSaxsMode, UsaxsSaxsModes["dirty"])

    yield from bps.mv(
        a_stage.x, terms.SAXS.ax_out.get(),
        d_stage.x, terms.SAXS.dx_out.get(),
    )

    # now Main stages are out of place,
    # so we can now set the limits and then move pinhole in place.
    # removed 12-21-2021, JIL. Not needed. Hard interlocks are better anyway
    #a_stage.x.set_lim(
    #    terms.SAXS.ax_out.get() - terms.SAXS.ax_limit_offset.get(),
    #    a_stage.x.high_limit_travel.get())
    #d_stage.x.set_lim(
    #    d_stage.x.low_limit_travel.get(),
    #    terms.SAXS.dx_out.get() + terms.SAXS.dx_limit_offset.get())

    logger.info("Removed USAXS from beam position")
    yield from bps.mv(terms.SAXS.UsaxsSaxsMode, UsaxsSaxsModes["out of beam"])


def move_USAXSIn():
    # yield from plc_protect.stop_if_tripped()
    yield from bps.mv(
        ccd_shutter,        "close",
        ti_filter_shutter,  "close",
    )

    logger.info("Moving to USAXS mode")

    confirmUsaxsSaxsOutOfBeam()
    # yield from plc_protect.wait_for_interlock()

    # in case there is an error in moving, it is NOT SAFE to start a scan
    yield from bps.mv(terms.SAXS.UsaxsSaxsMode, UsaxsSaxsModes["dirty"])

    # move USAXS in the beam
    # set the limits so we can move pinhole in place.
    # removed 12-21-2021, JIL. Not needed. Hard interlocks are better anyway
    #a_stage.x.set_lim(
    #    terms.SAXS.ax_in.get() - terms.SAXS.ax_limit_offset.get(),
    #    a_stage.x.high_limit_travel.get())
    #d_stage.x.set_lim(
    #    d_stage.x.low_limit_travel.get(),
    #    terms.SAXS.dx_in.get() + terms.SAXS.dx_limit_offset.get())

    yield from bps.mv(
        guard_slit.h_size,  terms.SAXS.usaxs_guard_h_size.get(),
        guard_slit.v_size,  terms.SAXS.usaxs_guard_v_size.get(),
        usaxs_slit.h_size,  terms.SAXS.usaxs_h_size.get(),
        usaxs_slit.v_size,  terms.SAXS.usaxs_v_size.get(),
        a_stage.y,          terms.SAXS.ay_in.get(),
        a_stage.x,          terms.SAXS.ax_in.get(),
        d_stage.x,          terms.SAXS.dx_in.get(),
        d_stage.y,          terms.SAXS.dy_in.get(),
        #d_stage.x,          terms.USAXS.DX0.get, #this is same as terms.SAXS.dx_in.get
    )

    logger.info("USAXS is in position")
    yield from bps.mv(terms.SAXS.UsaxsSaxsMode, UsaxsSaxsModes["USAXS in beam"])
