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
from apstools.utils import cleanupText
from bluesky import plan_stubs as bps
from bluesky import preprocessors as bpp
from bluesky.utils import plan

from usaxs.callbacks.spec_data_file_writer import specwriter
from usaxs.utils.override import user_override
from usaxs.utils.user_sample_title import getSampleTitle
from usaxs.utils.utils import techniqueSubdirectory

from ..utils.a2q_q2a import q2angle
from ..utils.global_suspenders import get_suspend_BeamInHutch
from ..utils.global_suspenders import get_suspend_FE_shutter
from .amplifiers_plan import autoscale_amplifiers
from .command_list import after_plan
from .command_list import before_plan
from .filter_plans import insertScanFilters
from .fly_scan_plan import Flyscan_internal_plan
from .mode_changes import mode_USAXS
from .mono_feedback import MONO_FEEDBACK_OFF
from .mono_feedback import MONO_FEEDBACK_ON
from .requested_stop import IfRequestedStopBeforeNextScan
from .sample_imaging import record_sample_image_on_demand
from .sample_transmission import measure_USAXS_Transmission
from .uascan_plan import uascan

logger = logging.getLogger(__name__)

MASTER_TIMEOUT = 60
a_stage = oregistry["a_stage"]
ar_start = oregistry["ar_start"]
d_stage = oregistry["d_stage"]
flyscan_trajectories = oregistry["flyscan_trajectories"]
guard_slit = oregistry["guard_slit"]
I0_controls = oregistry["I0_controls"]
I00_controls = oregistry["I00_controls"]
lax_autosave = oregistry["lax_autosave"]
m_stage = oregistry["m_stage"]
mono_shutter = oregistry["mono_shutter"]
monochromator = oregistry["monochromator"]
s_stage = oregistry["s_stage"]
scaler0 = oregistry["scaler0"]
struck = oregistry["struck"]
terms = oregistry["terms"]
upd_controls = oregistry["upd_controls"]
usaxs_flyscan = oregistry["usaxs_flyscan"]
usaxs_q_calc = oregistry["usaxs_q_calc"]
usaxs_shutter = oregistry["usaxs_shutter"]
usaxs_slit = oregistry["usaxs_slit"]
user_data = oregistry["user_data"]

suspend_FE_shutter = get_suspend_FE_shutter
suspend_BeamInHutch = get_suspend_BeamInHutch

