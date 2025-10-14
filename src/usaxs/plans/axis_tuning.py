"""
Plans for axis tuning in USAXS.

This module provides functions for tuning and calibrating various instrument axes
and stages. It includes functions for tuning monochromator, analyzer, detector,
and other optical components. The tuning process involves finding optimal positions
for maximum signal intensity.

Note: Don't use blocking calls here
"""

import logging
import time
from typing import Any
from typing import Dict
from typing import Optional

from apsbits.core.instrument_init import oregistry
from apstools.callbacks.scan_signal_statistics import SignalStatsCallback
from apstools.plans import lineup2
from apstools.utils import trim_plot_by_name
from bluesky import plan_stubs as bps

from .amplifiers_plan import autoscale_amplifiers
from .mode_changes import mode_USAXS
from .requested_stop import IfRequestedStopBeforeNextScan

# Device instances
I0_controls = oregistry["I0_controls"]
I00_controls = oregistry["I00_controls"]
upd_controls = oregistry["upd_controls"]

terms = oregistry["terms"]
scaler0 = oregistry["scaler0"]
mono_shutter = oregistry["mono_shutter"]
usaxs_shutter = oregistry["usaxs_shutter"]
a_stage = oregistry["a_stage"]
# axis_tune_range = oregistry["axis_tune_range"]
d_stage = oregistry["d_stage"]
m_stage = oregistry["m_stage"]
d_stage = oregistry["d_stage"]
m_stage = oregistry["m_stage"]
s_stage = oregistry["s_stage"]
usaxs_q_calc = oregistry["usaxs_q_calc"]
UPD_SIGNAL = oregistry["UPD_SIGNAL"]
UPD = oregistry["UPD"]
I0_SIGNAL = oregistry["I0_SIGNAL"]
I0 = oregistry["I0"]
scaler0 = oregistry["scaler0"]
upd_photocurrent_calc = oregistry["upd_photocurrent_calc"]

upd_photocurrent_calc = oregistry["upd_photocurrent_calc"]
I0_photocurrent_calc = oregistry["I0_photocurrent_calc"]

user_data = oregistry["user_data"]
monochromator = oregistry["monochromator"]
usaxs_shutter = oregistry["usaxs_shutter"]

logger = logging.getLogger(__name__)


# Register user override for USAXS minimum step
# user_override.register("usaxs_minstep")  # what is this for?


# Set empty plan for channel-cut crystals
# if m_stage.isChannelCut:
#     m_stage.r2p.tuner = empty_plan
#     m_stage.r2p.pre_tune_method = empty_plan
#     m_stage.r2p.post_tune_method = empty_plan
#     tune_m2rp = empty_plan


def tune_mr(md: Optional[Dict[str, Any]] = None):
    """Tune the monochromator rotation."""
    if md is None:
        md = {}

    yield from IfRequestedStopBeforeNextScan()
    # success = False
    try:
        yield from bps.mv(usaxs_shutter, "open")
        yield from bps.mv(scaler0.preset_time, 0.1)
        yield from bps.mv(upd_controls.auto.mode, "manual")
        md["plan_name"] = "tune_mr"
        logger.info(f"tuning axis: {m_stage.r.name}")

        yield from autoscale_amplifiers([upd_controls, I0_controls])
        scaler0.select_channels(["I0"])
        trim_plot_by_name(5)
        stats = SignalStatsCallback()
        yield from lineup2(
            [I0, scaler0],
            m_stage.r,
            -m_stage.r.tune_range.get(),
            m_stage.r.tune_range.get(),
            31,
            nscans=1,
            signal_stats=stats,
            md=md,
        )
        print(stats.report())
        yield from bps.mv(
            usaxs_shutter,
            "close",
            scaler0.count_mode,
            "AutoCount",
            upd_controls.auto.mode,
            "auto+background",
        )
        scaler0.select_channels()
        # success = stats.analysis.success
        if stats.analysis.success:
            yield from bps.mv(terms.USAXS.mr_val_center, m_stage.r.position)
            logger.debug(f"final position: {m_stage.r.position}")
        else:
            print(f"tune_mr failed for {stats.analysis.reasons}")

    except Exception as e:
        logger.error(f"Error in tune_mr: {e}")
        raise
    finally:
        yield from bps.mv(usaxs_shutter, "close")

    # return success


