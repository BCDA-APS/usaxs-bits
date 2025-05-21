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

import datetime
import logging
import os
import time
from collections import OrderedDict
from typing import Any
from typing import Dict
from typing import Optional

from apsbits.core.instrument_init import oregistry, MONO_FEEDBACK_ON, MONO_FEEDBACK_OFF
from apstools.devices import SCALER_AUTOCOUNT_MODE
from apstools.plans import restorable_stage_sigs
from bluesky import plan_stubs as bps
from bluesky import preprocessors as bpp
from ..utils.override_parameters import user_override
from ..utils.setup_new_user import cleanupText, techniqueSubdirectory
from ..utils.user_sample_title import getSampleTitle
from ..suspenders.suspender_functions import suspend_FE_shutter, suspend_BeamInHutch

# Constants
ccd_shutter = oregistry["ccd_shutter"]
tune_m2rp = oregistry["tune_m2rp"]
tune_ar = oregistry["tune_ar"]
tune_a2rp = oregistry["tune_a2rp"]
NOTIFY_ON_BADTUNE = oregistry["NOTIFY_ON_BADTUNE"]
email_notices = oregistry["email_notices"]
tune_mr = oregistry["tune_mr"]
uascan = oregistry["uascan"]
NOTIFY_ON_BAD_FLY_SCAN = oregistry["NOTIFY_ON_BAD_FLY_SCAN"]

logger = logging.getLogger(__name__)
logger.info(__file__)

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

# Device and plan instances from oregistry (allowed list)
mono_shutter = oregistry["mono_shutter"]
usaxs_shutter = oregistry["usaxs_shutter"]
ar_start = oregistry["ar_start"]
guard_slit = oregistry["guard_slit"]
lax_autosave = oregistry["lax_autosave"]
m_stage = oregistry["m_stage"]
monochromator = oregistry["monochromator"]
s_stage = oregistry["s_stage"]
saxs_det = oregistry["saxs_det"]
saxs_stage = oregistry["saxs_stage"]
struck = oregistry["struck"]
terms = oregistry["terms"]
usaxs_flyscan = oregistry["usaxs_flyscan"]
usaxs_q_calc = oregistry["usaxs_q_calc"]
usaxs_slit = oregistry["usaxs_slit"]
user_data = oregistry["user_data"]
waxs_det = oregistry["waxs_det"]
a_stage = oregistry["a_stage"]
d_stage = oregistry["d_stage"]
flyscan_trajectories = oregistry["flyscan_trajectories"]
# Plan helpers (if available in oregistry)
IfRequestedStopBeforeNextScan = oregistry["IfRequestedStopBeforeNextScan"]
mode_USAXS = oregistry["mode_USAXS"]
mode_SAXS = oregistry["mode_SAXS"]
mode_WAXS = oregistry["mode_WAXS"]
record_sample_image_on_demand = oregistry["record_sample_image_on_demand"]
measure_USAXS_Transmission = oregistry["measure_USAXS_Transmission"]
measure_SAXS_Transmission = oregistry["measure_SAXS_Transmission"]
insertSaxsFilters = oregistry["insertSaxsFilters"]
insertWaxsFilters = oregistry["insertWaxsFilters"]
areaDetectorAcquire = oregistry["areaDetectorAcquire"]
q2angle = oregistry["q2angle"]
autoscale_amplifiers = oregistry["autoscale_amplifiers"]
I0_controls = oregistry["I0_controls"]
I00_controls = oregistry["I00_controls"]
upd_controls = oregistry["upd_controls"]
trd_controls = oregistry["trd_controls"]
scaler0 = oregistry["scaler0"]
scaler1 = oregistry["scaler1"]
constants = oregistry["constants"]
after_plan = oregistry["after_plan"]
before_plan = oregistry["before_plan"]

