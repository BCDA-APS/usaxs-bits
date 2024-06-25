
"""
configure per-axis tuning

A tunable axis has these attributes::

    tuner : obj (function reference)
        reference to tuning method, such as `apstools.plans.TuneAxis()`,
        Default value is `None` -- this *must* be set before axis can be tuned.

    pre_tune_method : obj (function reference)
        function to be called before tuning starts,
        the default prints status.
        Use this to stage various components for the tune.

    pre_tune_method : obj (function reference)
        function to be called after tuning ends,
        the default prints status.
        Use this to unstage various components after the tune.

For reference, `apstools.plans.TuneAxis().tune()` uses these default attributes::

    width : float
        full range that axis will be scanned, default = 1

    num : int
        full range that axis will be scanned, default = 10

    peak_choice : str
        either "cen" (default: peak value) or "com" (center of mass)

These attributes, set internally, are available for reference::

    axis : instance of `EpicsMotor` (or other positioner with `APS_devices.AxisTunerMixin`)
        positioner to be used

    signals : list of instances of `ScalerCH`, `EpicsScaler`, or similar
        list of detectors to be used

    signal_name : str
        name of specific detector signal (must be in `signals`) to use for tuning

These attributes, set internally, are results of the tune scan::

    tune_ok : bool
        status of most recent tune

    peaks : instance of `bluesky.callbacks.fitting.PeakStats`
        with results from most recent tune scan

    stats : [peaks]
        list of peak summary statistics from all previous tune scans

    center : float
        value of tune result: `if tune_ok: axis.move(center)`

"""

__all__ = [
    'axis_tune_range',
    "TUNE_METHOD_PEAK_CHOICE",
    "USING_MS_STAGE",
    "TUNING_DET_SIGNAL",
    ]

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

from apstools.plans import TuneAxis
from apstools.utils import trim_plot_by_name
from bluesky import plan_stubs as bps
from ophyd import Component, Device, EpicsSignal
from ophyd import Kind
from ophyd import EpicsScaler
from ophyd.scaler import ScalerCH
# from .override_ScalerCH import ScalerCH - removed JIL 6/2024, will this casue issues? 


logger.debug("before instrument imports")
from ..framework import bec
from .amplifiers import autoscale_amplifiers
from .amplifiers import I0_controls, I00_controls, upd_controls
from .general_terms import terms
from .miscellaneous import usaxs_q_calc
from .scalers import scaler0, I0_SIGNAL, I00_SIGNAL, UPD_SIGNAL
from .shutters import mono_shutter, ti_filter_shutter
from .stages import m_stage, ms_stage, s_stage, a_stage, as_stage, d_stage

# replace the definition from apstools.plans
from .axis_tuning_patches import UsaxsTuneAxis as TuneAxis

# use center-of-mass, and not peak value: "com"
TUNE_METHOD_PEAK_CHOICE = "com"

USING_MS_STAGE = False
TUNING_DET_SIGNAL = {True: I00_SIGNAL, False: I0_SIGNAL}[USING_MS_STAGE]


class TuneRanges(Device):
    """
    width of tuning for each axis
    """

    # in order of optical path
    mr   = Component(EpicsSignal, "9idcLAX:USAXS:tune_mr_range")
    msrp = Component(EpicsSignal, "9idcLAX:USAXS:tune_msrp_range")
    m2rp = Component(EpicsSignal, "9idcLAX:USAXS:tune_m2rp_range")
    ar   = Component(EpicsSignal, "9idcLAX:USAXS:tune_ar_range")
    asrp = Component(EpicsSignal, "9idcLAX:USAXS:tune_asrp_range")
    a2rp = Component(EpicsSignal, "9idcLAX:USAXS:tune_a2rp_range")
    dx = Component(EpicsSignal, "9idcLAX:USAXS:tune_dx_range")
    dy = Component(EpicsSignal, "9idcLAX:USAXS:tune_dy_range")

    @property
    def display(self):
        return ', '.join(
            [
                f"{k}={getattr(self, k).get()}"
                for k in self.component_names
            ]
        )

axis_tune_range = TuneRanges(name="axis_tune_range")


# -------------------------------------------