def tune_ar(md: Optional[Dict[str, Any]] = None):
    """
    Tune the AR stage.

    This function tunes the analyzer rotation stage by finding the optimal position
    for maximum signal intensity. It includes setting up the scaler, configuring
    the detector controls, and performing a lineup scan.

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
    success = False
    try:
        yield from bps.mv(usaxs_shutter, "open")
        yield from bps.mv(scaler0.preset_time, 0.1)
        yield from bps.mv(upd_controls.auto.mode, "manual")
        md["plan_name"] = "tune_ar"
        yield from IfRequestedStopBeforeNextScan()
        logger.info(f"tuning axis: {a_stage.r.name}")
        # axis_start = a_stage.r.position
        yield from bps.mv(
            mono_shutter,
            "open",
            usaxs_shutter,
            "open",
        )
        yield from autoscale_amplifiers([upd_controls, I0_controls])
        trim_plot_by_name(5)
        scaler0.select_channels(["UPD"])
        stats = SignalStatsCallback()
        yield from lineup2(
            [UPD, scaler0],
            a_stage.r,
            -a_stage.r.tune_range.get(),
            a_stage.r.tune_range.get(),
            31,
            nscans=1,
            signal_stats=stats,
            md=md,
        )
        print(stats.report())
        yield from bps.mv(
            usaxs_shutter,
            "close",
            scaler0.count_mode,
            "AutoCount",
            upd_controls.auto.mode,
            "auto+background",
        )
        scaler0.select_channels()
        success = stats.analysis.success
        print(f"Result: {success}")
        if success:
            yield from bps.mv(
                # fmt: off
                terms.USAXS.ar_val_center,
                a_stage.r.position,
                usaxs_q_calc.channels.B.input_value,
                a_stage.r.position,
                # fmt: on
            )
            logger.debug(f"final position: {a_stage.r.position}")
        else:
            logger.info(f"tune_ar failed for {stats.analysis.reasons}")

    except Exception as e:
        logger.error(f"Error in tune_ar: {str(e)}")
        raise

    # return success


def find_ar(md: Optional[Dict[str, Any]] = None):
    """
    Tune the AR stage with adaptive range.

    This function tunes the analyzer rotation stage by finding the optimal position
    for maximum signal intensity. It includes setting up the scaler, configuring
    the detector controls, and performing a lineup scan.

    Uses adaptive scanning to search over originally large range narrowing closer and closer 
    uses lineup2 algorith and allows for up to 5 scans. 

    uses upd_photocurrent_calc = oregistry["upd_photocurrent_calc"]
    - optionally this is I0: I0_photocurrent_calc = oregistry["I0_photocurrent_calc"]

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
    success = False
    try:
        yield from bps.mv(usaxs_shutter, "open")
        yield from bps.mv(scaler0.preset_time, 0.1)
        #yield from bps.mv(upd_controls.auto.mode, "manual")
        md["plan_name"] = "find_ar"
        yield from IfRequestedStopBeforeNextScan()
        logger.info(f"tuning axis: {a_stage.r.name}")
        # axis_start = a_stage.r.position
        yield from bps.mv(
            mono_shutter,
            "open",
            usaxs_shutter,
            "open",
            upd_controls.auto.mode,
            "auto+background",  #set UPD amlifier to autorange to auto_background setting so we do not top the UPD
        )
        #yield from autoscale_amplifiers([upd_controls, I0_controls])
        trim_plot_by_name(5)
        # control BEC plotting since we use upd_photocurrent_calc
        #upd_photocurrent_calc.kind = "hinted" # set kind to inlcude in plotting by BEC
        #upd_photocurrent_calc.channels.kind = "hinted" # set kind to inlcude in plotting by BEC
        #upd_photocurrent_calc.channels.A.kind = "hinted" # set kind to inlcude in plotting by BEC
        scaler0.kind = "normal"
        scaler0.select_channels([])         # no scaler channels to be plotted (sets 'kinnd=normal' for all channels)
        stats = SignalStatsCallback()
        yield from lineup2(
            [upd_photocurrent_calc, scaler0],
            a_stage.r,
            -5*a_stage.r.tune_range.get(),
            5*a_stage.r.tune_range.get(),
            41,
            nscans=5,
            signal_stats=stats,
            md=md,
        )
        print(stats.report())
        yield from bps.mv(
            usaxs_shutter,
            "close",
            scaler0.count_mode,
            "AutoCount",
            upd_controls.auto.mode,
            "auto+background",
        )
        scaler0.select_channels()
        success = stats.analysis.success
        print(f"Result: {success}")
        if success:
            yield from bps.mv(
                # fmt: off
                terms.USAXS.ar_val_center,
                a_stage.r.position,
                usaxs_q_calc.channels.B.input_value,
                a_stage.r.position,
                # fmt: on
            )
            logger.debug(f"final position: {a_stage.r.position}")
        else:
            logger.info(f"find_ar failed for {stats.analysis.reasons}")

    except Exception as e:
        logger.error(f"Error in find_ar: {str(e)}")
        raise

    # return success


