"""
Plans for changing instrument modes in USAXS.
"""

### This file is work-in-progress
# see: https://subversion.xray.aps.anl.gov/spec/beamlines/USAXS/trunk/macros/local/usaxs_commands.mac

import datetime
import logging

from apsbits.core.instrument_init import oregistry
from apsbits.utils.config_loaders import get_config
from apstools.devices import SCALER_AUTOCOUNT_MODE
from bluesky import plan_stubs as bps
from ophyd.scaler import ScalerCH

from .filter_plans import insertBlackflyFilters
from .filter_plans import insertRadiographyFilters
from .filter_plans import insertScanFilters
from .mono_feedback import MONO_FEEDBACK_ON
from .move_instrument import UsaxsSaxsModes
from .move_instrument import move_SAXSIn
from .move_instrument import move_SAXSOut
from .move_instrument import move_USAXSIn
from .move_instrument import move_USAXSOut
from .move_instrument import move_WAXSIn
from .move_instrument import move_WAXSOut

logger = logging.getLogger(__name__)


terms = oregistry["terms"]
user_data = oregistry["user_data"]
d_stage = oregistry["d_stage"]
m_stage = oregistry["m_stage"]
a_stage = oregistry["a_stage"]
gslit_stage = oregistry["gslit_stage"]
usaxs_shutter = oregistry["usaxs_shutter"]
blackfly_det = oregistry["blackfly_det"]
guard_slit = oregistry["guard_slit"]
usaxs_slit = oregistry["usaxs_slit"]
diagnostics = oregistry["diagnostics"]
mono_shutter = oregistry["mono_shutter"]
monochromator = oregistry["monochromator"]


iconfig = get_config()
scaler0_name = iconfig.get("SCALER_PV_NAMES", {}).get("SCALER0_NAME")

scaler0 = ScalerCH(scaler0_name, name="scaler0")
scaler0.stage_sigs["count_mode"] = "OneShot"

NUM_AUTORANGE_GAINS = 5  # common to all autorange sequence programs
AMPLIFIER_MINIMUM_SETTLING_TIME = 0.01  # reasonable?


def confirm_instrument_mode(mode_name):
    """
    True if instrument is in the named mode

    Parameter

    mode_name (str) :
        One of the strings defined in ``UsaxsSaxsModes``
    """
    expected_mode = UsaxsSaxsModes[mode_name]
    return terms.SAXS.UsaxsSaxsMode.get() in (expected_mode, mode_name)


# #def mode_Laser(md=None):
#     """
#     Sets to Laser distance meter mode, using AR500 laser.
#     """
#     yield from mode_OpenBeamPath()
#     yield from user_data.set_state_plan(
#         "Preparing for Laser distacne meter mode"
#         )
#     yield from bps.mv(
#         usaxs_shutter,        "close",
#         d_stage.x, laser.dx.get(),
#         d_stage.y, laser.dy.get(),
#         )
#     yield from bps.mv(
#         laser.enable,  1,
#         )


def mode_DirectBeam(md=None):
    """
    Sets to imaging mode for direct beam, using BlackFly camera.
    """
    yield from mode_USAXS()
    yield from MONO_FEEDBACK_ON()
    yield from user_data.set_state_plan("Preparing for BlackFly imaging mode")

    yield from bps.mv(
        # fmt: off
        # laser.enable,  0,
        d_stage.x,
        terms.USAXS.blackfly.dx.get(),
        d_stage.y,
        terms.USAXS.blackfly.dy.get(),
        m_stage.x,
        -200,
        a_stage.x,
        -200,
        gslit_stage.x,
        0,
        # fmt: on
    )

    yield from insertBlackflyFilters()
    yield from bps.mv(
        # fmt: off
        usaxs_shutter,
        "open",
        # fmt: on
    )

    yield from user_data.set_state_plan(
        "Ready for BlackFly direct beam visualization mode"
    )
    ts = str(datetime.datetime.now())
    yield from bps.mv(
        # fmt: off
        user_data.time_stamp,
        ts,
        user_data.macro_file_time,
        ts,
        user_data.scanning,
        0,
        user_data.collection_in_progress,
        0,
        blackfly_det.cam.acquire,
        1,
        # we are using Blackfly now, let's start it...
        # fmt: on
    )


