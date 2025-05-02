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

import logging
from typing import Any
from typing import Dict
from typing import Generator
from typing import Optional

from apsbits.utils.config_loaders import get_config
from apsbits.utils.controls_setup import oregistry
from apstools.devices import SCALER_AUTOCOUNT_MODE
from bluesky import plan_stubs as bps
from bluesky import preprocessors as bpp
from ophyd.scaler import ScalerCH

from .filter_plans import insertRadiographyFilters
from .filter_plans import insertScanFilters
from .move_instrument import UsaxsSaxsModes
from .move_instrument import move_SAXSIn
from .move_instrument import move_SAXSOut
from .move_instrument import move_USAXSOut
from .move_instrument import move_WAXSIn
from .move_instrument import move_WAXSOut

logger = logging.getLogger(__name__)
logger.info(__file__)

iconfig = get_config()
scaler0_name = iconfig.get("SCALER_PV_NAMES", {}).get("SCALER0_NAME")

scaler0 = ScalerCH(scaler0_name, name="scaler0")
scaler0.stage_sigs["count_mode"] = "OneShot"
scaler0.select_channels()


# Device instances
a_stage = oregistry["a_stage"]
d_stage = oregistry["d_stage"]
guard_slit = oregistry["guard_slit"]
m_stage = oregistry["m_stage"]
mono_shutter = oregistry["mono_shutter"]
terms = oregistry["terms"]
usaxs_shutter = oregistry["usaxs_shutter"]
usaxs_slit = oregistry["usaxs_slit"]
user_data = oregistry["user_device"]


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


# def mode_BlackFly(
#     md: Optional[Dict[str, Any]] = None,
# ) -> Generator[Any, None, None]:
#     """
#     Set instrument to imaging mode for direct beam using BlackFly camera.

#     This mode configures the instrument for direct beam imaging using the BlackFly
#     camera. It includes setting up the correct stage positions, inserting appropriate
#     filters, and configuring the camera for acquisition.

#     Parameters
#     ----------
#     md : Optional[Dict[str, Any]], optional
#         Metadata dictionary to be added to the scan, by default None

#     Yields
#     ------
#     Generator[Any, None, None]
#         A generator that yields plan steps
#     """
#     if md is None:
#         md = {}

#     try:
#         yield from mode_USAXS()
#         yield from DCMfeedbackON()
#         yield from user_data.set_state_plan("Preparing for BlackFly imaging mode")

#         yield from bps.mv(
#             d_stage.x,
#             terms.USAXS.blackfly.dx.get(),
#             d_stage.y,
#             terms.USAXS.blackfly.dy.get(),
#             m_stage.x,
#             -200,
#             a_stage.x,
#             -200,
#             guard_slit.x,
#             0,
#         )

#         yield from insertBlackflyFilters()
#         yield from bps.mv(
#             usaxs_shutter,
#             "open",
#         )

#         yield from user_data.set_state_plan("Ready for BlackFly imaging mode")
#         ts = str(datetime.datetime.now())
#         yield from bps.mv(
#             user_data.time_stamp,
#             ts,
#             user_data.macro_file_time,
#             ts,
#             user_data.scanning,
#             0,
#             user_data.collection_in_progress,
#             0,
#             blackfly_det.cam.acquire,
#             1,  # Start BlackFly acquisition
#         )
#     except Exception as e:
#         logger.error(f"Error in mode_BlackFly: {str(e)}")
#         raise


def mode_USAXS(
    md: Optional[Dict[str, Any]] = None,
    RE: Optional[Any] = None,
    bec: Optional[Any] = None,
    specwriter: Optional[Any] = None,
) -> Generator[Any, None, Any]:
    """Change instrument to USAXS mode.

    This function changes the instrument configuration to USAXS mode
    and sets up the appropriate devices and detectors.

    Parameters
    ----------
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

    USAGE:  ``RE(mode_USAXS())``
    """
    if md is None:
        md = {}
    if RE is None:
        raise ValueError("RunEngine instance must be provided")
    if bec is None:
        raise ValueError("Bluesky Live Callbacks instance must be provided")
    if specwriter is None:
        raise ValueError("SPEC file writer instance must be provided")

    _md = {}
    _md.update(md or {})

    @bpp.run_decorator(md=_md)
    def _inner() -> Generator[Any, None, Any]:
        yield from user_data.set_state_plan("changing to USAXS mode")
        yield from bps.mv(scaler0.count_mode, "OneShot")
        yield from bps.trigger(scaler0, group="mode_change")
        yield from bps.wait(group="mode_change")

    return (yield from _inner())


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
        # yield from IfRequestedStopBeforeNextScan() #this function does not exist

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


def mode_WAXS() -> Generator[Any, None, None]:
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

    try:
        yield from user_data.set_state_plan("Preparing for WAXS mode")
        # yield from IfRequestedStopBeforeNextScan() #function needs to be discussed

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


def mode_Radiography() -> Generator[Any, None, None]:
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
    try:
        yield from user_data.set_state_plan("Preparing for Radiography mode")
        # yield from IfRequestedStopBeforeNextScan() #function needs to be discussed

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
            usaxs_shutter,
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


def mode_Imaging() -> Generator[Any, None, None]:
    """
    Set instrument to Imaging mode.

    This mode configures the instrument for imaging measurements. It includes
    setting up the correct stage positions, inserting appropriate filters, and
    configuring the detector for acquisition.

    Parameters
    ----------

    Yields
    ------
    Generator[Any, None, None]
        A generator that yields plan steps
    """

    try:
        yield from user_data.set_state_plan("Preparing for Imaging mode")
        # yield from IfRequestedStopBeforeNextScan()

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
            usaxs_shutter,
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


def mode_OpenBeamPath() -> Generator[Any, None, None]:
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

    try:
        yield from user_data.set_state_plan("Preparing for Open Beam Path mode")
        # yield from IfRequestedStopBeforeNextScan()

        # Move stages out of beam path
        yield from move_USAXSOut()
        yield from move_SAXSOut()
        yield from move_WAXSOut()

        # Open shutters
        yield from bps.mv(
            usaxs_shutter,
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