def tune_a2rp(md: Optional[Dict[str, Any]] = None):
    """
    Tune the A2RP stage.

    This function tunes the analyzer second rotation piezo stage by finding the
    optimal position for maximum signal intensity. It includes setting up the
    scaler, configuring the detector controls, and performing a lineup scan.

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
    # success = False
    try:
        yield from bps.mv(usaxs_shutter, "open")
        yield from bps.sleep(0.1)  # piezo is fast, give the system time to react
        yield from bps.mv(scaler0.preset_time, 0.1)
        yield from bps.mv(upd_controls.auto.mode, "manual")
        md["plan_name"] = "tune_a2rp"
        yield from IfRequestedStopBeforeNextScan()
        logger.info(f"tuning axis: {a_stage.r2p.name}")
        # axis_start = a_stage.r2p.position
        yield from bps.mv(
            mono_shutter,
            "open",
            usaxs_shutter,
            "open",
        )
        yield from autoscale_amplifiers([upd_controls, I0_controls])
        scaler0.select_channels(["UPD"])
        trim_plot_by_name(5)
        stats = SignalStatsCallback()
        yield from lineup2(
            [UPD, scaler0],
            a_stage.r2p,
            -a_stage.r2p.tune_range.get(),
            a_stage.r2p.tune_range.get(),
            31,
            nscans=1,
            signal_stats=stats,
            md=md,
        )
        print(stats.report())
        yield from bps.mv(
            usaxs_shutter,
            "close",
            scaler0.count_mode,
            "AutoCount",
            upd_controls.auto.mode,
            "auto+background",
        )
        scaler0.select_channels()
        # success = stats.analysis.success
        if stats.analysis.success:
            logger.debug(f"final position: {a_stage.r2p.position}")
        else:
            print(f"tune_a2rp failed for {stats.analysis.reasons}")

    except Exception as e:
        logger.error(f"Error in tune_a2rp: {str(e)}")
        raise

    # return success


def tune_dx(md: Optional[Dict[str, Any]] = None):
    """
    Tune the DX stage.

    This function tunes the detector X stage by finding the optimal position
    for maximum signal intensity. It includes setting up the scaler, configuring
    the detector controls, and performing a lineup scan.

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
        yield from bps.mv(usaxs_shutter, "open")
        yield from bps.sleep(0.1)  # piezo is fast, give the system time to react
        yield from bps.mv(scaler0.preset_time, 0.1)
        yield from bps.mv(upd_controls.auto.mode, "manual")
        md["plan_name"] = "tune_dx"
        yield from IfRequestedStopBeforeNextScan()
        logger.info(f"tuning axis: {d_stage.x.name}")
        # axis_start = d_stage.x.position
        yield from bps.mv(
            mono_shutter,
            "open",
            usaxs_shutter,
            "open",
        )
        yield from autoscale_amplifiers([upd_controls, I0_controls])
        trim_plot_by_name(5)
        scaler0.select_channels(["UPD"])
        stats = SignalStatsCallback()
        yield from lineup2(
            [UPD, scaler0],
            d_stage.x,
            -d_stage.x.tune_range.get(),
            d_stage.x.tune_range.get(),
            31,
            nscans=1,
            signal_stats=stats,
            md=md,
        )
        print(stats.report())
        yield from bps.mv(
            usaxs_shutter,
            "close",
            scaler0.count_mode,
            "AutoCount",
            upd_controls.auto.mode,
            "auto+background",
        )
        scaler0.select_channels()
        if stats.analysis.success:
            yield from bps.mv(
                terms.USAXS.DX0,
                d_stage.x.position,
            )
            logger.info(f"final position: {d_stage.x.position}")
        else:
            logger.info(f"tune_dx failed for {stats.analysis.reasons}")

    except Exception as e:
        logger.error(f"Error in tune_dx: {str(e)}")
        raise