@bpp.suspend_decorator(suspend_FE_shutter)
@bpp.suspend_decorator(suspend_BeamInHutch)
def preUSAXStune(
    md: Optional[Dict[str, Any]] = None,
    RE: Optional[Any] = None,
    bec: Optional[Any] = None,
    specwriter: Optional[Any] = None,
):
    """
    Tune the USAXS optics in any mode, is safe.

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
    Generator[Any, None, None]
        A generator that yields plan steps

    USAGE:  ``RE(preUSAXStune())``
    """
    if md is None:
        md = {}
    if RE is None:
        raise ValueError("RunEngine instance must be provided")
    if bec is None:
        raise ValueError("Bluesky Live Callbacks instance must be provided")
    if specwriter is None:
        raise ValueError("SPEC file writer instance must be provided")

    yield from bps.mv(
        monochromator.feedback.on,
        MONO_FEEDBACK_ON,
        mono_shutter,
        "open",
        ccd_shutter,
        "close",
        timeout=MASTER_TIMEOUT,
    )
    yield from IfRequestedStopBeforeNextScan()  # stop if user chose to do so.

    yield from mode_USAXS()

    if terms.preUSAXStune.use_specific_location.get() in (1, "yes"):
        yield from bps.mv(
            s_stage.x,
            terms.preUSAXStune.sx.get(),
            s_stage.y,
            terms.preUSAXStune.sy.get(),
            timeout=MASTER_TIMEOUT,
        )

    yield from bps.mv(
        d_stage.x,
        terms.USAXS.DX0.get(),
        d_stage.y,
        terms.USAXS.diode.dy.get(),
        user_data.time_stamp,
        str(datetime.datetime.now()),
        usaxs_slit.v_size,
        terms.SAXS.usaxs_v_size.get(),
        usaxs_slit.h_size,
        terms.SAXS.usaxs_h_size.get(),
        guard_slit.v_size,
        terms.SAXS.usaxs_guard_v_size.get(),
        guard_slit.h_size,
        terms.SAXS.usaxs_guard_h_size.get(),
        scaler0.preset_time,
        0.1,
        timeout=MASTER_TIMEOUT,
    )
    yield from user_data.set_state_plan("pre-USAXS optics tune")

    # when all that is complete, then ...
    yield from bps.mv(usaxs_shutter, "open", timeout=MASTER_TIMEOUT)

    # TODO: install suspender using usaxs_CheckBeamStandard.get()

    tuners = OrderedDict()  # list the axes to tune
    # 20IDB does not need tuning M stage too often. Leave to manual staff action
    # tuners[m_stage.r] = tune_mr            # tune M stage to monochromator
    if not m_stage.isChannelCut:
        tuners[m_stage.r2p] = tune_m2rp  # make M stage crystals parallel
    if terms.USAXS.useMSstage.get():
        # tuners[ms_stage.rp] = tune_msrp    # align MSR stage with M stage
        pass
    if terms.USAXS.useSBUSAXS.get():
        # tuners[as_stage.rp] = tune_asrp
        #     align ASR stage with MSR stage
        #     and set ASRP0 value
        pass
    tuners[a_stage.r] = tune_ar  # tune A stage to M stage
    tuners[a_stage.r2p] = tune_a2rp  # make A stage crystals parallel
    tuners[a_stage.r] = tune_ar  # tune A stage to M stage
    tuners[a_stage.r2p] = tune_a2rp  # make A stage crystals parallel

    # now, tune the desired axes, bail out if a tune fails
    # yield from bps.install_suspender(suspend_BeamInHutch)
    for axis, tune in tuners.items():
        yield from bps.mv(usaxs_shutter, "open", timeout=MASTER_TIMEOUT)
        yield from tune(md=md)
        if not axis.tuner.tune_ok:
            logger.warning("!!! tune failed for axis %s !!!", axis.name)
            if NOTIFY_ON_BADTUNE:
                email_notices.send(
                    f"USAXS tune failed for axis {axis.name}",
                    f"USAXS tune failed for axis {axis.name}",
                )

        # If we don't wait, the next tune often fails
        # intensity stays flat, statistically
        # We need to wait a short bit to allow EPICS database
        # to complete processing and report back to us.
        yield from bps.sleep(1)
    # tune a2rp one more time as final step, we will see if it is needed...
    # yield from bps.mv(usaxs_shutter, "open", timeout=MASTER_TIMEOUT)
    # yield from tune_a2rp(md=md)
    # if not axis.tuner.tune_ok:
    #    logger.warning("!!! tune failed for axis %s !!!", "a2rp")
    # yield from bps.sleep(1)
    # yield from bps.remove_suspender(suspend_BeamInHutch)

    logger.info("USAXS count time: %s second(s)", terms.USAXS.usaxs_time.get())
    yield from bps.mv(
        scaler0.preset_time,
        terms.USAXS.usaxs_time.get(),
        user_data.time_stamp,
        str(datetime.datetime.now()),
        terms.preUSAXStune.num_scans_last_tune,
        0,
        terms.preUSAXStune.run_tune_next,
        0,
        terms.preUSAXStune.epoch_last_tune,
        time.time(),
        timeout=MASTER_TIMEOUT,
    )
    yield from user_data.set_state_plan("pre-USAXS optics tune")


