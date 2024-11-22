
"""
user-facing scans
"""

__all__ = """
    preSWAXStune
    preUSAXStune
    allUSAXStune
    SAXS
    USAXSscan
    WAXS
""".split()

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

from apstools.devices import SCALER_AUTOCOUNT_MODE
from bluesky import plan_stubs as bps
from bluesky import preprocessors as bpp
from collections import OrderedDict
import datetime
import os
import time

from apstools.plans import restorable_stage_sigs
from ..devices import a_stage#, as_stage
#from ..devices import apsbss
from ..devices import ar_start
from ..devices import autoscale_amplifiers
from ..devices import blackfly_optical
from ..devices import ccd_shutter, mono_shutter, ti_filter_shutter
from ..devices import constants
from ..devices import d_stage, s_stage
from ..devices import email_notices, NOTIFY_ON_RESET, NOTIFY_ON_BADTUNE
from ..devices import flyscan_trajectories
from ..devices import guard_slit, usaxs_slit
from ..devices import lax_autosave
from ..devices import m_stage #, ms_stage
from ..devices import monochromator, MONO_FEEDBACK_OFF, MONO_FEEDBACK_ON
from ..devices import NOTIFY_ON_BAD_FLY_SCAN
from ..devices import saxs_det
from ..devices import saxs_stage
from ..devices import scaler0, scaler1
from ..devices import struck
from ..devices import terms
from ..devices import upd_controls, I0_controls, I00_controls, trd_controls
from ..devices import usaxs_flyscan
from ..devices import usaxs_q_calc
from ..devices import user_data
from ..devices import user_override
from ..devices import waxsx, waxs_det
from ..devices.suspenders import suspend_BeamInHutch
from ..framework import bec, RE, specwriter
from ..utils.cleanup_text import cleanupText
from ..utils.setup_new_user import techniqueSubdirectory
from ..utils.user_sample_title import getSampleTitle
from .area_detector import areaDetectorAcquire
from .axis_tuning import tune_ar, tune_a2rp#, tune_asrp
from .axis_tuning import tune_mr, tune_m2rp#, tune_msrp
from .filters import insertSaxsFilters
from .filters import insertWaxsFilters
from .mode_changes import mode_SAXS
from .mode_changes import mode_USAXS
from .mode_changes import mode_WAXS
from .requested_stop import IfRequestedStopBeforeNextScan
from .sample_imaging import record_sample_image_on_demand
from .sample_transmission import measure_SAXS_Transmission
from .sample_transmission import measure_USAXS_Transmission
from .uascan import uascan
from ..utils.a2q_q2a import angle2q, q2angle


# these two templates match each other, sort of
AD_FILE_TEMPLATE = "%s%s_%4.4d.hdf"
LOCAL_FILE_TEMPLATE = "%s_%04d.hdf"
MASTER_TIMEOUT = 60
user_override.register("useDynamicTime")

# Make sure these are not staged. For acquire_time,
# any change > 0.001 s takes ~0.5 s for Pilatus to complete!
DO_NOT_STAGE_THESE_KEYS___THEY_ARE_SET_IN_EPICS = """
    acquire_time acquire_period num_images num_exposures
""".split()


def preUSAXStune(md={}):
    """
    tune the USAXS optics *only* if in USAXS mode

    USAGE:  ``RE(preUSAXStune())``
    """
    yield from bps.mv(
        monochromator.feedback.on, MONO_FEEDBACK_ON,
        mono_shutter, "open",
        ccd_shutter, "close",
        timeout=MASTER_TIMEOUT,
    )
    yield from IfRequestedStopBeforeNextScan()         # stop if user chose to do so.

    yield from mode_USAXS()

    if terms.preUSAXStune.use_specific_location.get() in (1, "yes"):
        yield from bps.mv(
            s_stage.x, terms.preUSAXStune.sx.get(),
            s_stage.y, terms.preUSAXStune.sy.get(),
            timeout=MASTER_TIMEOUT,
            )

    yield from bps.mv(
        # ensure diode in place (Radiography puts it elsewhere)
        d_stage.x, terms.USAXS.diode.dx.get(),
        d_stage.y, terms.USAXS.diode.dy.get(),

        user_data.time_stamp, str(datetime.datetime.now()),
        # user_data.collection_in_progress, 1,

        # Is this covered by user_mode, "USAXS"?
        usaxs_slit.v_size,  terms.SAXS.usaxs_v_size.get(),
        usaxs_slit.h_size,  terms.SAXS.usaxs_h_size.get(),
        guard_slit.v_size,  terms.SAXS.usaxs_guard_v_size.get(),
        guard_slit.h_size,  terms.SAXS.usaxs_guard_h_size.get(),

        scaler0.preset_time,  0.1,
        timeout=MASTER_TIMEOUT,
    )
    yield from user_data.set_state_plan("pre-USAXS optics tune")

    # when all that is complete, then ...
    yield from bps.mv(ti_filter_shutter, "open", timeout=MASTER_TIMEOUT)

    # TODO: install suspender using usaxs_CheckBeamStandard.get()

    tuners = OrderedDict()                 # list the axes to tune
    # 20IDB does not need tuning M stage too often. Leave to manual staff action
    #tuners[m_stage.r] = tune_mr            # tune M stage to monochromator
    if not m_stage.isChannelCut:
        tuners[m_stage.r2p] = tune_m2rp        # make M stage crystals parallel
    if terms.USAXS.useMSstage.get():
        #tuners[ms_stage.rp] = tune_msrp    # align MSR stage with M stage
        pass
    if terms.USAXS.useSBUSAXS.get():
        #tuners[as_stage.rp] = tune_asrp    # align ASR stage with MSR stage and set ASRP0 value
        pass
    tuners[a_stage.r2p] = tune_a2rp        # make A stage crystals parallel
    tuners[a_stage.r] = tune_ar            # tune A stage to M stage
    # moving this up improves overall stability at 20IDB
    #tuners[a_stage.r2p] = tune_a2rp        # make A stage crystals parallel

    # now, tune the desired axes, bail out if a tune fails
    yield from bps.install_suspender(suspend_BeamInHutch)
    for axis, tune in tuners.items():
        yield from bps.mv(ti_filter_shutter, "open", timeout=MASTER_TIMEOUT)
        yield from tune(md=md)
        #if not axis.tuner.tune_ok:
        #    logger.warning("!!! tune failed for axis %s !!!", axis.name)
        #    if NOTIFY_ON_BADTUNE:
        #        email_notices.send(
        #            f"USAXS tune failed for axis {axis.name}",
        #            f"USAXS tune failed for axis {axis.name}"
        #            )

        # If we don't wait, the next tune often fails
        # intensity stays flat, statistically
        # We need to wait a short bit to allow EPICS database
        # to complete processing and report back to us.
        yield from bps.sleep(1)
    # tune a2rp one more time as final step, we will see if it is needed...  
    #yield from bps.mv(ti_filter_shutter, "open", timeout=MASTER_TIMEOUT)
    #yield from tune_a2rp(md=md)
    #if not axis.tuner.tune_ok:
    #    logger.warning("!!! tune failed for axis %s !!!", "a2rp")
    #yield from bps.sleep(1)
    yield from bps.remove_suspender(suspend_BeamInHutch)

    logger.info("USAXS count time: %s second(s)", terms.USAXS.usaxs_time.get())
    yield from bps.mv(
        scaler0.preset_time,        terms.USAXS.usaxs_time.get(),
        user_data.time_stamp,       str(datetime.datetime.now()),
        # user_data.collection_in_progress, 0,
        terms.preUSAXStune.num_scans_last_tune, 0,
        terms.preUSAXStune.run_tune_next,       0,
        terms.preUSAXStune.epoch_last_tune,     time.time(),
        timeout=MASTER_TIMEOUT,
    )
    yield from user_data.set_state_plan("pre-USAXS optics tune")