def tune_dy(md: Optional[Dict[str, Any]] = None):
    """
    Tune the DY stage.

    This function tunes the detector Y stage by finding the optimal position
    for maximum signal intensity. It includes setting up the scaler, configuring
    the detector controls, and performing a lineup scan.

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
        yield from bps.mv(usaxs_shutter, "open")
        yield from bps.sleep(0.1)  # piezo is fast, give the system time to react
        yield from bps.mv(scaler0.preset_time, 0.1)
        yield from bps.mv(upd_controls.auto.mode, "manual")
        md["plan_name"] = "tune_dy"
        yield from IfRequestedStopBeforeNextScan()
        logger.info(f"tuning axis: {d_stage.y.name}")
        # axis_start = d_stage.y.position
        yield from bps.mv(
            mono_shutter,
            "open",
            usaxs_shutter,
            "open",
        )
        yield from autoscale_amplifiers([upd_controls, I0_controls])
        scaler0.select_channels(["UPD"])
        trim_plot_by_name(5)
        stats = SignalStatsCallback()
        yield from lineup2(
            [UPD, scaler0],
            d_stage.y,
            -d_stage.y.tune_range.get(),
            d_stage.y.tune_range.get(),
            31,
            nscans=1,
            signal_stats=stats,
            md=md,
        )
        print(stats.report())
        yield from bps.mv(
            usaxs_shutter,
            "close",
            scaler0.count_mode,
            "AutoCount",
            upd_controls.auto.mode,
            "auto+background",
        )
        scaler0.select_channels()
        if stats.analysis.success:
            yield from bps.mv(terms.SAXS.dy_in, d_stage.y.position)
            logger.info(f"final position: {d_stage.y.position}")
        else:
            logger.info(f"tune_dy failed for {stats.analysis.reasons}")

    except Exception as e:
        logger.error(f"Error in tune_dy: {str(e)}")
        raise


def tune_diode(md: Optional[Dict[str, Any]] = None):
    """
    Tune both DX and DY stages.

    This function tunes both the detector X and Y stages by finding the optimal
    positions for maximum signal intensity. It calls tune_dx and tune_dy in
    sequence.

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
        yield from tune_dx(md=md)
        yield from tune_dy(md=md)

    except Exception as e:
        logger.error(f"Error in tune_diode: {str(e)}")
        raise


def tune_usaxs_optics(side: bool = False, md: Optional[Dict[str, Any]] = None):
    """
    Tune all USAXS optics.

    This function tunes all the optical components needed for USAXS measurements.
    It includes tuning the monochromator, analyzer, and detector stages in the
    correct sequence.

    Parameters
    ----------
    side : bool, optional
        Whether to tune side-bounce components, by default False
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

        yield from tune_mr(md=md)
        # yield from tune_m2rp(md=md)
        # if side:
        #     yield from tune_msrp(md=md)
        #     yield from tune_asrp(md=md)
        yield from tune_ar(md=md)
        yield from tune_a2rp(md=md)

        yield from bps.mv(
            terms.preUSAXStune.num_scans_last_tune,
            0,
            terms.preUSAXStune.epoch_last_tune,
            time.time(),
        )

    except Exception as e:
        logger.error(f"Error in tune_usaxs_optics: {str(e)}")
        raise


def tune_saxs_optics(md: Optional[Dict[str, Any]] = None):
    """
    Tune all SAXS optics.

    This function tunes all the optical components needed for SAXS measurements.
    It includes tuning the monochromator and analyzer stages in the correct sequence.

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
        yield from tune_mr(md=md)
        # yield from tune_m2rp(md=md)
        yield from bps.mv(
            terms.preUSAXStune.epoch_last_tune,
            time.time(),
        )

    except Exception as e:
        logger.error(f"Error in tune_saxs_optics: {str(e)}")
        raise