def mr_pretune_hook():
    stage = m_stage.r
    logger.info(f"Tuning axis {stage.name}, current position is {stage.position}")
    yield from bps.mv(scaler0.preset_time, 0.1,)
    y_name = TUNING_DET_SIGNAL.chname.get()
    scaler0.select_channels([y_name])
    scaler0.channels.chan01.kind = Kind.config
    trim_plot_by_name(n=5)
    # trim_plot_lines(bec, 5, stage, TUNING_DET_SIGNAL)


def mr_posttune_hook():
    msg = "Tuning axis {}, final position is {}"
    logger.info(msg.format(m_stage.r.name, m_stage.r.position))

    if m_stage.r.tuner.tune_ok:
        yield from bps.mv(terms.USAXS.mr_val_center, m_stage.r.position)

    scaler0.select_channels(None)


def _getScalerSignalName_(scaler, signal):
    if isinstance(scaler, ScalerCH):
        return signal.chname.get()
    elif isinstance(scaler, EpicsScaler):
        return signal.name

m_stage.r.tuner = TuneAxis(
    [scaler0],
    m_stage.r,
    signal_name=_getScalerSignalName_(scaler0, TUNING_DET_SIGNAL),
    width_signal=axis_tune_range.mr,
)
m_stage.r.tuner.peak_choice = TUNE_METHOD_PEAK_CHOICE
m_stage.r.tuner.num = 31
m_stage.r.tuner.width = axis_tune_range.mr.get()     # -0.004

m_stage.r.pre_tune_method = mr_pretune_hook
m_stage.r.post_tune_method = mr_posttune_hook

# -------------------------------------------


def m2rp_pretune_hook():
    stage = m_stage.r2p
    logger.info(f"Tuning axis {stage.name}, current position is {stage.position}")
    yield from bps.mv(scaler0.preset_time, 0.1)
    yield from bps.mv(scaler0.delay, 0.02)
    y_name = TUNING_DET_SIGNAL.chname.get()
    scaler0.select_channels([y_name])
    scaler0.channels.chan01.kind = Kind.config
    trim_plot_by_name(n=5)
    # trim_plot_lines(bec, 5, stage, TUNING_DET_SIGNAL)


def m2rp_posttune_hook():
    #
    # TODO: first, re-position piezo considering hysteresis?
    #
    msg = "Tuning axis {}, final position is {}"
    logger.info(msg.format(m_stage.r2p.name, m_stage.r2p.position))
    yield from bps.mv(scaler0.delay, 0.05)

    if m_stage.r2p.tuner.tune_ok:
        pass    # #165: update center when/if we get a PV for that

    scaler0.select_channels(None)


# use I00 (if MS stage is used, use I0)
m_stage.r2p.tuner = TuneAxis(
    [scaler0],
    m_stage.r2p,
    signal_name=_getScalerSignalName_(scaler0, TUNING_DET_SIGNAL),
    width_signal=axis_tune_range.m2rp,
)
m_stage.r2p.tuner.peak_choice = TUNE_METHOD_PEAK_CHOICE
m_stage.r2p.tuner.num = 21
m_stage.r2p.tuner.width = axis_tune_range.m2rp.get()     -8

m_stage.r2p.pre_tune_method = m2rp_pretune_hook
m_stage.r2p.post_tune_method = m2rp_posttune_hook


# -------------------------------------------


def msrp_pretune_hook():
    stage = ms_stage.rp
    logger.info(f"Tuning axis {stage.name}, current position is {stage.position}")
    yield from bps.mv(scaler0.preset_time, 0.1)
    y_name = TUNING_DET_SIGNAL.chname.get()
    scaler0.select_channels([y_name])
    scaler0.channels.chan01.kind = Kind.config
    trim_plot_by_name(n=5)
    # trim_plot_lines(bec, 5, stage, TUNING_DET_SIGNAL)


def msrp_posttune_hook():
    msg = "Tuning axis {}, final position is {}"
    logger.info(msg.format(ms_stage.rp.name, ms_stage.rp.position))

    if ms_stage.rp.tuner.tune_ok:
        yield from bps.mv(terms.USAXS.msr_val_center, ms_stage.rp.position)

    scaler0.select_channels(None)


