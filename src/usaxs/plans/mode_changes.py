"""
Support the different instrument modes.

This module provides functions to switch between different instrument modes:
- USAXS (Ultra Small Angle X-ray Scattering)
- SAXS (Small Angle X-ray Scattering)
- WAXS (Wide Angle X-ray Scattering)
- BlackFly (Imaging mode)
- Radiography
- OpenBeamPath

Each mode function configures the instrument for a specific type of measurement
by setting up the correct stage positions, inserting appropriate filters, and
configuring detectors and scalers.
"""

### This file is work-in-progress
# see: https://subversion.xray.aps.anl.gov/spec/beamlines/USAXS/trunk/macros/local/usaxs_commands.mac

__all__ = """
    mode_BlackFly
    mode_Imaging
    mode_OpenBeamPath
    mode_Radiography
    mode_SAXS
    mode_SBUSAXS
    mode_USAXS
    mode_WAXS
""".split()

import datetime
import logging
from typing import Any, Dict, Generator, Optional

from apsbits.utils.controls_setup import oregistry
from apstools.devices import SCALER_AUTOCOUNT_MODE
from bluesky import plan_stubs as bps

from .filters import insertBlackflyFilters
from .filters import insertRadiographyFilters
from .filters import insertScanFilters
from .mono_feedback import DCMfeedbackON
from .move_instrument import UsaxsSaxsModes
from .move_instrument import move_SAXSIn
from .move_instrument import move_SAXSOut
from .move_instrument import move_USAXSIn
from .move_instrument import move_USAXSOut
from .move_instrument import move_WAXSIn
from .move_instrument import move_WAXSOut

logger = logging.getLogger(__name__)
logger.info(__file__)

# Constants
MONO_FEEDBACK_ON = oregistry["MONO_FEEDBACK_ON"]

# Device instances
a_stage = oregistry["a_stage"]
blackfly_det = oregistry["blackfly_det"]
ccd_shutter = oregistry["ccd_shutter"]
constants = oregistry["constants"]
d_stage = oregistry["d_stage"]
email_notices = oregistry["email_notices"]
guard_slit = oregistry["guard_slit"]
lax_autosave = oregistry["lax_autosave"]
m_stage = oregistry["m_stage"]
mono_shutter = oregistry["mono_shutter"]
monochromator = oregistry["monochromator"]
s_stage = oregistry["s_stage"]
saxs_det = oregistry["saxs_det"]
saxs_stage = oregistry["saxs_stage"]
scaler0 = oregistry["scaler0"]
scaler1 = oregistry["scaler1"]
terms = oregistry["terms"]
ti_filter_shutter = oregistry["ti_filter_shutter"]
trd_controls = oregistry["trd_controls"]
upd_controls = oregistry["upd_controls"]
usaxs_flyscan = oregistry["usaxs_flyscan"]
usaxs_q_calc = oregistry["usaxs_q_calc"]
usaxs_slit = oregistry["usaxs_slit"]
user_data = oregistry["user_data"]
user_override = oregistry["user_override"]
waxs_det = oregistry["waxs_det"]
suspend_BeamInHutch = oregistry["suspend_BeamInHutch"]
suspend_FE_shutter = oregistry["suspend_FE_shutter"]
IfRequestedStopBeforeNextScan = oregistry["IfRequestedStopBeforeNextScan"]


def confirm_instrument_mode(mode_name: str) -> bool:
    """
    Check if instrument is in the specified mode.

    Parameters
    ----------
    mode_name : str
        One of the strings defined in ``UsaxsSaxsModes``

    Returns
    -------
    bool
        True if instrument is in the named mode, False otherwise
    """
    try:
        expected_mode = UsaxsSaxsModes[mode_name]
        return terms.SAXS.UsaxsSaxsMode.get() in (expected_mode, mode_name)
    except KeyError:
        logger.error(f"Invalid mode name: {mode_name}")
        return False


# #def mode_Laser(md=None):
#     """
#     Sets to Laser distance meter mode, using AR500 laser.
#     """
#     yield from mode_OpenBeamPath()
#     yield from user_data.set_state_plan(
#         "Preparing for Laser distacne meter mode"
#         )
#     yield from bps.mv(
#         ccd_shutter,        "close",
#         d_stage.x, laser.dx.get(),
#         d_stage.y, laser.dy.get(),
#         )
#     yield from bps.mv(
#         laser.enable,  1,
#         )