@bpp.suspend_decorator(suspend_FE_shutter)
@bpp.suspend_decorator(suspend_BeamInHutch)
def allUSAXStune(
    md: Optional[Dict[str, Any]] = None,
    RE: Optional[Any] = None,
    bec: Optional[Any] = None,
    specwriter: Optional[Any] = None,
):
    """
    Tune mr, ar, a2rp, ar, a2rp USAXS optics.

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
    Generator[Any, None, None]
        A generator that yields plan steps

    USAGE:  ``RE(allUSAXStune())``
    """
    if md is None:
        md = {}
    if RE is None:
        RE = oregistry["RE"]
    if bec is None:
        bec = oregistry["bec"]
    if specwriter is None:
        specwriter = oregistry["specwriter"]

    # Get devices from oregistry
    monochromator = oregistry["monochromator"]
    mono_shutter = oregistry["mono_shutter"]
    ccd_shutter = oregistry["ccd_shutter"]
    terms = oregistry["terms"]
    s_stage = oregistry["s_stage"]
    d_stage = oregistry["d_stage"]
    user_data = oregistry["user_device"]
    usaxs_slit = oregistry["usaxs_slit"]
    guard_slit = oregistry["guard_slit"]
    scaler0 = oregistry["scaler0"]
    usaxs_shutter = oregistry["usaxs_shutter"]
    m_stage = oregistry["m_stage"]
    a_stage = oregistry["a_stage"]
    email_notices = oregistry["email_notices"]

    yield from bps.mv(
        monochromator.feedback.on,
        MONO_FEEDBACK_ON,
        mono_shutter,
        "open",
        ccd_shutter,
        "close",
        timeout=MASTER_TIMEOUT,
    )
    yield from IfRequestedStopBeforeNextScan(
        oregistry=oregistry
    )  # stop if user chose to do so.

    yield from mode_USAXS(oregistry=oregistry)

    if terms.preUSAXStune.use_specific_location.get() in (1, "yes"):
        yield from bps.mv(
            s_stage.x,
            terms.preUSAXStune.sx.get(),
            s_stage.y,
            terms.preUSAXStune.sy.get(),
            timeout=MASTER_TIMEOUT,
        )

    yield from bps.mv(
        d_stage.x,
        terms.USAXS.DX0.get(),  # TODO: resolve this database issue
        d_stage.y,
        terms.USAXS.diode.dy.get(),
        user_data.time_stamp,
        str(datetime.datetime.now()),
        usaxs_slit.v_size,
        terms.SAXS.usaxs_v_size.get(),
        usaxs_slit.h_size,
        terms.SAXS.usaxs_h_size.get(),
        guard_slit.v_size,
        terms.SAXS.usaxs_guard_v_size.get(),
        guard_slit.h_size,
        terms.SAXS.usaxs_guard_h_size.get(),
        scaler0.preset_time,
        0.1,
        timeout=MASTER_TIMEOUT,
    )
    yield from user_data.set_state_plan("pre-USAXS optics tune")

    # when all that is complete, then ...
    yield from bps.mv(usaxs_shutter, "open", timeout=MASTER_TIMEOUT)

    # TODO: install suspender using usaxs_CheckBeamStandard.get()

    tuners = OrderedDict()  # list the axes to tune
    tuners[m_stage.r] = tune_mr  # tune M stage to monochromator
    if not m_stage.isChannelCut:
        tuners[m_stage.r2p] = tune_m2rp  # make M stage crystals parallel
    if terms.USAXS.useMSstage.get():
        # tuners[ms_stage.rp] = tune_msrp    # align MSR stage with M stage
        pass
    if terms.USAXS.useSBUSAXS.get():
        # tuners[as_stage.rp] = tune_asrp    # align ASR stage with MSR stage
        pass
    tuners[a_stage.r] = tune_ar  # tune A stage to M stage
    tuners[a_stage.r2p] = tune_a2rp  # make A stage crystals parallel
    tuners[a_stage.r] = tune_ar  # tune A stage to M stage
    tuners[a_stage.r2p] = tune_a2rp  # make A stage crystals parallel

    # now, tune the desired axes, bail out if a tune fails
    # yield from bps.install_suspender(suspend_BeamInHutch)
    for axis, tune in tuners.items():
        yield from bps.mv(usaxs_shutter, "open", timeout=MASTER_TIMEOUT)
        yield from tune(md=md, oregistry=oregistry)
        if not axis.tuner.tune_ok:
            logger.warning("!!! tune failed for axis %s !!!", axis.name)
            if NOTIFY_ON_BADTUNE:
                email_notices.send(
                    f"USAXS tune failed for axis {axis.name}",
                    f"USAXS tune failed for axis {axis.name}",
                )

        # If we don't wait, the next tune often fails
        # intensity stays flat, statistically
        # We need to wait a short bit to allow EPICS database
        # to complete processing and report back to us.
        yield from bps.sleep(1)
    # yield from bps.remove_suspender(suspend_BeamInHutch)

    logger.info("USAXS count time: %s second(s)", terms.USAXS.usaxs_time.get())
    yield from bps.mv(
        scaler0.preset_time,
        terms.USAXS.usaxs_time.get(),
        user_data.time_stamp,
        str(datetime.datetime.now()),
        terms.preUSAXStune.num_scans_last_tune,
        0,
        terms.preUSAXStune.run_tune_next,
        0,
        terms.preUSAXStune.epoch_last_tune,
        time.time(),
        timeout=MASTER_TIMEOUT,
    )
    yield from user_data.set_state_plan("pre-USAXS optics tune")


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -


def preSWAXStune(
    md: Optional[Dict[str, Any]] = None,
    RE: Optional[Any] = None,
    bec: Optional[Any] = None,
    specwriter: Optional[Any] = None,
):
    """
    Tune the SAXS/WAXS optics in any mode, is safe.

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
    Generator[Any, None, None]
        A generator that yields plan steps

    USAGE:  ``RE(preSWAXStune())``
    """
    if md is None:
        md = {}
    if RE is None:
        raise ValueError("RunEngine instance must be provided")
    if bec is None:
        raise ValueError("Bluesky Live Callbacks instance must be provided")
    if specwriter is None:
        raise ValueError("SPEC file writer instance must be provided")

    # Get devices from oregistry
    monochromator = oregistry["monochromator"]
    mono_shutter = oregistry["mono_shutter"]
    ccd_shutter = oregistry["ccd_shutter"]
    terms = oregistry["terms"]
    s_stage = oregistry["s_stage"]
    user_data = oregistry["user_data"]
    scaler0 = oregistry["scaler0"]
    usaxs_shutter = oregistry["usaxs_shutter"]
    m_stage = oregistry["m_stage"]
    ms_stage = oregistry["ms_stage"]
    tune_msrp = oregistry["tune_msrp"]
    tune_mr = oregistry["tune_mr"]
    tune_m2rp = oregistry["tune_m2rp"]

    yield from bps.mv(
        monochromator.feedback.on,
        MONO_FEEDBACK_ON,
        mono_shutter,
        "open",
        ccd_shutter,
        "close",
        timeout=MASTER_TIMEOUT,
    )
    yield from IfRequestedStopBeforeNextScan(
        oregistry=oregistry
    )  # stop if user chose to do so.

    if terms.preUSAXStune.use_specific_location.get() in (1, "yes"):
        yield from bps.mv(
            s_stage.x,
            terms.preUSAXStune.sx.get(),
            s_stage.y,
            terms.preUSAXStune.sy.get(),
            timeout=MASTER_TIMEOUT,
        )

    yield from bps.mv(
        user_data.time_stamp,
        str(datetime.datetime.now()),
        scaler0.preset_time,
        0.1,
        timeout=MASTER_TIMEOUT,
    )
    yield from user_data.set_state_plan("pre-SWAXS optics tune")

    # when all that is complete, then ...
    yield from bps.mv(usaxs_shutter, "open", timeout=MASTER_TIMEOUT)

    # TODO: install suspender using usaxs_CheckBeamStandard.get()

    tuners = OrderedDict()  # list the axes to tune
    tuners[m_stage.r] = tune_mr  # tune M stage to monochromator
    if not m_stage.isChannelCut:
        tuners[m_stage.r2p] = tune_m2rp  # make M stage crystals parallel
    if terms.USAXS.useMSstage.get():
        tuners[ms_stage.rp] = tune_msrp  # align MSR stage with M stage

    # now, tune the desired axes, bail out if a tune fails
    yield from bps.install_suspender(suspend_BeamInHutch)
    for axis, tune in tuners.items():
        yield from bps.mv(usaxs_shutter, "open", timeout=MASTER_TIMEOUT)
        yield from tune(md=md, oregistry=oregistry)
        if axis.tuner.tune_ok:
            # If we don't wait, the next tune often fails
            # intensity stays flat, statistically
            # We need to wait a short bit to allow EPICS database
            # to complete processing and report back to us.
            yield from bps.sleep(1)
        else:
            logger.warning("!!! tune failed for axis %s !!!", axis.name)
            # break
    yield from bps.remove_suspender(suspend_BeamInHutch)

    logger.info("USAXS count time: %s second(s)", terms.USAXS.usaxs_time.get())
    yield from bps.mv(
        scaler0.preset_time,
        terms.USAXS.usaxs_time.get(),
        user_data.time_stamp,
        str(datetime.datetime.now()),
        terms.preUSAXStune.num_scans_last_tune,
        0,
        terms.preUSAXStune.run_tune_next,
        0,
        terms.preUSAXStune.epoch_last_tune,
        time.time(),
        timeout=MASTER_TIMEOUT,
    )
    yield from user_data.set_state_plan("pre-SWAXS optics tune")


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -


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