def allUSAXStune(md={}):
    """
    tune mr, ar, a2rp, ar, a2rp USAXS optics

    USAGE:  ``RE(allUSAXStune())``
    """
    yield from bps.mv(
        monochromator.feedback.on, MONO_FEEDBACK_ON,
        mono_shutter, "open",
        ccd_shutter, "close",
        timeout=MASTER_TIMEOUT,
    )
    yield from IfRequestedStopBeforeNextScan()         # stop if user chose to do so.

    yield from mode_USAXS()

    if terms.preUSAXStune.use_specific_location.get() in (1, "yes"):
        yield from bps.mv(
            s_stage.x, terms.preUSAXStune.sx.get(),
            s_stage.y, terms.preUSAXStune.sy.get(),
            timeout=MASTER_TIMEOUT,
            )

    yield from bps.mv(
        # ensure diode in place (Radiography puts it elsewhere)
        d_stage.x, terms.USAXS.diode.dx.get(),
        d_stage.y, terms.USAXS.diode.dy.get(),

        user_data.time_stamp, str(datetime.datetime.now()),
        # user_data.collection_in_progress, 1,
        # Is this covered by user_mode, "USAXS"?
        usaxs_slit.v_size,  terms.SAXS.usaxs_v_size.get(),
        usaxs_slit.h_size,  terms.SAXS.usaxs_h_size.get(),
        guard_slit.v_size,  terms.SAXS.usaxs_guard_v_size.get(),
        guard_slit.h_size,  terms.SAXS.usaxs_guard_h_size.get(),

        scaler0.preset_time,  0.1,
        timeout=MASTER_TIMEOUT,
    )
    yield from user_data.set_state_plan("pre-USAXS optics tune")

    # when all that is complete, then ...
    yield from bps.mv(ti_filter_shutter, "open", timeout=MASTER_TIMEOUT)

    # TODO: install suspender using usaxs_CheckBeamStandard.get()

    tuners = OrderedDict()                 # list the axes to tune
    tuners[m_stage.r] = tune_mr            # tune M stage to monochromator
    if not m_stage.isChannelCut:
        tuners[m_stage.r2p] = tune_m2rp        # make M stage crystals parallel
    if terms.USAXS.useMSstage.get():
        #tuners[ms_stage.rp] = tune_msrp    # align MSR stage with M stage
        pass
    if terms.USAXS.useSBUSAXS.get():
        #tuners[as_stage.rp] = tune_asrp    # align ASR stage with MSR stage and set ASRP0 value
        pass
    tuners[a_stage.r] = tune_ar            # tune A stage to M stage
    tuners[a_stage.r2p] = tune_a2rp        # make A stage crystals parallel
    tuners[a_stage.r] = tune_ar            # tune A stage to M stage
    tuners[a_stage.r2p] = tune_a2rp        # make A stage crystals parallel

    # now, tune the desired axes, bail out if a tune fails
    yield from bps.install_suspender(suspend_BeamInHutch)
    for axis, tune in tuners.items():
        yield from bps.mv(ti_filter_shutter, "open", timeout=MASTER_TIMEOUT)
        yield from tune(md=md)
        if not axis.tuner.tune_ok:
            logger.warning("!!! tune failed for axis %s !!!", axis.name)
            if NOTIFY_ON_BADTUNE:
                email_notices.send(
                    f"USAXS tune failed for axis {axis.name}",
                    f"USAXS tune failed for axis {axis.name}"
                    )

        # If we don't wait, the next tune often fails
        # intensity stays flat, statistically
        # We need to wait a short bit to allow EPICS database
        # to complete processing and report back to us.
        yield from bps.sleep(1)
    yield from bps.remove_suspender(suspend_BeamInHutch)

    logger.info("USAXS count time: %s second(s)", terms.USAXS.usaxs_time.get())
    yield from bps.mv(
        scaler0.preset_time,        terms.USAXS.usaxs_time.get(),
        user_data.time_stamp,       str(datetime.datetime.now()),
        # user_data.collection_in_progress, 0,
        terms.preUSAXStune.num_scans_last_tune, 0,
        terms.preUSAXStune.run_tune_next,       0,
        terms.preUSAXStune.epoch_last_tune,     time.time(),
        timeout=MASTER_TIMEOUT,
    )
    yield from user_data.set_state_plan("pre-USAXS optics tune")

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -


def preSWAXStune(md={}):
    """
    tune the SAXS & WAXS optics in any mode, is safe

    USAGE:  ``RE(preSWAXStune())``
    """
    # yield from bps.mv(
    #     monochromator.feedback.on, MONO_FEEDBACK_ON,
    #     mono_shutter, "open",
    #     ccd_shutter, "close",
    #     timeout=MASTER_TIMEOUT,
    # )
    # yield from IfRequestedStopBeforeNextScan()         # stop if user chose to do so.

    # if terms.preUSAXStune.use_specific_location.get() in (1, "yes"):
    #     yield from bps.mv(
    #         s_stage.x, terms.preUSAXStune.sx.get(),
    #         s_stage.y, terms.preUSAXStune.sy.get(),
    #         timeout=MASTER_TIMEOUT,
    #         )

    # yield from bps.mv(
    #     user_data.time_stamp, str(datetime.datetime.now()),
    #     # user_data.collection_in_progress, 1,

    #     scaler0.preset_time,  0.1,
    #     timeout=MASTER_TIMEOUT,
    # )
    # yield from user_data.set_state_plan("pre-SWAXS optics tune")

    # # when all that is complete, then ...
    # yield from bps.mv(ti_filter_shutter, "open", timeout=MASTER_TIMEOUT)

    # # TODO: install suspender using usaxs_CheckBeamStandard.get()

    # tuners = OrderedDict()                 # list the axes to tune
    # tuners[m_stage.r] = tune_mr            # tune M stage to monochromator
    # if not m_stage.isChannelCut:
    #     tuners[m_stage.r2p] = tune_m2rp        # make M stage crystals parallel
    # if terms.USAXS.useMSstage.get():
    #     tuners[ms_stage.rp] = tune_msrp    # align MSR stage with M stage

    # # now, tune the desired axes, bail out if a tune fails
    # yield from bps.install_suspender(suspend_BeamInHutch)
    # for axis, tune in tuners.items():
    #     yield from bps.mv(ti_filter_shutter, "open", timeout=MASTER_TIMEOUT)
    #     yield from tune(md=md)
    #     if axis.tuner.tune_ok:
    #         # If we don't wait, the next tune often fails
    #         # intensity stays flat, statistically
    #         # We need to wait a short bit to allow EPICS database
    #         # to complete processing and report back to us.
    #         yield from bps.sleep(1)
    #     else:
    #         logger.warning("!!! tune failed for axis %s !!!", axis.name)
    #         # break
    # yield from bps.remove_suspender(suspend_BeamInHutch)

    # logger.info("USAXS count time: %s second(s)", terms.USAXS.usaxs_time.get())
    # yield from bps.mv(
    #     scaler0.preset_time,        terms.USAXS.usaxs_time.get(),
    #     user_data.time_stamp,       str(datetime.datetime.now()),
    #     # user_data.collection_in_progress, 0,

    #     terms.preUSAXStune.num_scans_last_tune, 0,
    #     terms.preUSAXStune.run_tune_next,       0,
    #     terms.preUSAXStune.epoch_last_tune,     time.time(),
    #     timeout=MASTER_TIMEOUT,
    # )
    # yield from user_data.set_state_plan("pre-SWAXS optics tune")
    yield from bps.null()

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -


def USAXSscan(x, y, thickness_mm, title, md=None):
    """
    general scan macro for fly or step USAXS with 1D or 2D collimation
    """
    #_md = apsbss.update_MD(md or {})
    _md = md or OrderedDict()
    _md["sample_thickness_mm"] = thickness_mm
    _md["title"] = title
    if terms.FlyScan.use_flyscan.get():
        yield from Flyscan(x, y, thickness_mm, title, md=_md)
    else:
        yield from USAXSscanStep(x, y, thickness_mm, title, md=_md)


