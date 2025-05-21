"""
user-facing scans
"""

import datetime
import logging
import os
import time
from collections import OrderedDict
from typing import Any
from typing import Dict
from typing import Optional

from .mono_feedback import MONO_FEEDBACK_OFF
from .mono_feedback import MONO_FEEDBACK_ON
from apsbits.core.instrument_init import oregistry
from apstools.devices import SCALER_AUTOCOUNT_MODE
from apstools.plans import restorable_stage_sigs
from bluesky import plan_stubs as bps
from bluesky import preprocessors as bpp
from .axis_tuning import tune_mr
from .axis_tuning import tune_ar
from .axis_tuning import tune_a2rp
from usaxs.startup import suspend_BeamInHutch
from usaxs.startup import suspend_FE_shutter
from usaxs.utils.emails import email_notices
from usaxs.utils.override_parameters import user_override
from .requested_stop import IfRequestedStopBeforeNextScan
from .mode_changes import mode_USAXS
from ..utils.a2q_q2a import q2angle
from .command_list import after_plan
from .command_list import before_plan
from .mode_changes import mode_USAXS
from .mode_changes import mode_SAXS
from .mode_changes import mode_WAXS
from .requested_stop import IfRequestedStopBeforeNextScan 
from .sample_transmission import measure_SAXS_Transmission
from .sample_transmission import measure_USAXS_Transmission
from .filter_changes import insertSaxsFilters
from .filter_changes import insertWaxsFilters
from .area_detector import areaDetectorAcquire
from .amplifiers import autoscale_amplifiers
from .I0_controls import I0_controls
from .I00_controls import I00_controls
from .upd_controls import upd_controls
from .trd_controls import trd_controls
from .sample_imaging import record_sample_image_on_demand


# from usaxs.utils.setup_new_user import cleanupText
# from usaxs.utils.setup_new_user import techniqueSubdirectory
# from usaxs.utils.user_sample_title import getSampleTitle

# # Constants
# tune_m2rp = oregistry["tune_m2rp"]
# tune_ar = oregistry["tune_ar"]
# tune_a2rp = oregistry["tune_a2rp"]
# NOTIFY_ON_BADTUNE = oregistry["NOTIFY_ON_BADTUNE"]

# tune_mr = oregistry["tune_mr"]
# uascan = oregistry["uascan"]
# NOTIFY_ON_BAD_FLY_SCAN = oregistry["NOTIFY_ON_BAD_FLY_SCAN"]

logger = logging.getLogger(__name__)


# # these two templates match each other, sort of
# AD_FILE_TEMPLATE = "%s%s_%4.4d.hdf"
# LOCAL_FILE_TEMPLATE = "%s_%04d.hdf"
MASTER_TIMEOUT = 60
# user_override.register("useDynamicTime")

# # Make sure these are not staged. For acquire_time,
# # any change > 0.001 s takes ~0.5 s for Pilatus to complete!
# DO_NOT_STAGE_THESE_KEYS___THEY_ARE_SET_IN_EPICS = """
#     acquire_time acquire_period num_images num_exposures
# """.split()