def mode_BlackFly(
    md: Optional[Dict[str, Any]] = None,
) -> Generator[Any, None, None]:
    """
    Set instrument to imaging mode for direct beam using BlackFly camera.

    This mode configures the instrument for direct beam imaging using the BlackFly
    camera. It includes setting up the correct stage positions, inserting appropriate
    filters, and configuring the camera for acquisition.

    Parameters
    ----------
    md : Optional[Dict[str, Any]], optional
        Metadata dictionary to be added to the scan, by default None

    Yields
    ------
    Generator[Any, None, None]
        A generator that yields plan steps
    """
    if md is None:
        md = {}

    try:
        yield from mode_USAXS()
        yield from DCMfeedbackON()
        yield from user_data.set_state_plan("Preparing for BlackFly imaging mode")

        yield from bps.mv(
            d_stage.x,
            terms.USAXS.blackfly.dx.get(),
            d_stage.y,
            terms.USAXS.blackfly.dy.get(),
            m_stage.x,
            -200,
            a_stage.x,
            -200,
            guard_slit.x,
            0,
        )

        yield from insertBlackflyFilters()
        yield from bps.mv(
            ti_filter_shutter,
            "open",
        )

        yield from user_data.set_state_plan("Ready for BlackFly imaging mode")
        ts = str(datetime.datetime.now())
        yield from bps.mv(
            user_data.time_stamp,
            ts,
            user_data.macro_file_time,
            ts,
            user_data.scanning,
            0,
            user_data.collection_in_progress,
            0,
            blackfly_det.cam.acquire,
            1,  # Start BlackFly acquisition
        )
    except Exception as e:
        logger.error(f"Error in mode_BlackFly: {str(e)}")
        raise


def mode_USAXS(
    md: Optional[Dict[str, Any]] = None,
) -> Generator[Any, None, None]:
    """
    Set instrument to USAXS mode.

    This mode configures the instrument for Ultra Small Angle X-ray Scattering
    measurements. It includes setting up the correct stage positions, inserting
    appropriate filters, and configuring the scaler for autocount mode.

    Parameters
    ----------
    md : Optional[Dict[str, Any]], optional
        Metadata dictionary to be added to the scan, by default None

    Yields
    ------
    Generator[Any, None, None]
        A generator that yields plan steps
    """
    if md is None:
        md = {}

    try:
        yield from user_data.set_state_plan("Preparing for USAXS mode")
        yield from IfRequestedStopBeforeNextScan()

        # Move stages to USAXS positions
        yield from move_USAXSIn()
        yield from insertScanFilters()

        # Configure scaler for autocount mode
        yield from bps.mv(
            scaler0.count_mode,
            SCALER_AUTOCOUNT_MODE,
            scaler0.preset_time,
            0.1,
        )

        # Update mode in EPICS
        yield from bps.mv(
            terms.SAXS.UsaxsSaxsMode,
            UsaxsSaxsModes["USAXS"],
            user_data.scanning,
            0,
            user_data.collection_in_progress,
            0,
        )

        yield from user_data.set_state_plan("Ready for USAXS mode")

    except Exception as e:
        logger.error(f"Error in mode_USAXS: {str(e)}")
        raise


# def mode_SBUSAXS():  # TODO:
mode_SBUSAXS = mode_USAXS  # for now


def mode_SAXS(
    md: Optional[Dict[str, Any]] = None,
) -> Generator[Any, None, None]:
    """
    Set instrument to SAXS mode.

    This mode configures the instrument for Small Angle X-ray Scattering
    measurements. It includes setting up the correct stage positions, inserting
    appropriate filters, and configuring the scaler for autocount mode.

    Parameters
    ----------
    md : Optional[Dict[str, Any]], optional
        Metadata dictionary to be added to the scan, by default None

    Yields
    ------
    Generator[Any, None, None]
        A generator that yields plan steps
    """
    if md is None:
        md = {}

    try:
        yield from user_data.set_state_plan("Preparing for SAXS mode")
        yield from IfRequestedStopBeforeNextScan()

        # Move stages to SAXS positions
        yield from move_SAXSIn()
        yield from insertScanFilters()

        # Configure scaler for autocount mode
        yield from bps.mv(
            scaler0.count_mode,
            SCALER_AUTOCOUNT_MODE,
            scaler0.preset_time,
            0.1,
        )

        # Update mode in EPICS
        yield from bps.mv(
            terms.SAXS.UsaxsSaxsMode,
            UsaxsSaxsModes["SAXS"],
            user_data.scanning,
            0,
            user_data.collection_in_progress,
            0,
        )

        yield from user_data.set_state_plan("Ready for SAXS mode")

    except Exception as e:
        logger.error(f"Error in mode_SAXS: {str(e)}")
        raise


def mode_WAXS(
    md: Optional[Dict[str, Any]] = None,
) -> Generator[Any, None, None]:
    """
    Set instrument to WAXS mode.

    This mode configures the instrument for Wide Angle X-ray Scattering
    measurements. It includes setting up the correct stage positions, inserting
    appropriate filters, and configuring the scaler for autocount mode.

    Parameters
    ----------
    md : Optional[Dict[str, Any]], optional
        Metadata dictionary to be added to the scan, by default None

    Yields
    ------
    Generator[Any, None, None]
        A generator that yields plan steps
    """
    if md is None:
        md = {}

    try:
        yield from user_data.set_state_plan("Preparing for WAXS mode")
        yield from IfRequestedStopBeforeNextScan()

        # Move stages to WAXS positions
        yield from move_WAXSIn()
        yield from insertScanFilters()

        # Configure scaler for autocount mode
        yield from bps.mv(
            scaler0.count_mode,
            SCALER_AUTOCOUNT_MODE,
            scaler0.preset_time,
            0.1,
        )

        # Update mode in EPICS
        yield from bps.mv(
            terms.SAXS.UsaxsSaxsMode,
            UsaxsSaxsModes["WAXS"],
            user_data.scanning,
            0,
            user_data.collection_in_progress,
            0,
        )

        yield from user_data.set_state_plan("Ready for WAXS mode")

    except Exception as e:
        logger.error(f"Error in mode_WAXS: {str(e)}")
        raise