# use I00 (if MS stage is used, use I0)
ms_stage.rp.tuner = TuneAxis(
    [scaler0],
    ms_stage.rp,
    signal_name=_getScalerSignalName_(scaler0, TUNING_DET_SIGNAL),
    width_signal=axis_tune_range.msrp,
)
ms_stage.rp.tuner.peak_choice = TUNE_METHOD_PEAK_CHOICE
ms_stage.rp.tuner.num = 21
ms_stage.rp.tuner.width = axis_tune_range.msrp.get()     # 6

ms_stage.rp.pre_tune_method = msrp_pretune_hook
ms_stage.rp.post_tune_method = msrp_posttune_hook

# -------------------------------------------


def ar_pretune_hook():
    stage = a_stage.r
    logger.info(f"Tuning axis {stage.name}, current position is {stage.position}")
    yield from bps.mv(scaler0.preset_time, 0.1)
    y_name = UPD_SIGNAL.chname.get()
    scaler0.select_channels([y_name])
    scaler0.channels.chan01.kind = Kind.config
    trim_plot_by_name(n=5)
    # trim_plot_lines(bec, 5, stage, UPD_SIGNAL)


def ar_posttune_hook():
    msg = "Tuning axis {}, final position is {}"
    logger.info(msg.format(a_stage.r.name, a_stage.r.position))

    if a_stage.r.tuner.tune_ok:
        yield from bps.mv(terms.USAXS.ar_val_center, a_stage.r.position)
        # remember the Q calculation needs a new 2theta0
        # use the current AR encoder position
        yield from bps.mv(
            usaxs_q_calc.channels.B.input_value, terms.USAXS.ar_val_center.get(),
            a_stage.r, terms.USAXS.ar_val_center.get(),
        )
    scaler0.select_channels(None)


a_stage.r.tuner = TuneAxis(
        [scaler0],
        a_stage.r,
        signal_name=_getScalerSignalName_(scaler0, UPD_SIGNAL),
        width_signal=axis_tune_range.ar,
)
a_stage.r.tuner.peak_choice = TUNE_METHOD_PEAK_CHOICE
a_stage.r.tuner.num = 35
a_stage.r.tuner.width = axis_tune_range.ar.get()     # -0.004

a_stage.r.pre_tune_method = ar_pretune_hook
a_stage.r.post_tune_method = ar_posttune_hook

# -------------------------------------------


def asrp_pretune_hook():
    stage = as_stage.rp
    logger.info(f"Tuning axis {stage.name}, current position is {stage.position}")
    yield from bps.mv(scaler0.preset_time, 0.1)
    y_name = UPD_SIGNAL.chname.get()
    scaler0.select_channels([y_name])
    scaler0.channels.chan01.kind = Kind.config
    trim_plot_by_name(n=5)
    # trim_plot_lines(bec, 5, stage, UPD_SIGNAL)


def asrp_posttune_hook():
    msg = "Tuning axis {}, final position is {}"
    logger.info(msg.format(as_stage.rp.name, as_stage.rp.position))
    yield from bps.mv(terms.USAXS.asr_val_center, as_stage.rp.position)

    if as_stage.rp.tuner.tune_ok:
        pass    # #165: update center when/if we get a PV for that

    scaler0.select_channels(None)


# use I00 (if MS stage is used, use I0)
as_stage.rp.tuner = TuneAxis(
    [scaler0],
    as_stage.rp,
    signal_name=_getScalerSignalName_(scaler0, UPD_SIGNAL),
    width_signal=axis_tune_range.asrp,
)
as_stage.rp.tuner.peak_choice = TUNE_METHOD_PEAK_CHOICE
as_stage.rp.tuner.num = 21
as_stage.rp.tuner.width = axis_tune_range.asrp.get()     # 6

as_stage.rp.pre_tune_method = asrp_pretune_hook
as_stage.rp.post_tune_method = asrp_posttune_hook

# -------------------------------------------