# # Device and plan instances from oregistry (allowed list)
mono_shutter = oregistry["mono_shutter"]
usaxs_shutter = oregistry["usaxs_shutter"]
# usaxs_shutter = oregistry["usaxs_shutter"]
# ar_start = oregistry["ar_start"]
guard_slit = oregistry["guard_slit"]
# lax_autosave = oregistry["lax_autosave"]
# m_stage = oregistry["m_stage"]
monochromator = oregistry["monochromator"]
terms = oregistry["terms"]
s_stage = oregistry["s_stage"]
# saxs_det = oregistry["saxs_det"]
# saxs_stage = oregistry["saxs_stage"]
# struck = oregistry["struck"]
# terms = oregistry["terms"]
# usaxs_flyscan = oregistry["usaxs_flyscan"]
# usaxs_q_calc = oregistry["usaxs_q_calc"]
usaxs_slit = oregistry["usaxs_slit"]
user_data = oregistry["user_device"]
scaler0 = oregistry["scaler0"]
# waxs_det = oregistry["waxs_det"]
m_stage = oregistry["m_stage"]
a_stage = oregistry["a_stage"]
d_stage = oregistry["d_stage"]
# flyscan_trajectories = oregistry["flyscan_trajectories"]
# # Plan helpers (if available in oregistry)
# mode_USAXS = oregistry["mode_USAXS"]
# mode_SAXS = oregistry["mode_SAXS"]
# mode_WAXS = oregistry["mode_WAXS"]
# record_sample_image_on_demand = oregistry["record_sample_image_on_demand"]
# measure_USAXS_Transmission = oregistry["measure_USAXS_Transmission"]
# measure_SAXS_Transmission = oregistry["measure_SAXS_Transmission"]
# insertSaxsFilters = oregistry["insertSaxsFilters"]
# insertWaxsFilters = oregistry["insertWaxsFilters"]
# areaDetectorAcquire = oregistry["areaDetectorAcquire"]
# autoscale_amplifiers = oregistry["autoscale_amplifiers"]
# I0_controls = oregistry["I0_controls"]
# I00_controls = oregistry["I00_controls"]
# upd_controls = oregistry["upd_controls"]
# trd_controls = oregistry["trd_controls"]
# scaler0 = oregistry["scaler0"]
# scaler1 = oregistry["scaler1"]
# constants = oregistry["constants"]
 





@bpp.suspend_decorator(suspend_FE_shutter)
@bpp.suspend_decorator(suspend_BeamInHutch)
def USAXSscan(
    x: float,
    y: float,
    thickness_mm: float,
    title: str,
    md: Optional[Dict[str, Any]] = None,
    RE: Optional[Any] = None,
    bec: Optional[Any] = None,
    specwriter: Optional[Any] = None,
):
    """
    Execute a USAXS scan at the specified position.

    Parameters
    ----------
    x : float
        X position for the scan
    y : float
        Y position for the scan
    thickness_mm : float
        Sample thickness in mm
    title : str
        Title for the scan
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
    Generator[Any, None, None]
        A generator that yields plan steps

    USAGE:  ``RE(USAXSscan(x, y, thickness_mm, title))``
    """
    if md is None:
        md = {}
    if RE is None:
        raise ValueError("RunEngine instance must be provided")
    if bec is None:
        raise ValueError("Bluesky Live Callbacks instance must be provided")
    if specwriter is None:
        raise ValueError("SPEC file writer instance must be provided")

    _md = md or OrderedDict()
    _md["sample_thickness_mm"] = thickness_mm
    _md["title"] = title
    if terms.FlyScan.use_flyscan.get():
        yield from Flyscan(x, y, thickness_mm, title, md=_md)
    else:
        yield from USAXSscanStep(x, y, thickness_mm, title, md=_md)

    yield from bps.mv(monochromator.feedback.on, MONO_FEEDBACK_ON)