def instrument_default_tune_ranges():
    """
    Set default tune ranges for all tunable axes.

    This function sets the default tuning ranges for all tunable axes based on
    the current monochromator energy. The ranges are optimized for different
    energy ranges and crystal types.

    Yields
    ------
    Generator[Any, None, None]
        A generator that yields plan steps
    """
    try:
        yield from bps.null()

        # The commented code below contains the original tuning range logic
        # It's kept for reference but disabled as it's now handled elsewhere
        """
        if monochromator.dcm.energy.position < 10.99:  # ~ 10 keV for Si 220 crystals
            m_stage.r.tuner.width = 0.005
            a_stage.r.tuner.width = 0.003
            m_stage.r2p.tuner.width = 10
            a_stage.r2p.tuner.width = 7
            minstep = user_override.pick("usaxs_minstep", 0.000045)
            logger.info("Setting minstep to %s", minstep)
            yield from bps.mv(terms.USAXS.usaxs_minstep, minstep)

        elif 10.99 <= monochromator.dcm.energy.position < 12.99:   # Si 220 crystals
            m_stage.r.tuner.width = 0.005
            a_stage.r.tuner.width = 0.0025
            m_stage.r2p.tuner.width = 9
            a_stage.r2p.tuner.width = 8
            minstep = user_override.pick("usaxs_minstep", 0.000035)
            logger.info("Setting minstep to %s", minstep)
            yield from bps.mv(terms.USAXS.usaxs_minstep, minstep)

        elif 12.99 <= monochromator.dcm.energy.position < 18.1:   # Si 220 crystals
            m_stage.r.tuner.width = 0.005
            a_stage.r.tuner.width = 0.0022
            m_stage.r2p.tuner.width = 8
            a_stage.r2p.tuner.width = 7
            minstep = user_override.pick("usaxs_minstep", 0.000025)
            logger.info("Setting minstep to %s", minstep)
            yield from bps.mv(terms.USAXS.usaxs_minstep, minstep)

        elif 18.1 <= monochromator.dcm.energy.position < 20.8:   # Si 220 crystals
            m_stage.r.tuner.width = 0.005
            a_stage.r.tuner.width = 0.002
            m_stage.r2p.tuner.width = 8
            a_stage.r2p.tuner.width = 6
            minstep = user_override.pick("usaxs_minstep", 0.000025)
            logger.info("Setting minstep to %s", minstep)
            yield from bps.mv(terms.USAXS.usaxs_minstep, minstep)

        elif 20.8 <= monochromator.dcm.energy.position:   # Si 220 or 440 crystals
            if m_stage.r.user_readback.value >= 11 :
                #Si 440 crystals
                m_stage.r.tuner.width = 0.005
                a_stage.r.tuner.width = 0.0006
                m_stage.r2p.tuner.width = 8
                a_stage.r2p.tuner.width = 1.5
                minstep = user_override.pick("usaxs_minstep", 0.000006)
                logger.info("Setting minstep to %s", minstep)
                yield from bps.mv(terms.USAXS.usaxs_minstep, minstep)

            else:
                #Si 220 crystals
                m_stage.r.tuner.width = 0.005
                a_stage.r.tuner.width = 0.0018
                m_stage.r2p.tuner.width = 8
                a_stage.r2p.tuner.width = 12
                minstep = user_override.pick("usaxs_minstep", 0.00002)
                logger.info("Setting minstep to %s", minstep)
                yield from bps.mv(terms.USAXS.usaxs_minstep, minstep)
        """

    except Exception as e:
        logger.error(f"Error in instrument_default_tune_ranges: {str(e)}")
        raise


def update_EPICS_tuning_widths():
    """
    Update the tuning widths in EPICS PVs from local settings.

    This function updates the EPICS process variables with the current tuning
    width settings from the local device objects.

    Yields
    ------
    Generator[Any, None, None]
        A generator that yields plan steps
    """
    try:
        yield from bps.null()
        # The commented code below contains the original update logic
        # It's kept for reference but disabled as it's now handled elsewhere
        """
        yield from bps.mv(
            axis_tune_range.mr,     m_stage.r.tuner.width,
            axis_tune_range.ar,     a_stage.r.tuner.width,
            axis_tune_range.m2rp,   m_stage.r2p.tuner.width,
            axis_tune_range.a2rp,   a_stage.r2p.tuner.width,
            axis_tune_range.msrp,   ms_stage.rp.tuner.width,
            axis_tune_range.asrp,   as_stage.rp.tuner.width,
        )
        """

    except Exception as e:
        logger.error(f"Error in update_EPICS_tuning_widths: {str(e)}")
        raise


def user_defined_settings():
    """
    Allow users to redefine instrument defaults.

    This function is called from beforePlan() (in 50-plans.py) at the start of
    every batch set of measurements. Users can override any instrument defaults
    here, such as tuning ranges for various optical axes.

    Note: Don't use blocking calls here. It is important that the user not use
    any blocking calls such as setting or getting PVs in EPICS. Blocking calls
    will block the python interpreter for long periods (such as time.sleep())
    or make direct calls for EPICS or file I/O that interrupt how the Bluesky
    RunEngine operates.

    Yields
    ------
    Generator[Any, None, None]
        A generator that yields plan steps
    """
    try:
        yield from bps.null()

    except Exception as e:
        logger.error(f"Error in user_defined_settings: {str(e)}")
        raise