def USAXSscanStep(pos_X, pos_Y, thickness, scan_title, md=None):
    """
    general scan macro for step USAXS for both 1D & 2D collimation
    """

    from .command_list import after_plan, before_plan

    # bluesky_runengine_running = RE.state != "idle"

    yield from IfRequestedStopBeforeNextScan()

    yield from mode_USAXS()

    yield from bps.mv(
        usaxs_slit.v_size, terms.SAXS.usaxs_v_size.get(),
        usaxs_slit.h_size, terms.SAXS.usaxs_h_size.get(),
        guard_slit.v_size, terms.SAXS.usaxs_guard_v_size.get(),
        guard_slit.h_size, terms.SAXS.usaxs_guard_h_size.get(),
        timeout=MASTER_TIMEOUT,
    )
    yield from before_plan()

    yield from bps.mv(
        s_stage.x, pos_X,
        s_stage.y, pos_Y,
        timeout=MASTER_TIMEOUT,
    )

    # Update Sample name.  getSampleTitle is used to create proper sample name. It may add time and temperature
    #   therefore it needs to be done close to real data collection, after mode chaneg and optional tuning.
    scan_title = getSampleTitle(scan_title)
    #_md = apsbss.update_MD(md or {})
    _md = md or OrderedDict()
    _md["sample_thickness_mm"] = thickness
    _md["title"] = scan_title

    scan_title_clean = cleanupText(scan_title)

    # SPEC-compatibility
    SCAN_N = RE.md["scan_id"]+1     # the next scan number (user-controllable)

    ts = str(datetime.datetime.now())
    yield from bps.mv(
        user_data.sample_title, scan_title,
        user_data.sample_thickness, thickness,
        user_data.spec_scan, str(SCAN_N),
        # or terms.FlyScan.order_number.get()
        user_data.time_stamp, ts,
        user_data.scan_macro, "uascan",
        # user_data.collection_in_progress, 1,
        timeout=MASTER_TIMEOUT,
    )
    yield from user_data.set_state_plan("starting USAXS step scan")

    yield from bps.mv(
        user_data.spec_file, os.path.split(specwriter.spec_filename)[-1],
        timeout=MASTER_TIMEOUT,
    )

    # offset the calc from exact zero so can plot log(|Q|)
    # q_offset = terms.USAXS.start_offset.get()
    # angle_offset = q2angle(q_offset, monochromator.dcm.wavelength.position)
    # ar0_calc_offset = terms.USAXS.ar_val_center.get() + angle_offset

    yield from bps.mv(
        a_stage.r, terms.USAXS.ar_val_center.get(),
        # these two were moved by mode_USAXS(), belt & suspenders here
        d_stage.x, terms.USAXS.DX0.get(),
        a_stage.x, terms.USAXS.AX0.get(),
        timeout=MASTER_TIMEOUT,
    )
    yield from user_data.set_state_plan("Moving to Q=0")
    yield from bps.mv(
        usaxs_q_calc.channels.B.input_value, terms.USAXS.ar_val_center.get(),
        timeout=MASTER_TIMEOUT,
    )

    # TODO: what to do with USAXSScanUp?
    # 2019-01-25, prj+jil: this is probably not used now, only known to SPEC
    # it's used to cal Finish_in_Angle and START
    # both of which get passed to EPICS
    # That happens outside of this code.  completely.

    # measure transmission values using pin diode if desired
    yield from bps.install_suspender(suspend_BeamInHutch)
    yield from measure_USAXS_Transmission(md=_md)

    yield from bps.mv(
        monochromator.feedback.on, MONO_FEEDBACK_OFF,
        timeout=MASTER_TIMEOUT,
        )

    # enable asrp link to ar for 2D USAXS
    if terms.USAXS.is2DUSAXSscan.get():
        RECORD_SCAN_INDEX_10x_per_second = 9
        yield from bps.mv(
            terms.FlyScan.asrp_calc_SCAN, RECORD_SCAN_INDEX_10x_per_second,
            timeout=MASTER_TIMEOUT,
        )

    # we'll reset these after the scan is done
    old_femto_change_gain_up = upd_controls.auto.gainU.get()
    old_femto_change_gain_down = upd_controls.auto.gainD.get()

    yield from bps.mv(
        upd_controls.auto.gainU, terms.USAXS.setpoint_up.get(),
        upd_controls.auto.gainD, terms.USAXS.setpoint_down.get(),
        ti_filter_shutter, "open",
        timeout=MASTER_TIMEOUT,
    )
    yield from autoscale_amplifiers([upd_controls, I0_controls, I00_controls])

    yield from user_data.set_state_plan("Running USAXS step scan")

    SCAN_N = RE.md["scan_id"]+1     # update with next number
    yield from bps.mv(
        user_data.scanning, "scanning",          # we are scanning now (or will be very soon)
        user_data.spec_scan, str(SCAN_N),
        timeout=MASTER_TIMEOUT,
    )

    _md['plan_name'] = "uascan"
    _md['plan_args'] = dict(
        pos_X = pos_X,
        pos_Y = pos_Y,
        thickness = thickness,
        scan_title = scan_title,
        )

    uascan_path = techniqueSubdirectory("usaxs")
    uascan_file_name = (
        f"{scan_title_clean}"
        #f"_{plan_name}"
        f"_{terms.FlyScan.order_number.get():04d}"
        ".h5"
    )
    _md["hdf5_path"] = uascan_path
    _md["hdf5_file"] = uascan_file_name
    logger.info("USAXSscan HDF5 data path: %s", _md["hdf5_path"])
    logger.info("USAXSscan HDF5 data file: %s", _md["hdf5_file"])
    logger.info("*"*10)  # this line gets clobbered on the console

    startAngle = (
        terms.USAXS.ar_val_center.get()
        - q2angle(terms.USAXS.start_offset.get(), monochromator.dcm.wavelength.position)
    )
    endAngle = (
        terms.USAXS.ar_val_center.get()
        - q2angle(terms.USAXS.finish.get(), monochromator.dcm.wavelength.position)
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
        md=_md
    )
    bec.enable_plots()

    yield from bps.mv(
        user_data.scanning, "no",          # for sure, we are not scanning now
        timeout=MASTER_TIMEOUT,
    )
    yield from bps.remove_suspender(suspend_BeamInHutch)

    yield from user_data.set_state_plan("USAXS step scan finished")

    yield from bps.mvr(terms.FlyScan.order_number, 1)  # increment it
    yield from bps.mv(
        ti_filter_shutter, "close",
        monochromator.feedback.on, MONO_FEEDBACK_ON,
        # user_data.collection_in_progress, 0,

        scaler0.update_rate, 5,
        scaler0.auto_count_delay, 0.25,
        scaler0.delay, 0.05,
        scaler0.preset_time, 1,
        scaler0.auto_count_time, 1,

        upd_controls.auto.gainU, old_femto_change_gain_up,
        upd_controls.auto.gainD, old_femto_change_gain_down,
        timeout=MASTER_TIMEOUT,
        )

    yield from user_data.set_state_plan("Moving USAXS back and saving data")
    # file writing is handled by the nxwriter callback, by a RE subscription
    yield from bps.mv(
        a_stage.r, terms.USAXS.ar_val_center.get(),
        a_stage.x, terms.USAXS.AX0.get(),
        d_stage.x, terms.USAXS.DX0.get(),
        timeout=MASTER_TIMEOUT,
        )

    # TODO: make this link for side-bounce
    # disable asrp link to ar for 2D USAXS
    # FS_disableASRP

    # measure_USAXS_PD_dark_currents    # used to be here, not now
    yield from after_plan(weight=3)