def mode_USAXS(md=None):
    """
    Set the instrument to USAXS mode.

    Parameters
    ----------
    md : dict, optional
        Metadata dictionary for the scan.
    """
    yield from user_data.set_state_plan("Moving USAXS to USAXS mode")

    yield from bps.mv(
        # fmt: off
        usaxs_shutter,
        "close",
        # fmt: on
    )

    yield from MONO_FEEDBACK_ON()

    # retune_needed = False

    if not confirm_instrument_mode("USAXS in beam"):
        mode_now = terms.SAXS.UsaxsSaxsMode.get(as_string=True)
        logger.debug(f"Found UsaxsSaxsMode = {mode_now}")
        logger.info("Moving to USAXS mode ... please wait ...")
        yield from move_WAXSOut()
        yield from move_SAXSOut()
        yield from move_USAXSIn()
        # retune_needed = True

    yield from insertScanFilters()  # not appropriate?

    # this mostly checks if we were not in USAXS mode in wrong place (e.g., radiography)
    yield from bps.mv(
        # fmt: off
        scaler0.count_mode,
        SCALER_AUTOCOUNT_MODE,
        a_stage.x,
        terms.USAXS.AX0.get(),
        m_stage.x,
        0,
        gslit_stage.x,
        terms.USAXS.AX0.get(),  # this requires AX0 and Gslits.X be the same.
        d_stage.x,
        terms.USAXS.DX0.get(),
        d_stage.y,
        terms.USAXS.dy_in.get(),
        guard_slit.h_size,
        terms.USAXS.guard_h_size.get(),
        guard_slit.v_size,
        terms.USAXS.guard_v_size.get(),
        usaxs_slit.h_size,
        terms.USAXS.usaxs_h_size.get(),
        usaxs_slit.v_size,
        terms.USAXS.usaxs_v_size.get(),
        blackfly_det.cam.acquire,
        0,  # stop Blackfly if it is running...
        # fmt: on
    )

    logger.debug("Prepared for USAXS mode")
    yield from user_data.set_state_plan("USAXS Mode")
    ts = str(datetime.datetime.now())
    yield from bps.mv(
        # fmt: off
        user_data.time_stamp,
        ts,
        user_data.macro_file_time,
        ts,
        user_data.scanning,
        0,
        # fmt: on
    )

    # #if retune_needed:
    #     # don't tune here
    #     # Instead, set a signal to be caught by the plan in the RunEngine
    #     yield from bps.mv(terms.USAXS.retune_needed, True)


# def mode_SBUSAXS():  # TODO:
mode_SBUSAXS = mode_USAXS  # for now


def mode_SAXS(md=None):
    """
    Set the instrument to SAXS mode.

    Parameters
    ----------
    md : dict, optional
        Metadata dictionary for the scan.
    """
    yield from user_data.set_state_plan("Moving USAXS to SAXS mode")

    yield from bps.mv(
        # fmt: off
        usaxs_shutter,
        "close",
        # laser.enable,  0,
        m_stage.x,
        0,
        gslit_stage.x,
        terms.USAXS.AX0.get(),  # this requires AX0 and Gslits.X be the same.
        # fmt: on
    )

    if not confirm_instrument_mode("SAXS in beam"):
        mode_now = terms.SAXS.UsaxsSaxsMode.get(as_string=True)
        logger.debug(f"Found UsaxsSaxsMode = {mode_now}")
        logger.info("Moving to SAXS mode ... please wait ...")
        yield from move_WAXSOut()
        yield from move_USAXSOut()
        yield from move_SAXSIn()

    logger.debug("Prepared for SAXS mode")
    # insertScanFilters
    yield from user_data.set_state_plan("SAXS Mode")
    ts = str(datetime.datetime.now())
    yield from bps.mv(
        # fmt: off
        user_data.time_stamp,
        ts,
        user_data.macro_file_time,
        ts,
        user_data.scanning,
        0,
        # fmt: on
    )


def mode_WAXS(md=None):
    """
    Set the instrument to WAXS mode.

    Parameters
    ----------
    md : dict, optional
        Metadata dictionary for the scan.
    """
    yield from user_data.set_state_plan("Moving USAXS to WAXS mode")

    yield from bps.mv(
        # fmt: off
        usaxs_shutter,
        "close",
        m_stage.x,
        0,
        gslit_stage.x,
        terms.USAXS.AX0.get(),  # this requires AX0 and Gslits.X be the same.
        # laser.enable,  0,
        # fmt: on
    )

    if confirm_instrument_mode("WAXS in beam"):
        logger.debug("WAXS is in beam")
    else:
        mode_now = terms.SAXS.UsaxsSaxsMode.get(as_string=True)
        logger.debug(f"Found UsaxsSaxsMode = {mode_now}")
        logger.info("Moving to WAXS mode ... please wait ...")
        yield from move_SAXSOut()
        yield from move_USAXSOut()
        yield from move_WAXSIn()

    logger.debug("Prepared for WAXS mode")
    # insertScanFilters
    yield from user_data.set_state_plan("WAXS Mode")
    ts = str(datetime.datetime.now())
    yield from bps.mv(
        # fmt: off
        user_data.time_stamp,
        ts,
        user_data.macro_file_time,
        ts,
        user_data.scanning,
        0,
        # fmt: on
    )