def SAXS(
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
    Execute a SAXS scan at the specified position.

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

    USAGE:  ``RE(SAXS(pos_X, pos_Y, thickness, scan_title))``
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

    yield from before_plan()

    yield from mode_SAXS()

    pinz_target = terms.SAXS.z_in.get() + constants["SAXS_PINZ_OFFSET"]
    yield from bps.mv(
        usaxs_slit.v_size,
        terms.SAXS.v_size.get(),
        usaxs_slit.h_size,
        terms.SAXS.h_size.get(),
        guard_slit.v_size,
        terms.SAXS.guard_v_size.get(),
        guard_slit.h_size,
        terms.SAXS.guard_h_size.get(),
        saxs_stage.z,
        pinz_target,
        user_data.sample_thickness,
        thickness,
        terms.SAXS.collecting,
        1,
        timeout=MASTER_TIMEOUT,
    )

    yield from bps.mv(
        s_stage.x,
        pos_X,
        s_stage.y,
        pos_Y,
        timeout=MASTER_TIMEOUT,
    )

    scan_title = getSampleTitle(scan_title)
    _md = md or OrderedDict()
    _md.update(md or {})
    _md["plan_name"] = "SAXS"
    _md["sample_thickness_mm"] = thickness
    _md["title"] = scan_title

    scan_title_clean = cleanupText(scan_title)

    SCAN_N = RE.md["scan_id"] + 1

    ad_file_template = AD_FILE_TEMPLATE
    local_file_template = LOCAL_FILE_TEMPLATE

    SAXSscan_path = techniqueSubdirectory("saxs")
    SAXS_file_name = local_file_template % (
        scan_title_clean,
        saxs_det.hdf1.file_number.get(),
    )
    _md["hdf5_path"] = str(SAXSscan_path)
    _md["hdf5_file"] = str(SAXS_file_name)

    pilatus_path = os.path.join(
        "/mnt/usaxscontrol", *SAXSscan_path.split(os.path.sep)[2:]
    )
    if not pilatus_path.endswith("/"):
        pilatus_path += "/"
    local_name = os.path.join(SAXSscan_path, SAXS_file_name)
    logger.info(f"Area Detector HDF5 file: {local_name}")
    pilatus_name = os.path.join(pilatus_path, SAXS_file_name)
    logger.info(f"Pilatus computer Area Detector HDF5 file: {pilatus_name}")

    saxs_det.hdf1.file_path._auto_monitor = False
    saxs_det.hdf1.file_template._auto_monitor = False
    yield from bps.mv(
        saxs_det.hdf1.file_name,
        scan_title_clean,
        saxs_det.hdf1.file_path,
        pilatus_path,
        saxs_det.hdf1.file_template,
        ad_file_template,
        timeout=MASTER_TIMEOUT,
    )
    saxs_det.hdf1.file_path._auto_monitor = True
    saxs_det.hdf1.file_template._auto_monitor = True

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
        "SAXS",
        timeout=MASTER_TIMEOUT,
    )
    yield from user_data.set_state_plan("starting SAXS collection")
    yield from bps.mv(
        user_data.spec_file,
        os.path.split(specwriter.spec_filename)[-1],
        timeout=MASTER_TIMEOUT,
    )
    old_delay = scaler0.delay.get()

    @restorable_stage_sigs([saxs_det.cam, saxs_det.hdf1])
    def _image_acquisition_steps():
        yield from measure_SAXS_Transmission()
        yield from insertSaxsFilters()

        yield from bps.mv(
            mono_shutter,
            "open",
            monochromator.feedback.on,
            MONO_FEEDBACK_OFF,
            usaxs_shutter,
            "open",
            saxs_det.cam.num_images,
            terms.SAXS.num_images.get(),
            saxs_det.cam.acquire_time,
            terms.SAXS.acquire_time.get(),
            saxs_det.cam.acquire_period,
            terms.SAXS.acquire_time.get() + 0.004,
            timeout=MASTER_TIMEOUT,
        )
        for k in DO_NOT_STAGE_THESE_KEYS___THEY_ARE_SET_IN_EPICS:
            if k in saxs_det.cam.stage_sigs:
                saxs_det.cam.stage_sigs.pop(k)
        saxs_det.hdf1.stage_sigs["file_template"] = ad_file_template
        saxs_det.hdf1.stage_sigs["file_write_mode"] = "Single"
        saxs_det.hdf1.stage_sigs["blocking_callbacks"] = "No"

        yield from bps.sleep(0.2)
        yield from autoscale_amplifiers([I0_controls])

        yield from bps.mv(
            usaxs_shutter,
            "close",
            timeout=MASTER_TIMEOUT,
        )

        SCAN_N = RE.md["scan_id"] + 1
        yield from bps.mv(
            scaler1.preset_time,
            terms.SAXS.acquire_time.get() + 1,
            scaler0.preset_time,
            1.2 * terms.SAXS.acquire_time.get() + 1,
            scaler0.count_mode,
            "OneShot",
            scaler1.count_mode,
            "OneShot",
            scaler0.update_rate,
            60,
            scaler1.update_rate,
            60,
            scaler0.count,
            0,
            scaler0.delay,
            0,
            terms.SAXS_WAXS.start_exposure_time,
            ts,
            user_data.spec_scan,
            str(SCAN_N),
            timeout=MASTER_TIMEOUT,
        )
        yield from user_data.set_state_plan(
            f"SAXS collection for {terms.SAXS.acquire_time.get()} s"
        )

        yield from record_sample_image_on_demand("saxs", scan_title_clean, _md)
        yield from areaDetectorAcquire(saxs_det, create_directory=-5, md=_md)

    yield from _image_acquisition_steps()

    ts = str(datetime.datetime.now())
    yield from bps.mv(
        scaler0.count,
        0,
        scaler1.count,
        0,
        terms.SAXS_WAXS.I0,
        scaler1.channels.chan02.s.get(),
        scaler0.update_rate,
        5,
        scaler1.update_rate,
        5,
        terms.SAXS_WAXS.end_exposure_time,
        ts,
        scaler0.delay,
        old_delay,
        monochromator.feedback.on,
        MONO_FEEDBACK_ON,
        terms.SAXS.collecting,
        0,
        user_data.time_stamp,
        ts,
        timeout=MASTER_TIMEOUT,
    )
    yield from user_data.set_state_plan("Done SAXS")
    logger.info(f"I0 value: {terms.SAXS_WAXS.I0.get()}")
    yield from after_plan()