def Flyscan(pos_X, pos_Y, thickness, scan_title, md=None):
    """
    do one USAXS Fly Scan
    """
    plan_name = "Flyscan"

    from .command_list import after_plan, before_plan

    bluesky_runengine_running = RE.state != "idle"

    yield from IfRequestedStopBeforeNextScan()

    yield from mode_USAXS()

    yield from bps.mv(
        usaxs_slit.v_size, terms.SAXS.usaxs_v_size.get(),
        usaxs_slit.h_size, terms.SAXS.usaxs_h_size.get(),
        guard_slit.v_size, terms.SAXS.usaxs_guard_v_size.get(),
        guard_slit.h_size, terms.SAXS.usaxs_guard_h_size.get(),
        timeout=MASTER_TIMEOUT,
    )
    yield from before_plan()

    yield from bps.mv(
        s_stage.x, pos_X,
        s_stage.y, pos_Y,
        timeout=MASTER_TIMEOUT,
    )

    # Update Sample name. getSampleTitle is used to create proper sample name. It may add time and temperature
    #   therefore it needs to be done close to real data collection, after mode chaneg and optional tuning.
    scan_title = getSampleTitle(scan_title)
    _md = md or OrderedDict()
    _md["sample_thickness_mm"] = thickness
    _md["title"] = scan_title

    scan_title_clean = cleanupText(scan_title)

    # SPEC-compatibility
    SCAN_N = RE.md["scan_id"]+1     # the next scan number (user-controllable)

    flyscan_path = techniqueSubdirectory("usaxs")
    if not os.path.exists(flyscan_path) and bluesky_runengine_running:
        # must create this directory if not exists
        os.mkdir(flyscan_path)
    flyscan_file_name = (
        f"{scan_title_clean}"
        #f"_{plan_name}"
        f"_{terms.FlyScan.order_number.get():04d}"
        ".h5"
    )

    usaxs_flyscan.saveFlyData_HDF5_dir = flyscan_path
    usaxs_flyscan.saveFlyData_HDF5_file = flyscan_file_name

    ts = str(datetime.datetime.now())
    yield from bps.mv(
        user_data.sample_title, scan_title,
        user_data.sample_thickness, thickness,
        user_data.spec_scan, str(SCAN_N),
        # or terms.FlyScan.order_number.get()
        user_data.time_stamp, ts,
        user_data.scan_macro, "FlyScan",    # note camel-case
        # user_data.collection_in_progress, 1,
        timeout=MASTER_TIMEOUT,
    )
    yield from user_data.set_state_plan("starting USAXS Flyscan")

    yield from bps.mv(
        user_data.spec_file, os.path.split(specwriter.spec_filename)[-1],
        timeout=MASTER_TIMEOUT,
    )

    # offset the calc from exact zero so can plot log(|Q|)
    # q_offset = terms.USAXS.start_offset.get()
    # angle_offset = q2angle(q_offset, monochromator.dcm.wavelength.position)
    # ar0_calc_offset = terms.USAXS.ar_val_center.get() + angle_offset

    yield from bps.mv(
        a_stage.r, terms.USAXS.ar_val_center.get(),
        # these two were moved by mode_USAXS(), belt & suspenders here
        d_stage.x, terms.USAXS.DX0.get(),
        a_stage.x, terms.USAXS.AX0.get(),
        timeout=MASTER_TIMEOUT,
    )
    yield from user_data.set_state_plan("Moving to Q=0")
    yield from bps.mv(
        usaxs_q_calc.channels.B.input_value, terms.USAXS.ar_val_center.get(),
        timeout=MASTER_TIMEOUT,
    )

    # TODO: what to do with USAXSScanUp?
    # 2019-01-25, prj+jil: this is probably not used now, only known to SPEC
    # it's used to cal Finish_in_Angle and START
    # both of which get passed to EPICS
    # That happens outside of this code.  completely.

    # measure transmission values using pin diode if desired
    usaxs_flyscan.saveFlyData_HDF5_dir = flyscan_path
    usaxs_flyscan.saveFlyData_HDF5_file = flyscan_file_name
    yield from bps.install_suspender(suspend_BeamInHutch)
    yield from measure_USAXS_Transmission(md=_md)

    yield from bps.mv(
        monochromator.feedback.on, MONO_FEEDBACK_OFF,
        timeout=MASTER_TIMEOUT,
        )

    # enable asrp link to ar for 2D USAXS
    if terms.USAXS.is2DUSAXSscan.get():
        RECORD_SCAN_INDEX_10x_per_second = 9
        yield from bps.mv(
            terms.FlyScan.asrp_calc_SCAN, RECORD_SCAN_INDEX_10x_per_second,
            timeout=MASTER_TIMEOUT,
        )

    # we'll reset these after the scan is done
    old_femto_change_gain_up = upd_controls.auto.gainU.get()
    old_femto_change_gain_down = upd_controls.auto.gainD.get()

    yield from bps.mv(
        upd_controls.auto.gainU, terms.FlyScan.setpoint_up.get(),
        upd_controls.auto.gainD, terms.FlyScan.setpoint_down.get(),
        ti_filter_shutter, "open",
        timeout=MASTER_TIMEOUT,
    )
    yield from autoscale_amplifiers([upd_controls, I0_controls, I00_controls])


    FlyScanAutoscaleTime = 0.025
    yield from bps.mv(
        scaler0.update_rate, 0,
        scaler0.auto_count_update_rate, 0,
        upd_controls.auto.mode, "auto+background",
        scaler0.preset_time, FlyScanAutoscaleTime,
        scaler0.auto_count_time, FlyScanAutoscaleTime,
        scaler0.auto_count_delay, FlyScanAutoscaleTime,
        scaler0.delay, 0,
        scaler0.count_mode, SCALER_AUTOCOUNT_MODE,
        timeout=MASTER_TIMEOUT,
        )

   # Pause autosave on LAX to prevent delays in PVs processing.
    yield from bps.mv(
        lax_autosave.disable, 1,
        # autosave will restart after this interval (s)
        lax_autosave.max_time, usaxs_flyscan.scan_time.get()+9,
        timeout=MASTER_TIMEOUT,
        )

    yield from user_data.set_state_plan("Running Flyscan")

    ### move the stages to flyscan starting values from EPICS PVs
    yield from bps.mv(
        a_stage.r, flyscan_trajectories.ar.get()[0],
        a_stage.x, flyscan_trajectories.ax.get()[0],
        d_stage.x, flyscan_trajectories.dx.get()[0],
        ar_start, flyscan_trajectories.ar.get()[0],
        # ay_start, flyscan_trajectories.ay.get()[0],
        # dy_start, flyscan_trajectories.dy.get()[0],
        timeout=MASTER_TIMEOUT,
    )

    SCAN_N = RE.md["scan_id"]+1     # update with next number
    yield from bps.mv(
        user_data.scanning, "scanning",          # we are scanning now (or will be very soon)
        user_data.spec_scan, str(SCAN_N),
        timeout=MASTER_TIMEOUT,
    )

    _md = md or OrderedDict()
    _md.update(md or {})
    _md['plan_name'] = plan_name
    _md['plan_args'] = dict(
        pos_X = pos_X,
        pos_Y = pos_Y,
        thickness = thickness,
        scan_title = scan_title,
        )
    _md['fly_scan_time'] = usaxs_flyscan.scan_time.get()
        #'detectors': [det.name for det in detectors],
        #'num_points': num,
        #'num_intervals': num_intervals,
        #'hints': {}

    yield from record_sample_image_on_demand("usaxs", scan_title_clean, _md)

    yield from usaxs_flyscan.plan(md=_md)        # DO THE FLY SCAN

    yield from bps.mv(
        user_data.scanning, "no",          # for sure, we are not scanning now
        terms.FlyScan.elapsed_time, 0,  # show the users there is no more time
        timeout=MASTER_TIMEOUT,
    )
    yield from bps.remove_suspender(suspend_BeamInHutch)

    # Check if we had bad number of PSO pulses
    diff = flyscan_trajectories.num_pulse_positions.get() - struck.current_channel.get()
    if diff > 5 and bluesky_runengine_running:
        msg = "WARNING: Flyscan finished with %g less points" % diff
        logger.warning(msg)
        if NOTIFY_ON_BAD_FLY_SCAN:
            subject = "!!! bad number of PSO pulses !!!"
            email_notices.send(subject, msg)

    yield from user_data.set_state_plan("Flyscan finished")

    yield from bps.mvr(terms.FlyScan.order_number, 1)  # increment it
    yield from bps.mv(
        lax_autosave.disable, 0,    # enable
        lax_autosave.max_time, 0,   # start right away

        ti_filter_shutter, "close",
        monochromator.feedback.on, MONO_FEEDBACK_ON,
        # user_data.collection_in_progress, 0,

        scaler0.update_rate, 5,
        scaler0.auto_count_delay, 0.25,
        scaler0.delay, 0.05,
        scaler0.preset_time, 1,
        scaler0.auto_count_time, 1,

        upd_controls.auto.gainU, old_femto_change_gain_up,
        upd_controls.auto.gainD, old_femto_change_gain_down,
        timeout=MASTER_TIMEOUT,
        )

    yield from user_data.set_state_plan("Moving USAXS back and saving data")
    yield from bps.mv(
        a_stage.r, terms.USAXS.ar_val_center.get(),
        a_stage.x, terms.USAXS.AX0.get(),
        d_stage.x, terms.USAXS.DX0.get(),
        timeout=MASTER_TIMEOUT,
        )

    # TODO: make this link for side-bounce
    # disable asrp link to ar for 2D USAXS
    # FS_disableASRP

    # measure_USAXS_PD_dark_currents    # used to be here, not now
    yield from after_plan(weight=3)


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