def USAXSscanStep(
    pos_X: float,
    pos_Y: float,
    thickness: float,
    scan_title: str,
    md: Optional[Dict[str, Any]] = None,
    RE: Optional[Any] = None,
    bec: Optional[Any] = None,
    specwriter: Optional[Any] = None,
):
    """
    Execute a step USAXS scan at the specified position.

    Parameters
    ----------
    pos_X : float
        X position for the scan
    pos_Y : float
        Y position for the scan
    thickness : float
        Sample thickness in mm
    scan_title : str
        Title for the scan
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
    Generator[Any, None, None]
        A generator that yields plan steps

    USAGE:  ``RE(USAXSscanStep(pos_X, pos_Y, thickness, scan_title))``
    """
    if md is None:
        md = {}
    if RE is None:
        raise ValueError("RunEngine instance must be provided")
    if bec is None:
        raise ValueError("Bluesky Live Callbacks instance must be provided")
    if specwriter is None:
        raise ValueError("SPEC file writer instance must be provided")

    yield from IfRequestedStopBeforeNextScan()

    yield from mode_USAXS()

    yield from bps.mv(
        usaxs_slit.v_size,
        terms.SAXS.usaxs_v_size.get(),
        usaxs_slit.h_size,
        terms.SAXS.usaxs_h_size.get(),
        guard_slit.v_size,
        terms.SAXS.usaxs_guard_v_size.get(),
        guard_slit.h_size,
        terms.SAXS.usaxs_guard_h_size.get(),
        timeout=MASTER_TIMEOUT,
    )
    yield from before_plan()

    yield from bps.mv(
        s_stage.x,
        pos_X,
        s_stage.y,
        pos_Y,
        timeout=MASTER_TIMEOUT,
    )

    # Update Sample name. getSampleTitle is used to create proper sample name.
    # It may add time and temperature therefore it needs to be done close to real
    # data collection, after mode change and optional tuning.
    scan_title = getSampleTitle(scan_title)
    _md = md or OrderedDict()
    _md["sample_thickness_mm"] = thickness
    _md["title"] = scan_title

    scan_title_clean = cleanupText(scan_title)

    # SPEC-compatibility
    SCAN_N = RE.md["scan_id"] + 1  # the next scan number (user-controllable)

    ts = str(datetime.datetime.now())
    yield from bps.mv(
        user_data.sample_title,
        scan_title,
        user_data.sample_thickness,
        thickness,
        user_data.spec_scan,
        str(SCAN_N),
        user_data.time_stamp,
        ts,
        user_data.scan_macro,
        "uascan",
        timeout=MASTER_TIMEOUT,
    )
    yield from user_data.set_state_plan("starting USAXS step scan")

    yield from bps.mv(
        user_data.spec_file,
        os.path.split(specwriter.spec_filename)[-1],
        timeout=MASTER_TIMEOUT,
    )

    yield from bps.mv(
        a_stage.r,
        terms.USAXS.ar_val_center.get(),
        d_stage.x,
        terms.USAXS.DX0.get(),
        a_stage.x,
        terms.USAXS.AX0.get(),
        timeout=MASTER_TIMEOUT,
    )
    yield from user_data.set_state_plan("Moving to Q=0")
    yield from bps.mv(
        usaxs_q_calc.channels.B.input_value,
        terms.USAXS.ar_val_center.get(),
        timeout=MASTER_TIMEOUT,
    )

    yield from measure_USAXS_Transmission(md=_md)

    yield from bps.mv(
        monochromator.feedback.on,
        MONO_FEEDBACK_OFF,
        timeout=MASTER_TIMEOUT,
    )

    if terms.USAXS.is2DUSAXSscan.get():
        RECORD_SCAN_INDEX_10x_per_second = 9
        yield from bps.mv(
            terms.FlyScan.asrp_calc_SCAN,
            RECORD_SCAN_INDEX_10x_per_second,
            timeout=MASTER_TIMEOUT,
        )

    old_femto_change_gain_up = upd_controls.auto.gainU.get()
    old_femto_change_gain_down = upd_controls.auto.gainD.get()

    yield from bps.mv(
        upd_controls.auto.gainU,
        terms.USAXS.setpoint_up.get(),
        upd_controls.auto.gainD,
        terms.USAXS.setpoint_down.get(),
        usaxs_shutter,
        "open",
        timeout=MASTER_TIMEOUT,
    )
    yield from autoscale_amplifiers([upd_controls, I0_controls, I00_controls])

    yield from user_data.set_state_plan("Running USAXS step scan")

    SCAN_N = RE.md["scan_id"] + 1  # update with next number
    yield from bps.mv(
        user_data.scanning,
        "scanning",
        user_data.spec_scan,
        str(SCAN_N),
        timeout=MASTER_TIMEOUT,
    )

    _md["plan_name"] = "uascan"
    _md["plan_args"] = dict(
        pos_X=pos_X,
        pos_Y=pos_Y,
        thickness=thickness,
        scan_title=scan_title,
    )

    uascan_path = techniqueSubdirectory("usaxs")
    uascan_file_name = (
        f"{scan_title_clean}" f"_{terms.FlyScan.order_number.get():04d}" ".h5"
    )
    _md["hdf5_path"] = uascan_path
    _md["hdf5_file"] = uascan_file_name
    logger.info("USAXSscan HDF5 data path: %s", _md["hdf5_path"])
    logger.info("USAXSscan HDF5 data file: %s", _md["hdf5_file"])
    logger.info("*" * 10)

    startAngle = terms.USAXS.ar_val_center.get() - q2angle(
        terms.USAXS.start_offset.get(), monochromator.dcm.wavelength.position
    )
    endAngle = terms.USAXS.ar_val_center.get() - q2angle(
        terms.USAXS.finish.get(), monochromator.dcm.wavelength.position
    )
    bec.disable_plots()

    yield from record_sample_image_on_demand("usaxs", scan_title_clean, _md)

    use_dynamic_time = user_override.pick(
        "useDynamicTime", terms.USAXS.useDynamicTime.get()
    )
    yield from uascan(
        startAngle,
        terms.USAXS.ar_val_center.get(),
        endAngle,
        terms.USAXS.usaxs_minstep.get(),
        terms.USAXS.uaterm.get(),
        terms.USAXS.num_points.get(),
        terms.USAXS.usaxs_time.get(),
        terms.USAXS.DX0.get(),
        terms.USAXS.SDD.get(),
        terms.USAXS.AX0.get(),
        terms.USAXS.SAD.get(),
        useDynamicTime=use_dynamic_time,
        md=_md,
    )
    bec.enable_plots()

    yield from bps.mv(
        user_data.scanning,
        "no",
        timeout=MASTER_TIMEOUT,
    )

    yield from user_data.set_state_plan("USAXS step scan finished")

    yield from bps.mvr(terms.FlyScan.order_number, 1)
    yield from bps.mv(
        usaxs_shutter,
        "close",
        monochromator.feedback.on,
        MONO_FEEDBACK_ON,
        scaler0.update_rate,
        5,
        scaler0.auto_count_delay,
        0.25,
        scaler0.delay,
        0.05,
        scaler0.preset_time,
        1,
        scaler0.auto_count_time,
        1,
        upd_controls.auto.gainU,
        old_femto_change_gain_up,
        upd_controls.auto.gainD,
        old_femto_change_gain_down,
        timeout=MASTER_TIMEOUT,
    )

    yield from user_data.set_state_plan("Moving USAXS back and saving data")
    yield from bps.mv(
        a_stage.r,
        terms.USAXS.ar_val_center.get(),
        a_stage.x,
        terms.USAXS.AX0.get(),
        d_stage.x,
        terms.USAXS.DX0.get(),
        timeout=MASTER_TIMEOUT,
    )

    yield from after_plan(weight=3)


