"""
user-facing scans
"""

import datetime
import logging
import os
from collections import OrderedDict
from typing import Any
from typing import Dict
from typing import Optional

from apsbits.core.instrument_init import oregistry
from apstools.devices import SCALER_AUTOCOUNT_MODE
from bluesky import plan_stubs as bps
from bluesky import preprocessors as bpp

from usaxs.startup import suspend_BeamInHutch
from usaxs.startup import suspend_FE_shutter
from usaxs.utils.emails import email_notices
from usaxs.utils.override import user_override
from usaxs.utils.setup_new_user import techniqueSubdirectory
from apstools.utils import cleanupText
from usaxs.utils.user_sample_title import getSampleTitle

from ..utils.a2q_q2a import q2angle
# from .amplifiers_plan import autoscale_amplifiers     # fix this when amplifiers are available
# from .amplifiers_plan import I0_controls     # fix this when amplifiers are available
# from .amplifiers_plan import I00_controls     # fix this when amplifiers are available

from .command_list import after_plan
from .command_list import before_plan

from .mode_changes import mode_USAXS
from .mono_feedback import MONO_FEEDBACK_OFF
from .mono_feedback import MONO_FEEDBACK_ON
from .requested_stop import IfRequestedStopBeforeNextScan
from .sample_imaging import record_sample_image_on_demand
from .sample_transmission import measure_USAXS_Transmission
from .uascan import uascan


logger = logging.getLogger(__name__)

MASTER_TIMEOUT = 60
mono_shutter = oregistry["mono_shutter"]
usaxs_shutter = oregistry["usaxs_shutter"]
guard_slit = oregistry["guard_slit"]
monochromator = oregistry["monochromator"]
terms = oregistry["terms"]
s_stage = oregistry["s_stage"]
usaxs_slit = oregistry["usaxs_slit"]
user_data = oregistry["user_device"]
scaler0 = oregistry["scaler0"]
m_stage = oregistry["m_stage"]
a_stage = oregistry["a_stage"]
d_stage = oregistry["d_stage"]
usaxs_q_calc = oregistry["usaxs_q_calc"]
usaxs_flyscan = oregistry["usaxs_flyscan"]
lax_autosave = oregistry["lax_autosave"]
struck = oregistry["struck"]
flyscan_trajectories = oregistry["flyscan_trajectories"]
ar_start = oregistry["ar_start"]
NOTIFY_ON_BAD_FLY_SCAN = oregistry["NOTIFY_ON_BAD_FLY_SCAN"]
upd_controls = oregistry["upd_controls"]

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