@bpp.suspend_decorator(suspend_FE_shutter)
@bpp.suspend_decorator(suspend_BeamInHutch)
def WAXS(
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
    Execute a WAXS scan at the specified position.

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

    USAGE:  ``RE(WAXS(pos_X, pos_Y, thickness, scan_title))``
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

    yield from before_plan()

    yield from mode_WAXS()

    yield from bps.mv(
        usaxs_slit.v_size,
        terms.SAXS.v_size.get(),
        usaxs_slit.h_size,
        terms.SAXS.h_size.get(),
        guard_slit.v_size,
        terms.SAXS.guard_v_size.get(),
        guard_slit.h_size,
        terms.SAXS.guard_h_size.get(),
        user_data.sample_thickness,
        thickness,
        terms.WAXS.collecting,
        1,
        timeout=MASTER_TIMEOUT,
    )

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
    _md["plan_name"] = "WAXS"

    scan_title_clean = cleanupText(scan_title)

    SCAN_N = RE.md["scan_id"] + 1

    ad_file_template = AD_FILE_TEMPLATE
    local_file_template = LOCAL_FILE_TEMPLATE

    WAXSscan_path = techniqueSubdirectory("waxs")
    WAXS_file_name = local_file_template % (
        scan_title_clean,
        waxs_det.hdf1.file_number.get(),
    )
    _md["hdf5_path"] = str(WAXSscan_path)
    _md["hdf5_file"] = str(WAXS_file_name)

    pilatus_path = os.path.join("/mnt/share1", *WAXSscan_path.split(os.path.sep)[2:])
    if not pilatus_path.endswith("/"):
        pilatus_path += "/"
    local_name = os.path.join(WAXSscan_path, WAXS_file_name)
    logger.info(f"Area Detector HDF5 file: {local_name}")
    pilatus_name = os.path.join(pilatus_path, WAXS_file_name)
    logger.info(f"Pilatus computer Area Detector HDF5 file: {pilatus_name}")

    waxs_det.hdf1.file_path._auto_monitor = False
    waxs_det.hdf1.file_template._auto_monitor = False
    yield from bps.mv(
        waxs_det.hdf1.file_name,
        scan_title_clean,
        waxs_det.hdf1.file_path,
        pilatus_path,
        waxs_det.hdf1.file_template,
        ad_file_template,
        timeout=MASTER_TIMEOUT,
    )
    waxs_det.hdf1.file_path._auto_monitor = True
    waxs_det.hdf1.file_template._auto_monitor = True

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
        "WAXS",
        timeout=MASTER_TIMEOUT,
    )
    yield from user_data.set_state_plan("starting WAXS collection")
    yield from bps.mv(
        user_data.spec_file,
        os.path.split(specwriter.spec_filename)[-1],
        timeout=MASTER_TIMEOUT,
    )
    old_delay = scaler0.delay.get()

    @restorable_stage_sigs([waxs_det.cam, waxs_det.hdf1])
    def _image_acquisition_steps():
        yield from insertWaxsFilters()

        yield from bps.mv(
            mono_shutter,
            "open",
            monochromator.feedback.on,
            MONO_FEEDBACK_OFF,
            usaxs_shutter,
            "open",
            waxs_det.cam.num_images,
            terms.WAXS.num_images.get(),
            waxs_det.cam.acquire_time,
            terms.WAXS.acquire_time.get(),
            waxs_det.cam.acquire_period,
            terms.WAXS.acquire_time.get() + 0.004,
            timeout=MASTER_TIMEOUT,
        )
        for k in DO_NOT_STAGE_THESE_KEYS___THEY_ARE_SET_IN_EPICS:
            if k in waxs_det.cam.stage_sigs:
                waxs_det.cam.stage_sigs.pop(k)
        waxs_det.hdf1.stage_sigs["file_template"] = ad_file_template
        waxs_det.hdf1.stage_sigs["file_write_mode"] = "Single"
        waxs_det.hdf1.stage_sigs["blocking_callbacks"] = "No"

        yield from bps.sleep(0.2)
        yield from autoscale_amplifiers([I0_controls, trd_controls])

        yield from bps.mv(
            usaxs_shutter,
            "close",
            timeout=MASTER_TIMEOUT,
        )

        yield from bps.mv(
            scaler1.preset_time,
            terms.WAXS.acquire_time.get() + 1,
            scaler0.preset_time,
            1.2 * terms.WAXS.acquire_time.get() + 1,
            scaler0.count_mode,
            "OneShot",
            scaler1.count_mode,
            "OneShot",
            scaler0.update_rate,
            60,
            scaler1.update_rate,
            60,
            scaler0.count,
            0,
            scaler0.delay,
            0,
            terms.SAXS_WAXS.start_exposure_time,
            ts,
            timeout=MASTER_TIMEOUT,
        )
        yield from user_data.set_state_plan(
            f"WAXS collection for {terms.WAXS.acquire_time.get()} s"
        )

        yield from record_sample_image_on_demand("waxs", scan_title_clean, _md)

        yield from areaDetectorAcquire(waxs_det, create_directory=-5, md=_md)

    yield from _image_acquisition_steps()

    ts = str(datetime.datetime.now())
    yield from bps.mv(
        scaler0.count,
        0,
        scaler1.count,
        0,
        terms.SAXS_WAXS.I0,
        scaler1.channels.chan02.s.get(),
        terms.SAXS_WAXS.diode_transmission,
        scaler0.channels.chan05.s.get(),
        terms.SAXS_WAXS.diode_gain,
        trd_controls.femto.gain.get(),
        terms.SAXS_WAXS.I0_transmission,
        scaler0.channels.chan02.s.get(),
        terms.SAXS_WAXS.I0_gain,
        I0_controls.femto.gain.get(),
        scaler0.update_rate,
        5,
        scaler1.update_rate,
        5,
        terms.SAXS_WAXS.end_exposure_time,
        ts,
        scaler0.delay,
        old_delay,
        monochromator.feedback.on,
        MONO_FEEDBACK_ON,
        terms.WAXS.collecting,
        0,
        user_data.time_stamp,
        ts,
        timeout=MASTER_TIMEOUT,
    )
    yield from user_data.set_state_plan("Done WAXS")

    logger.info(f"I0 value: {terms.SAXS_WAXS.I0.get()}")
    yield from after_plan()