def Flyscan(
    pos_X: float,
    pos_Y: float,
    thickness: float,
    scan_title: str,
    md: Optional[Dict[str, Any]] = None,
    RE: Optional[Any] = None,
    bec: Optional[Any] = None,
    specwriter: Optional[Any] = None,
):
    """
    Execute a fly scan at the specified position.

    Parameters
    ----------
    pos_X : float
        X position for the scan
    pos_Y : float
        Y position for the scan
    thickness : float
        Sample thickness in mm
    scan_title : str
        Title for the scan
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
    Generator[Any, None, None]
        A generator that yields plan steps

    USAGE:  ``RE(Flyscan(pos_X, pos_Y, thickness, scan_title))``
    """
    if md is None:
        md = {}
    if RE is None:
        raise ValueError("RunEngine instance must be provided")
    if bec is None:
        raise ValueError("Bluesky Live Callbacks instance must be provided")
    if specwriter is None:
        raise ValueError("SPEC file writer instance must be provided")

    yield from IfRequestedStopBeforeNextScan()

    yield from mode_USAXS()

    yield from bps.mv(
        usaxs_slit.v_size,
        terms.SAXS.usaxs_v_size.get(),
        usaxs_slit.h_size,
        terms.SAXS.usaxs_h_size.get(),
        guard_slit.v_size,
        terms.SAXS.usaxs_guard_v_size.get(),
        guard_slit.h_size,
        terms.SAXS.usaxs_guard_h_size.get(),
        timeout=MASTER_TIMEOUT,
    )

    oldUA = terms.USAXS.uaterm.get()
    yield from bps.mv(terms.USAXS.uaterm, oldUA + 0.1)
    yield from bps.sleep(0.05)
    yield from bps.mv(terms.USAXS.uaterm, oldUA)

    yield from before_plan()

    yield from bps.mv(
        s_stage.x,
        pos_X,
        s_stage.y,
        pos_Y,
        timeout=MASTER_TIMEOUT,
    )

    scan_title = getSampleTitle(scan_title)
    _md = md or OrderedDict()
    _md["sample_thickness_mm"] = thickness
    _md["title"] = scan_title

    scan_title_clean = cleanupText(scan_title)

    SCAN_N = RE.md["scan_id"] + 1

    flyscan_path = techniqueSubdirectory("usaxs")
    if not os.path.exists(flyscan_path) and RE.state != "idle":
        os.mkdir(flyscan_path)
    flyscan_file_name = (
        f"{scan_title_clean}" f"_{terms.FlyScan.order_number.get():04d}" ".h5"
    )

    usaxs_flyscan.saveFlyData_HDF5_dir = flyscan_path
    usaxs_flyscan.saveFlyData_HDF5_file = flyscan_file_name

    ts = str(datetime.datetime.now())
    yield from bps.mv(
        user_data.sample_title,
        scan_title,
        user_data.sample_thickness,
        thickness,
        user_data.spec_scan,
        str(SCAN_N),
        user_data.time_stamp,
        ts,
        user_data.scan_macro,
        "FlyScan",
        timeout=MASTER_TIMEOUT,
    )
    yield from user_data.set_state_plan("starting USAXS Flyscan")

    yield from bps.mv(
        user_data.spec_file,
        os.path.split(specwriter.spec_filename)[-1],
        timeout=MASTER_TIMEOUT,
    )

    yield from bps.mv(
        a_stage.r,
        terms.USAXS.ar_val_center.get(),
        d_stage.x,
        terms.USAXS.DX0.get(),
        a_stage.x,
        terms.USAXS.AX0.get(),
        timeout=MASTER_TIMEOUT,
    )
    yield from user_data.set_state_plan("Moving to Q=0")
    yield from bps.mv(
        usaxs_q_calc.channels.B.input_value,
        terms.USAXS.ar_val_center.get(),
        timeout=MASTER_TIMEOUT,
    )

    usaxs_flyscan.saveFlyData_HDF5_dir = flyscan_path
    usaxs_flyscan.saveFlyData_HDF5_file = flyscan_file_name
    yield from measure_USAXS_Transmission(md=_md)

    yield from bps.mv(
        monochromator.feedback.on,
        MONO_FEEDBACK_OFF,
        timeout=MASTER_TIMEOUT,
    )

    if terms.USAXS.is2DUSAXSscan.get():
        RECORD_SCAN_INDEX_10x_per_second = 9
        yield from bps.mv(
            terms.FlyScan.asrp_calc_SCAN,
            RECORD_SCAN_INDEX_10x_per_second,
            timeout=MASTER_TIMEOUT,
        )

    old_femto_change_gain_up = upd_controls.auto.gainU.get()
    old_femto_change_gain_down = upd_controls.auto.gainD.get()

    yield from bps.mv(
        upd_controls.auto.gainU,
        terms.FlyScan.setpoint_up.get(),
        upd_controls.auto.gainD,
        terms.FlyScan.setpoint_down.get(),
        usaxs_shutter,
        "open",
        timeout=MASTER_TIMEOUT,
    )
    yield from autoscale_amplifiers([upd_controls, I0_controls, I00_controls])

    FlyScanAutoscaleTime = 0.025
    yield from bps.mv(
        scaler0.update_rate,
        0,
        scaler0.auto_count_update_rate,
        0,
        upd_controls.auto.mode,
        "auto+background",
        scaler0.preset_time,
        FlyScanAutoscaleTime,
        scaler0.auto_count_time,
        FlyScanAutoscaleTime,
        scaler0.auto_count_delay,
        FlyScanAutoscaleTime,
        scaler0.delay,
        0,
        scaler0.count_mode,
        SCALER_AUTOCOUNT_MODE,
        timeout=MASTER_TIMEOUT,
    )

    yield from bps.mv(
        lax_autosave.disable,
        1,
        lax_autosave.max_time,
        usaxs_flyscan.scan_time.get() + 9,
        timeout=MASTER_TIMEOUT,
    )

    yield from user_data.set_state_plan("Running Flyscan")

    yield from bps.mv(
        a_stage.r,
        flyscan_trajectories.ar.get()[0],
        a_stage.x,
        flyscan_trajectories.ax.get()[0],
        d_stage.x,
        flyscan_trajectories.dx.get()[0],
        ar_start,
        flyscan_trajectories.ar.get()[0],
        timeout=MASTER_TIMEOUT,
    )

    SCAN_N = RE.md["scan_id"] + 1
    yield from bps.mv(
        user_data.scanning,
        "scanning",
        user_data.spec_scan,
        str(SCAN_N),
        timeout=MASTER_TIMEOUT,
    )

    _md = md or OrderedDict()
    _md.update(md or {})
    _md["plan_name"] = "Flyscan"
    _md["plan_args"] = dict(
        pos_X=pos_X,
        pos_Y=pos_Y,
        thickness=thickness,
        scan_title=scan_title,
    )
    _md["fly_scan_time"] = usaxs_flyscan.scan_time.get()

    yield from record_sample_image_on_demand("usaxs", scan_title_clean, _md)

    yield from usaxs_flyscan.plan(md=_md)

    yield from bps.mv(
        user_data.scanning,
        "no",
        terms.FlyScan.elapsed_time,
        0,
        timeout=MASTER_TIMEOUT,
    )

    diff = flyscan_trajectories.num_pulse_positions.get() - struck.current_channel.get()
    if diff > 5 and RE.state != "idle":
        msg = "WARNING: Flyscan finished with %g less points" % diff
        logger.warning(msg)
        if NOTIFY_ON_BAD_FLY_SCAN:
            subject = "!!! bad number of PSO pulses !!!"
            email_notices.send(subject, msg)

    yield from user_data.set_state_plan("Flyscan finished")

    yield from bps.mvr(terms.FlyScan.order_number, 1)
    yield from bps.mv(
        lax_autosave.disable,
        0,
        lax_autosave.max_time,
        0,
        usaxs_shutter,
        "close",
        monochromator.feedback.on,
        MONO_FEEDBACK_ON,
        scaler0.update_rate,
        5,
        scaler0.auto_count_delay,
        0.25,
        scaler0.delay,
        0.05,
        scaler0.preset_time,
        1,
        scaler0.auto_count_time,
        1,
        upd_controls.auto.gainU,
        old_femto_change_gain_up,
        upd_controls.auto.gainD,
        old_femto_change_gain_down,
        timeout=MASTER_TIMEOUT,
    )

    yield from user_data.set_state_plan("Moving USAXS back and saving data")
    yield from bps.mv(
        a_stage.r,
        terms.USAXS.ar_val_center.get(),
        a_stage.x,
        terms.USAXS.AX0.get(),
        d_stage.x,
        terms.USAXS.DX0.get(),
        timeout=MASTER_TIMEOUT,
    )

    yield from after_plan(weight=3)