@bpp.suspend_decorator(suspend_FE_shutter)
@bpp.suspend_decorator(suspend_BeamInHutch)
@plan
def USAXSscan(
    x: float,
    y: float,
    thickness_mm: float,
    title: str,
    md: Optional[Dict[str, Any]] = None,
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

    Returns
    -------
    Generator[Any, None, None]
        A generator that yields plan steps

    USAGE:  ``RE(USAXSscan(x, y, thickness_mm, title))``
    """
    if md is None:
        md = {}

    logger.info(f"Collecting USAXS for {title}")

    _md = md or OrderedDict()
    _md["sample_thickness_mm"] = thickness_mm
    _md["title"] = title
    if terms.FlyScan.use_flyscan.get():
        yield from Flyscan(x, y, thickness_mm, title, md=_md)
    else:
        yield from USAXSscanStep(x, y, thickness_mm, title, md=_md)

    yield from MONO_FEEDBACK_ON()


@plan
def USAXSscanStep(
    pos_X: float,
    pos_Y: float,
    thickness: float,
    scan_title: str,
    md: Optional[Dict[str, Any]] = None,
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

    Returns
    -------
    Generator[Any, None, None]
        A generator that yields plan steps

    USAGE:  ``RE(USAXSscanStep(pos_X, pos_Y, thickness, scan_title))``
    """

    from ..startup import RE
    from ..startup import bec

    if md is None:
        md = {}

    yield from IfRequestedStopBeforeNextScan()

    yield from mode_USAXS()

    yield from bps.mv(  # this should be just check if user changed slit sizes during
        # radiography.
        # fmt: off
        usaxs_slit.v_size,
        terms.SAXS.usaxs_v_size.get(),
        usaxs_slit.h_size,
        terms.SAXS.usaxs_h_size.get(),
        guard_slit.v_size,
        terms.SAXS.usaxs_guard_v_size.get(),
        guard_slit.h_size,
        terms.SAXS.usaxs_guard_h_size.get(),
        timeout=MASTER_TIMEOUT,
        # fmt: on
    )
    yield from before_plan()  # this will tune if needed.

    yield from bps.mv(  # sample in place.
        # fmt: off
        s_stage.x,
        pos_X,
        s_stage.y,
        pos_Y,
        timeout=MASTER_TIMEOUT,
        # fmt: on
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
    SCAN_N = RE.md["scan_id"] + 1  # update with next number

    ts = str(datetime.datetime.now())
    yield from bps.mv(
        # fmt: off
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
        # fmt: on
    )
    yield from user_data.set_state_plan("starting USAXS step scan")
    yield from user_data.set_state_plan("Moving to Q=0")

    yield from bps.mv(  # set spec file and move to Q=0 position, if needed.
        # fmt: off
        user_data.spec_file,
        os.path.split(specwriter.spec_filename)[-1],
        a_stage.r,
        terms.USAXS.ar_val_center.get(),
        d_stage.x,
        terms.USAXS.DX0.get(),
        a_stage.x,
        terms.USAXS.AX0.get(),
        usaxs_q_calc.channels.B.input_value,
        terms.USAXS.ar_val_center.get(),
        timeout=MASTER_TIMEOUT,
        # fmt: on
    )

    yield from measure_USAXS_Transmission()

    yield from MONO_FEEDBACK_OFF()

    # if terms.USAXS.is2DUSAXSscan.get():
    #     RECORD_SCAN_INDEX_10x_per_second = 9
    #     yield from bps.mv(
    #         terms.FlyScan.asrp_calc_SCAN,
    #         RECORD_SCAN_INDEX_10x_per_second,
    #         timeout=MASTER_TIMEOUT,
    #     )

    old_femto_change_gain_up = upd_controls.auto.gainU.get()
    old_femto_change_gain_down = upd_controls.auto.gainD.get()

    yield from bps.mv(
        # fmt: off
        upd_controls.auto.gainU,
        terms.USAXS.setpoint_up.get(),
        upd_controls.auto.gainD,
        terms.USAXS.setpoint_down.get(),
        usaxs_shutter,
        "open",
        timeout=MASTER_TIMEOUT,
        # fmt: on
    )
    yield from insertScanFilters()  # make sure filters are in place for scan

    yield from autoscale_amplifiers([upd_controls, I0_controls])

    yield from user_data.set_state_plan("Running USAXS step scan")

    # SPEC-compatibility
    SCAN_N = RE.md["scan_id"] + 1  # update with next number
    yield from bps.mv(
        # fmt: off
        user_data.scanning,
        "scanning",
        user_data.spec_scan,
        str(SCAN_N),
        timeout=MASTER_TIMEOUT,
        # fmt: on
    )

    _md["plan_name"] = "uascan"
    _md["plan_args"] = dict(
        pos_X=pos_X,
        pos_Y=pos_Y,
        thickness=thickness,
        scan_title=scan_title,
    )

    # setup names and paths as needed.
    uascan_path = techniqueSubdirectory("usaxs")
    uascan_file_name = (
        f"{scan_title_clean}" f"_{terms.FlyScan.order_number.get():04d}" ".h5"
    )
    _md["hdf5_path"] = uascan_path
    _md["hdf5_file"] = uascan_file_name
    logger.debug("USAXSscan HDF5 data path: %s", _md["hdf5_path"])
    logger.info("USAXSscan HDF5 data file: %s %s", _md["hdf5_path"], _md["hdf5_file"])
    logger.debug("*" * 10)

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
        # fmt: off
        user_data.scanning,
        "no",
        timeout=MASTER_TIMEOUT,
        # fmt: on
    )

    yield from user_data.set_state_plan("USAXS step scan finished")

    yield from bps.mvr(terms.FlyScan.order_number, 1)

    yield from MONO_FEEDBACK_ON()

    yield from user_data.set_state_plan("Moving USAXS back and saving data")

    yield from bps.mv(
        # fmt: off
        usaxs_shutter,
        "close",
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
        a_stage.r,
        terms.USAXS.ar_val_center.get(),
        a_stage.x,
        terms.USAXS.AX0.get(),
        d_stage.x,
        terms.USAXS.DX0.get(),
        timeout=MASTER_TIMEOUT,
        # fmt: on
    )

    yield from after_plan(weight=3)


@plan
def Flyscan(
    pos_X: float,
    pos_Y: float,
    thickness: float,
    scan_title: str,
    md: Optional[Dict[str, Any]] = None,
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

    Returns
    -------
    Generator[Any, None, None]
        A generator that yields plan steps

    USAGE:  ``RE(Flyscan(pos_X, pos_Y, thickness, scan_title))``
    """
    from ..startup import RE
    if md is None:
        md = {}

    yield from IfRequestedStopBeforeNextScan()

    yield from mode_USAXS()

    yield from bps.mv(  # make sure slits are correct, inc ase user changed them.
        # fmt: off
        usaxs_slit.v_size,
        terms.SAXS.usaxs_v_size.get(),
        usaxs_slit.h_size,
        terms.SAXS.usaxs_h_size.get(),
        guard_slit.v_size,
        terms.SAXS.usaxs_guard_v_size.get(),
        guard_slit.h_size,
        terms.SAXS.usaxs_guard_h_size.get(),
        timeout=MASTER_TIMEOUT,
        # fmt: on
    )

    # #verify, that usaxs_minstep is not too small to prevent PSO generator from failing
    # . 0.00002 deg is known minimum
    CurMinSTep = terms.USAXS.usaxs_minstep.get()
    if CurMinSTep < 0.00002:
        logger.warning(
            "Flyscan min_step is too small: %g deg, resetting to 0.00002 deg",
            CurMinSTep,
        )
        yield from bps.mv(terms.USAXS.usaxs_minstep, 0.00002)

    # this forces epics to recalculate and update paths in flyscan
    # without this bad things happen pon energy change. Keep me in.
    oldUA = terms.USAXS.uaterm.get()
    yield from bps.mv(terms.USAXS.uaterm, oldUA + 0.1)
    yield from bps.sleep(0.05)
    yield from bps.mv(terms.USAXS.uaterm, oldUA)

    yield from before_plan()

    yield from bps.mv(  # move sample in
        # fmt: off
        s_stage.x,
        pos_X,
        s_stage.y,
        pos_Y,
        timeout=MASTER_TIMEOUT,
        # fmt: on
    )

    # setup names and paths.
    scan_title = getSampleTitle(scan_title)
    _md = md or OrderedDict()
    _md["sample_thickness_mm"] = thickness
    _md["title"] = scan_title

    scan_title_clean = cleanupText(scan_title)
    # print("scan_title_clean:", scan_title_clean)

    # SPEC-compatibility
    SCAN_N = RE.md["scan_id"] + 1

    flyscan_path = techniqueSubdirectory("usaxs")
    if not os.path.exists(flyscan_path) and RE.state != "idle":
        os.mkdir(flyscan_path)
    flyscan_file_name = (
        f"{scan_title_clean}" f"_{terms.FlyScan.order_number.get():04d}" ".h5"
    )

    usaxs_flyscan.saveFlyData_HDF5_dir = flyscan_path
    usaxs_flyscan.saveFlyData_HDF5_file = flyscan_file_name
    logger.debug("Flyscan HDF5 data path: %s", flyscan_path)
    logger.info("Flyscan HDF5 data file: %s %s", flyscan_path, flyscan_file_name)
    logger.debug("*" * 10)

    # yield from user_data.set_state_plan("Moving to Q=0")
    yield from user_data.set_state_plan("starting USAXS Flyscan")

    ts = str(datetime.datetime.now())
    yield from bps.mv(
        # fmt: off
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
        user_data.spec_file,
        os.path.split(specwriter.spec_filename)[-1],
        a_stage.r,
        terms.USAXS.ar_val_center.get(),
        d_stage.x,
        terms.USAXS.DX0.get(),
        a_stage.x,
        terms.USAXS.AX0.get(),
        usaxs_q_calc.channels.B.input_value,
        terms.USAXS.ar_val_center.get(),
        timeout=MASTER_TIMEOUT,
        # fmt: on
    )
    yield from insertScanFilters()  # make sure filters are in place for scan

    yield from measure_USAXS_Transmission()

    yield from MONO_FEEDBACK_OFF()

    # if terms.USAXS.is2DUSAXSscan.get():
    #     RECORD_SCAN_INDEX_10x_per_second = 9
    #     yield from bps.mv(
    #         terms.FlyScan.asrp_calc_SCAN,
    #         RECORD_SCAN_INDEX_10x_per_second,
    #         timeout=MASTER_TIMEOUT,
    #     )

    old_femto_change_gain_up = upd_controls.auto.gainU.get()
    old_femto_change_gain_down = upd_controls.auto.gainD.get()

    yield from bps.mv(
        # fmt: off
        upd_controls.auto.gainU,
        terms.FlyScan.setpoint_up.get(),
        upd_controls.auto.gainD,
        terms.FlyScan.setpoint_down.get(),
        usaxs_shutter,
        "open",
        timeout=MASTER_TIMEOUT,
        # fmt: on
    )

    yield from autoscale_amplifiers([upd_controls, I0_controls, I00_controls])

    FlyScanAutoscaleTime = 0.025
    yield from bps.mv(
        # fmt: off
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
        lax_autosave.disable,
        1,
        lax_autosave.max_time,
        usaxs_flyscan.scan_time.get() + 9,
        timeout=MASTER_TIMEOUT,
        # fmt: on
    )

    yield from user_data.set_state_plan("Running Flyscan")

    yield from bps.mv(
        # fmt: off
        a_stage.r,
        flyscan_trajectories.ar.get()[0],
        a_stage.x,
        flyscan_trajectories.ax.get()[0],
        d_stage.x,
        flyscan_trajectories.dx.get()[0],
        ar_start,
        flyscan_trajectories.ar.get()[0],
        timeout=MASTER_TIMEOUT,
        # fmt: on
    )

    # SPEC-compatibility
    SCAN_N = RE.md["scan_id"] + 1
    yield from bps.mv(
        # fmt: off
        user_data.scanning,
        "scanning",
        user_data.spec_scan,
        str(SCAN_N),
        timeout=MASTER_TIMEOUT,
        # fmt: on
    )
    # save metadata
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

    # bec.disable_table()

    yield from Flyscan_internal_plan(md=_md)  # flyscan proper

    yield from bps.mv(
        # fmt: off
        user_data.scanning,
        "no",
        terms.FlyScan.elapsed_time,
        0,
        timeout=MASTER_TIMEOUT,
        # fmt: on
    )

    diff = flyscan_trajectories.num_pulse_positions.get() - struck.current_channel.get()
    if diff > 5 and RE.state != "idle":
        msg = "WARNING: Flyscan finished with %g less points" % diff
        logger.info("*") * 20
        logger.info(msg)
        logger.info("*") * 20
        # if NOTIFY_ON_BAD_FLY_SCAN:
        #     subject = "!!! bad number of PSO pulses !!!"
        #     email_notices.send(subject, msg)

    yield from bps.mvr(terms.FlyScan.order_number, 1)

    yield from user_data.set_state_plan("Moving USAXS back and saving data")

    yield from MONO_FEEDBACK_ON()

    yield from bps.mv(
        # fmt: off
        lax_autosave.disable,
        0,
        lax_autosave.max_time,
        0,
        usaxs_shutter,
        "close",
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
        a_stage.r,
        terms.USAXS.ar_val_center.get(),
        a_stage.x,
        terms.USAXS.AX0.get(),
        d_stage.x,
        terms.USAXS.DX0.get(),
        timeout=MASTER_TIMEOUT,
        # fmt: on
    )

    yield from user_data.set_state_plan("Flyscan finished")

    yield from after_plan(weight=3)