def SAXS(pos_X, pos_Y, thickness, scan_title, md=None):
    """
    collect SAXS data
    """

    from .command_list import after_plan, before_plan

    yield from IfRequestedStopBeforeNextScan()

    yield from before_plan()    # MUST come before mode_SAXS since it might tune

    yield from mode_SAXS()

    pinz_target = terms.SAXS.z_in.get() + constants["SAXS_PINZ_OFFSET"]
    yield from bps.mv(
        usaxs_slit.v_size, terms.SAXS.v_size.get(),
        usaxs_slit.h_size, terms.SAXS.h_size.get(),
        guard_slit.v_size, terms.SAXS.guard_v_size.get(),
        guard_slit.h_size, terms.SAXS.guard_h_size.get(),
        saxs_stage.z, pinz_target,      # MUST move before sample stage moves!
        user_data.sample_thickness, thickness,
        terms.SAXS.collecting, 1,
        # user_data.collection_in_progress, 1,
        timeout=MASTER_TIMEOUT,
    )

    yield from bps.mv(
        s_stage.x, pos_X,
        s_stage.y, pos_Y,
        timeout=MASTER_TIMEOUT,
    )

    # Update Sample name. getSampleTitle is used to create proper sample name. It may add time and temperature
    #   therefore it needs to be done close to real data collection, after mode chaneg and optional tuning.
    scan_title = getSampleTitle(scan_title)
    #_md = apsbss.update_MD(md or {})
    _md = md or OrderedDict()
    _md.update(md or {})
    _md['plan_name'] = "SAXS"
    _md["sample_thickness_mm"] = thickness
    _md["title"] = scan_title

    scan_title_clean = cleanupText(scan_title)

    # SPEC-compatibility
    SCAN_N = RE.md["scan_id"]+1     # the next scan number (user-controllable)

    # these two templates match each other, sort of
    ad_file_template = AD_FILE_TEMPLATE
    local_file_template = LOCAL_FILE_TEMPLATE

    # path on local file system
    SAXSscan_path = techniqueSubdirectory("saxs")
    SAXS_file_name = local_file_template % (scan_title_clean, saxs_det.hdf1.file_number.get())
    _md["hdf5_path"] = str(SAXSscan_path)
    _md["hdf5_file"] = str(SAXS_file_name)

    # NFS-mounted path as the Pilatus detector sees it
    pilatus_path = os.path.join("/mnt/usaxscontrol", *SAXSscan_path.split(os.path.sep)[2:])
    # area detector will create this path if needed ("Create dir. depth" setting)
    if not pilatus_path.endswith("/"):
        pilatus_path += "/"        # area detector needs this
    local_name = os.path.join(SAXSscan_path, SAXS_file_name)
    logger.info(f"Area Detector HDF5 file: {local_name}")
    pilatus_name = os.path.join(pilatus_path, SAXS_file_name)
    logger.info(f"Pilatus computer Area Detector HDF5 file: {pilatus_name}")

    saxs_det.hdf1.file_path._auto_monitor = False
    saxs_det.hdf1.file_template._auto_monitor = False
    yield from bps.mv(
        saxs_det.hdf1.file_name, scan_title_clean,
        saxs_det.hdf1.file_path, pilatus_path,
        saxs_det.hdf1.file_template, ad_file_template,
        timeout=MASTER_TIMEOUT,
        # auto_monitor=False,
    )
    saxs_det.hdf1.file_path._auto_monitor = True
    saxs_det.hdf1.file_template._auto_monitor = True

    ts = str(datetime.datetime.now())
    yield from bps.mv(
        user_data.sample_title, scan_title,
        user_data.sample_thickness, thickness,
        user_data.spec_scan, str(SCAN_N),
        user_data.time_stamp, ts,
        user_data.scan_macro, "SAXS",       # match the value in the scan logs
        timeout=MASTER_TIMEOUT,
    )
    yield from user_data.set_state_plan("starting SAXS collection")
    yield from bps.mv(
        user_data.spec_file, os.path.split(specwriter.spec_filename)[-1],
        timeout=MASTER_TIMEOUT,
    )
    old_delay = scaler0.delay.get()

    @restorable_stage_sigs([saxs_det.cam, saxs_det.hdf1])
    @bpp.suspend_decorator(suspend_BeamInHutch)
    def _image_acquisition_steps(): 
        yield from measure_SAXS_Transmission()
        yield from insertSaxsFilters()

        yield from bps.mv(
            mono_shutter, "open",
            monochromator.feedback.on, MONO_FEEDBACK_OFF,
            ti_filter_shutter, "open",
            saxs_det.cam.num_images, terms.SAXS.num_images.get(),
            saxs_det.cam.acquire_time, terms.SAXS.acquire_time.get(),
            saxs_det.cam.acquire_period, terms.SAXS.acquire_time.get() + 0.004,
            timeout=MASTER_TIMEOUT,
        )
        for k in DO_NOT_STAGE_THESE_KEYS___THEY_ARE_SET_IN_EPICS:
            if k in saxs_det.cam.stage_sigs:
                print(f"Removing {saxs_det.cam.name}.stage_sigs[{k}].")
                saxs_det.cam.stage_sigs.pop(k)
        saxs_det.hdf1.stage_sigs["file_template"] = ad_file_template
        saxs_det.hdf1.stage_sigs["file_write_mode"] = "Single"
        saxs_det.hdf1.stage_sigs["blocking_callbacks"] = "No"

        yield from bps.sleep(0.2)
        yield from autoscale_amplifiers([I0_controls])

        yield from bps.mv(
            ti_filter_shutter, "close",
            timeout=MASTER_TIMEOUT,
        )

        SCAN_N = RE.md["scan_id"]+1     # update with next number
        yield from bps.mv(
            scaler1.preset_time, terms.SAXS.acquire_time.get() + 1,
            scaler0.preset_time, 1.2*terms.SAXS.acquire_time.get() + 1,
            scaler0.count_mode, "OneShot",
            scaler1.count_mode, "OneShot",

            # update as fast as hardware will allow
            # this is needed to make sure we get as up to date I0 number as possible for AD software.
            scaler0.update_rate, 60,
            scaler1.update_rate, 60,
            scaler0.count, 0,
            scaler1.count, 0,

            scaler0.delay, 0,
            terms.SAXS_WAXS.start_exposure_time, ts,
            user_data.spec_scan, str(SCAN_N),
            timeout=MASTER_TIMEOUT,
        )
        yield from user_data.set_state_plan(f"SAXS collection for {terms.SAXS.acquire_time.get()} s")

        # replaced by  usxLAX:userTran1
        # yield from bps.mv(
        #     scaler0.count, 1,
        #     scaler1.count, 1,
        #     timeout=MASTER_TIMEOUT,
        # )

        yield from record_sample_image_on_demand("saxs", scan_title_clean, _md)
        yield from areaDetectorAcquire(saxs_det, create_directory=-5, md=_md)

    yield from _image_acquisition_steps()

    ts = str(datetime.datetime.now())
    yield from bps.mv(
        # scaler0.count, 0,
        # scaler1.count, 0,
        terms.SAXS_WAXS.I0, scaler1.channels.chan02.s.get(),
        scaler0.update_rate, 5,
        scaler1.update_rate, 5,
        terms.SAXS_WAXS.end_exposure_time, ts,
        scaler0.delay, old_delay,

        terms.SAXS.collecting, 0,
        user_data.time_stamp, ts,
        # user_data.collection_in_progress, 0,
        timeout=MASTER_TIMEOUT,
    )
    yield from user_data.set_state_plan("Done SAXS")
    logger.info(f"I0 value: {terms.SAXS_WAXS.I0.get()}")
    yield from after_plan()


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -


def WAXS(pos_X, pos_Y, thickness, scan_title, md=None):
    """
    collect WAXS data
    """

    from .command_list import after_plan, before_plan

    yield from IfRequestedStopBeforeNextScan()

    yield from before_plan()    # MUST come before mode_WAXS since it might tune

    yield from mode_WAXS()

    yield from bps.mv(
        usaxs_slit.v_size, terms.SAXS.v_size.get(),
        usaxs_slit.h_size, terms.SAXS.h_size.get(),
        guard_slit.v_size, terms.SAXS.guard_v_size.get(),
        guard_slit.h_size, terms.SAXS.guard_h_size.get(),
        user_data.sample_thickness, thickness,
        terms.WAXS.collecting, 1,
        #user_data.collection_in_progress, 1,
        timeout=MASTER_TIMEOUT,
    )

    yield from bps.mv(
        s_stage.x, pos_X,
        s_stage.y, pos_Y,
        timeout=MASTER_TIMEOUT,
    )

    # Update Sample name.  getSampleTitle is used to create proper sample name. It may add time and temperature
    #   therefore it needs to be done close to real data collection, after mode chaneg and optional tuning.
    scan_title = getSampleTitle(scan_title)
    #_md = apsbss.update_MD(md or {})
    _md = md or OrderedDict()
    _md["sample_thickness_mm"] = thickness
    _md["title"] = scan_title
    _md['plan_name'] = "WAXS"

    scan_title_clean = cleanupText(scan_title)

    # SPEC-compatibility
    SCAN_N = RE.md["scan_id"]+1     # the next scan number (user-controllable)

    # these two templates match each other, sort of
    ad_file_template = AD_FILE_TEMPLATE
    local_file_template = LOCAL_FILE_TEMPLATE

    # path on local file system
    WAXSscan_path = techniqueSubdirectory("waxs")
    WAXS_file_name = local_file_template % (scan_title_clean, waxs_det.hdf1.file_number.get())
    _md["hdf5_path"] = str(WAXSscan_path)
    _md["hdf5_file"] = str(WAXS_file_name)

    # NFS-mounted path as the Pilatus detector sees it
    pilatus_path = os.path.join("/mnt/usaxscontrol", *WAXSscan_path.split(os.path.sep)[2:])
    # area detector will create this path if needed ("Create dir. depth" setting)
    if not pilatus_path.endswith("/"):
        pilatus_path += "/"        # area detector needs this
    local_name = os.path.join(WAXSscan_path, WAXS_file_name)
    logger.info(f"Area Detector HDF5 file: {local_name}")
    pilatus_name = os.path.join(pilatus_path, WAXS_file_name)
    logger.info(f"Pilatus computer Area Detector HDF5 file: {pilatus_name}")

    waxs_det.hdf1.file_path._auto_monitor = False
    waxs_det.hdf1.file_template._auto_monitor = False
    yield from bps.mv(
        waxs_det.hdf1.file_name, scan_title_clean,
        waxs_det.hdf1.file_path, pilatus_path,
        waxs_det.hdf1.file_template, ad_file_template,
        timeout=MASTER_TIMEOUT,
        # auto_monitor=False,
    )
    waxs_det.hdf1.file_path._auto_monitor = True
    waxs_det.hdf1.file_template._auto_monitor = True

    ts = str(datetime.datetime.now())
    yield from bps.mv(
        user_data.sample_title, scan_title,
        user_data.sample_thickness, thickness,
        user_data.spec_scan, str(SCAN_N),
        user_data.time_stamp, ts,
        user_data.scan_macro, "WAXS",       # match the value in the scan logs
        timeout=MASTER_TIMEOUT,
    )
    yield from user_data.set_state_plan("starting WAXS collection")
    yield from bps.mv(
        user_data.spec_file, os.path.split(specwriter.spec_filename)[-1],
        timeout=MASTER_TIMEOUT,
   )
    old_delay = scaler0.delay.get()

    @restorable_stage_sigs([waxs_det.cam, waxs_det.hdf1])
    @bpp.suspend_decorator(suspend_BeamInHutch)
    def _image_acquisition_steps(): 
        #yield from measure_SAXS_Transmission()
        yield from insertWaxsFilters()

        yield from bps.mv(
            mono_shutter, "open",
            monochromator.feedback.on, MONO_FEEDBACK_OFF,
            ti_filter_shutter, "open",
            waxs_det.cam.num_images, terms.WAXS.num_images.get(),
            waxs_det.cam.acquire_time, terms.WAXS.acquire_time.get(),
            waxs_det.cam.acquire_period, terms.WAXS.acquire_time.get() + 0.004,
            timeout=MASTER_TIMEOUT,
        )
        for k in DO_NOT_STAGE_THESE_KEYS___THEY_ARE_SET_IN_EPICS:
            if k in waxs_det.cam.stage_sigs:
                print(f"Removing {waxs_det.cam.name}.stage_sigs[{k}].")
                waxs_det.cam.stage_sigs.pop(k)
        waxs_det.hdf1.stage_sigs["file_template"] = ad_file_template
        waxs_det.hdf1.stage_sigs["file_write_mode"] = "Single"
        waxs_det.hdf1.stage_sigs["blocking_callbacks"] = "No"

        yield from bps.sleep(0.2)
        yield from autoscale_amplifiers([I0_controls, trd_controls])

        yield from bps.mv(
            ti_filter_shutter, "close",
            timeout=MASTER_TIMEOUT,
        )

        yield from bps.mv(
            scaler1.preset_time, terms.WAXS.acquire_time.get() + 1,
            scaler0.preset_time, 1.2*terms.WAXS.acquire_time.get() + 1,
            scaler0.count_mode, "OneShot",
            scaler1.count_mode, "OneShot",

            # update as fast as hardware will allow
            # this is needed to make sure we get as up to date I0 number as possible for AD software.
            scaler0.update_rate, 60,
            scaler1.update_rate, 60,
            scaler0.count, 0,
            scaler1.count, 0,

            scaler0.delay, 0,
            terms.SAXS_WAXS.start_exposure_time, ts,
            timeout=MASTER_TIMEOUT,
        )
        yield from user_data.set_state_plan(f"WAXS collection for {terms.WAXS.acquire_time.get()} s")

        # replaced by  usxLAX:userTran1
        # yield from bps.mv(
        #     scaler0.count, 1,
        #     scaler1.count, 1,
        #     timeout=MASTER_TIMEOUT,
        # )

        yield from record_sample_image_on_demand("waxs", scan_title_clean, _md)

        yield from areaDetectorAcquire(waxs_det, create_directory=-5, md=_md)

    yield from _image_acquisition_steps()

    ts = str(datetime.datetime.now())
    yield from bps.mv(
        # scaler0.count, 0,
        # scaler1.count, 0,
        # WAXS uses same PVs for normalization and transmission as SAXS, should we aliased it same to terms.WAXS???
        terms.SAXS_WAXS.I0, scaler1.channels.chan02.s.get(),
        terms.SAXS_WAXS.diode_transmission, scaler0.channels.chan04.s.get(),
        terms.SAXS_WAXS.diode_gain, trd_controls.femto.gain.get(),
        terms.SAXS_WAXS.I0_transmission, scaler0.channels.chan02.s.get(),
        terms.SAXS_WAXS.I0_gain, I0_controls.femto.gain.get(),
        scaler0.update_rate, 5,
        scaler1.update_rate, 5,
        terms.SAXS_WAXS.end_exposure_time, ts,
        scaler0.delay, old_delay,

        terms.WAXS.collecting, 0,
        user_data.time_stamp, ts,
        #user_data.collection_in_progress, 0,
        timeout=MASTER_TIMEOUT,
    )
    yield from user_data.set_state_plan("Done WAXS")

    logger.info(f"I0 value: {terms.SAXS_WAXS.I0.get()}")
    yield from after_plan()