def mode_Radiography(md=None):
    """
    Put the instrument in USAXS Radiography mode.

    Parameters
    ----------
    md : dict, optional
        Metadata dictionary for the scan.
    """
    yield from mode_USAXS()

    logger.info("Moving to Radiography mode ... please wait ...")

    yield from MONO_FEEDBACK_ON()

    yield from bps.mv(
        # fmt: off
        # move to ccd position
        user_data.collection_in_progress,
        1,
        d_stage.x,
        terms.USAXS.ccd.dx.get(),
        d_stage.y,
        terms.USAXS.ccd.dy.get(),
        # make sure slits are in place
        usaxs_slit.v_size,
        terms.SAXS.usaxs_v_size.get(),
        usaxs_slit.h_size,
        terms.SAXS.usaxs_h_size.get(),
        guard_slit.v_size,
        terms.SAXS.usaxs_guard_v_size.get(),
        guard_slit.h_size,
        terms.SAXS.usaxs_guard_h_size.get(),
        # fmt: on
    )

    yield from insertRadiographyFilters()

    # when all that is complete, then ...
    ts = str(datetime.datetime.now())
    yield from bps.mv(
        # fmt: off
        usaxs_shutter,
        "open",
        # usaxs_shutter, "open",
        user_data.time_stamp,
        ts,
        user_data.macro_file_time,
        ts,
        user_data.scanning,
        0,
        user_data.collection_in_progress,
        0,
        blackfly_det.cam.acquire,
        1,  # we are using Blackfly now, let's start it...
        # fmt: on
    )

    yield from user_data.set_state_plan("Radiography Mode")
    logger.info("Instrument is configured for Radiography now.")
    if diagnostics.PSS.e_beam_ready.get() not in (1, "ON"):
        logger.warning("Not permitted to open mono shutter now.")
        logger.info("Open the mono shutter manually when permitted.")
    else:
        yield from bps.mv(
            mono_shutter,
            "open",
        )
        if mono_shutter.state == "open":
            logger.info("TV should now show Radiography CCD image.")
            print(
                "But before calling if you do not see an image:"
                "\n - are you CERTAIN the sample is not blocking the beam?"
                "\nMove sample out and try RE(tune_usaxs_optics()) again."
                "\n"
                "\nIf still no image on the CCD, check:"
                "\n"
                "\n* Beam on? APS up and running?"
                "\n* Shutters opened?"
                "\n* Sample/holder out of beam?"
                "\n"
                "\nIf all is OK, try running RE(tune_usaxs_optics())."
                "\nIf USAXStune worked? Run RE(mode_Radiography())."
                "\n"
                "\nStill not working? Call Jan."
            )
        else:
            logger.info("The mono shutter is closed now.  APS beam dump?")


def mode_Imaging(md=None):
    """
    Prepare the instrument for USAXS imaging.

    Parameters
    ----------
    md : dict, optional
        Metadata dictionary for the scan.
    """
    # see: /share1/USAXS_data/2019-02/USAXS_user_macros.mac
    # there it calls useModeUSAXS so that's what we'll do here
    yield from user_data.set_state_plan(
        "Moving USAXS to Imaging mode (same as USAXS mode now)"
    )
    yield from mode_USAXS()


def mode_OpenBeamPath(md=None):
    """
    Set the instrument to Open Beam Path mode.

    Parameters
    ----------
    md : dict, optional
        Metadata dictionary for the scan.
    """
    yield from user_data.set_state_plan("Moving USAXS to OpenBeamPath mode")
    yield from bps.mv(
        usaxs_shutter,
        "close",
        # laser.enable,  0,
    )

    if not confirm_instrument_mode("out of beam"):
        mode_now = terms.SAXS.UsaxsSaxsMode.get(as_string=True)
        logger.debug(f"Found UsaxsSaxsMode = {mode_now}")
        logger.info("Opening the beam path, moving all components out")
        yield from move_SAXSOut()
        yield from move_WAXSOut()
        yield from move_USAXSOut()
        yield from user_data.set_state_plan("USAXS moved to OpenBeamPath mode")