def mode_Radiography(
    md: Optional[Dict[str, Any]] = None,
) -> Generator[Any, None, None]:
    """
    Set instrument to Radiography mode.

    This mode configures the instrument for radiography measurements. It includes
    setting up the correct stage positions, inserting appropriate filters, and
    configuring the detector for acquisition.

    Parameters
    ----------
    md : Optional[Dict[str, Any]], optional
        Metadata dictionary to be added to the scan, by default None

    Yields
    ------
    Generator[Any, None, None]
        A generator that yields plan steps
    """
    if md is None:
        md = {}

    try:
        yield from user_data.set_state_plan("Preparing for Radiography mode")
        yield from IfRequestedStopBeforeNextScan()

        # Move stages to radiography positions
        yield from bps.mv(
            d_stage.x,
            terms.USAXS.radiography.dx.get(),
            d_stage.y,
            terms.USAXS.radiography.dy.get(),
            m_stage.x,
            -200,
            a_stage.x,
            -200,
            guard_slit.x,
            0,
        )

        yield from insertRadiographyFilters()
        yield from bps.mv(
            ti_filter_shutter,
            "open",
        )

        # Update mode in EPICS
        yield from bps.mv(
            terms.SAXS.UsaxsSaxsMode,
            UsaxsSaxsModes["Radiography"],
            user_data.scanning,
            0,
            user_data.collection_in_progress,
            0,
        )

        yield from user_data.set_state_plan("Ready for Radiography mode")

    except Exception as e:
        logger.error(f"Error in mode_Radiography: {str(e)}")
        raise


def mode_Imaging(
    md: Optional[Dict[str, Any]] = None,
) -> Generator[Any, None, None]:
    """
    Set instrument to Imaging mode.

    This mode configures the instrument for imaging measurements. It includes
    setting up the correct stage positions, inserting appropriate filters, and
    configuring the detector for acquisition.

    Parameters
    ----------
    md : Optional[Dict[str, Any]], optional
        Metadata dictionary to be added to the scan, by default None

    Yields
    ------
    Generator[Any, None, None]
        A generator that yields plan steps
    """
    if md is None:
        md = {}

    try:
        yield from user_data.set_state_plan("Preparing for Imaging mode")
        yield from IfRequestedStopBeforeNextScan()

        # Move stages to imaging positions
        yield from bps.mv(
            d_stage.x,
            terms.USAXS.imaging.dx.get(),
            d_stage.y,
            terms.USAXS.imaging.dy.get(),
            m_stage.x,
            -200,
            a_stage.x,
            -200,
            guard_slit.x,
            0,
        )

        yield from insertScanFilters()
        yield from bps.mv(
            ti_filter_shutter,
            "open",
        )

        # Update mode in EPICS
        yield from bps.mv(
            terms.SAXS.UsaxsSaxsMode,
            UsaxsSaxsModes["Imaging"],
            user_data.scanning,
            0,
            user_data.collection_in_progress,
            0,
        )

        yield from user_data.set_state_plan("Ready for Imaging mode")

    except Exception as e:
        logger.error(f"Error in mode_Imaging: {str(e)}")
        raise


def mode_OpenBeamPath(
    md: Optional[Dict[str, Any]] = None,
) -> Generator[Any, None, None]:
    """
    Set instrument to Open Beam Path mode.

    This mode configures the instrument for open beam path measurements. It includes
    moving stages out of the beam path and opening the necessary shutters.

    Parameters
    ----------
    md : Optional[Dict[str, Any]], optional
        Metadata dictionary to be added to the scan, by default None

    Yields
    ------
    Generator[Any, None, None]
        A generator that yields plan steps
    """
    if md is None:
        md = {}

    try:
        yield from user_data.set_state_plan("Preparing for Open Beam Path mode")
        yield from IfRequestedStopBeforeNextScan()

        # Move stages out of beam path
        yield from move_USAXSOut()
        yield from move_SAXSOut()
        yield from move_WAXSOut()

        # Open shutters
        yield from bps.mv(
            ti_filter_shutter,
            "open",
            mono_shutter,
            "open",
        )

        # Update mode in EPICS
        yield from bps.mv(
            terms.SAXS.UsaxsSaxsMode,
            UsaxsSaxsModes["OpenBeamPath"],
            user_data.scanning,
            0,
            user_data.collection_in_progress,
            0,
        )

        yield from user_data.set_state_plan("Ready for Open Beam Path mode")

    except Exception as e:
        logger.error(f"Error in mode_OpenBeamPath: {str(e)}")
        raise