def a2rp_pretune_hook():
    stage = a_stage.r2p
    logger.info(f"Tuning axis {stage.name}, current position is {stage.position}")
    yield from bps.mv(scaler0.preset_time, 0.1)
    yield from bps.mv(scaler0.delay, 0.02)
    y_name = UPD_SIGNAL.chname.get()
    scaler0.select_channels([y_name])
    scaler0.channels.chan01.kind = Kind.config
    trim_plot_by_name(n=5)
    # trim_plot_lines(bec, 5, stage, UPD_SIGNAL)


def a2rp_posttune_hook():
    #
    # TODO: first, re-position piezo considering hysteresis?
    #
    msg = "Tuning axis {}, final position is {}"
    logger.info(msg.format(a_stage.r2p.name, a_stage.r2p.position))
    yield from bps.mv(scaler0.delay, 0.05)

    if a_stage.r2p.tuner.tune_ok:
        pass    # #165: update center when/if we get a PV for that

    scaler0.select_channels(None)


a_stage.r2p.tuner = TuneAxis(
    [scaler0],
    a_stage.r2p,
    signal_name=_getScalerSignalName_(scaler0, UPD_SIGNAL),
    width_signal=axis_tune_range.a2rp,
)
a_stage.r2p.tuner.peak_choice = TUNE_METHOD_PEAK_CHOICE
a_stage.r2p.tuner.num = 31
a_stage.r2p.tuner.width = axis_tune_range.a2rp.get()     # -8
a_stage.r2p.pre_tune_method = a2rp_pretune_hook
a_stage.r2p.post_tune_method = a2rp_posttune_hook

# -------------------------------------------


def dx_pretune_hook():
    stage = d_stage.x
    logger.info(f"Tuning axis {stage.name}, current position is {stage.position}")
    yield from bps.mv(scaler0.preset_time, 0.1)
    y_name = UPD_SIGNAL.chname.get()
    scaler0.select_channels([y_name])
    scaler0.channels.chan01.kind = Kind.config
    trim_plot_by_name(n=5)
    # trim_plot_lines(bec, 5, stage, UPD_SIGNAL)


def dx_posttune_hook():
    stage = d_stage.x
    logger.info(f"Tuning axis {stage.name}, final position is {stage.position}")

    if stage.tuner.tune_ok:
        yield from bps.mv(terms.USAXS.DX0, stage.position)

    scaler0.select_channels(None)


d_stage.x.tuner = TuneAxis(
    [scaler0],
    d_stage.x,
    signal_name=_getScalerSignalName_(scaler0, UPD_SIGNAL),
    width_signal=axis_tune_range.dx,
)
d_stage.x.tuner.peak_choice = TUNE_METHOD_PEAK_CHOICE
d_stage.x.tuner.num = 35
d_stage.x.tuner.width = axis_tune_range.dx.get()     # 10

d_stage.x.pre_tune_method = dx_pretune_hook
d_stage.x.post_tune_method = dx_posttune_hook

# -------------------------------------------


def dy_pretune_hook():
    stage = d_stage.y
    logger.info(f"Tuning axis {stage.name}, current position is {stage.position}")
    yield from bps.mv(scaler0.preset_time, 0.1)
    y_name = UPD_SIGNAL.chname.get()
    scaler0.select_channels([y_name])
    scaler0.channels.chan01.kind = Kind.config
    trim_plot_by_name(n=5)
    # trim_plot_lines(bec, 5, stage, UPD_SIGNAL)


def dy_posttune_hook():
    stage = d_stage.y
    logger.info(f"Tuning axis {stage.name}, final position is {stage.position}")

    if stage.tuner.tune_ok:
        yield from bps.mv(terms.SAXS.dy_in, stage.position)

    scaler0.select_channels(None)


d_stage.y.tuner = TuneAxis(
    [scaler0],
    d_stage.y,
    signal_name=_getScalerSignalName_(scaler0, UPD_SIGNAL),
    width_signal=axis_tune_range.dy,
)
d_stage.y.tuner.peak_choice = TUNE_METHOD_PEAK_CHOICE
d_stage.y.tuner.num = 35
d_stage.y.tuner.width = axis_tune_range.dy.get()     # 10

d_stage.y.pre_tune_method = dy_pretune_hook
d_stage.y.post_tune_method = dy_posttune_hook
