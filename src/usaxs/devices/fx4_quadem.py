"""
FX4 quad electrometer support for the 12-ID-E USAXS instrument.

The FX4 replaces the Femto amplifier / V-F converter / scaler counting chain
for UPD, TRD and I0.  See ``PLAN.md`` and ``docs/FX4_config_cheatsheet.md``.

Classes
-------
``QuadFX4``
    The electrometer itself.  Adds to ophyd's ``QuadEM``: ``TriggerPolarity``
    (FX4-only), the time-series control records used by fly scans, and a
    ``trigger()`` that works on an unstaged device.
``FX4AutorangeDevice``
    The IOC sequence program (``usxFX4:FX4:seq01:``) that ranges the
    electrometer.  Analogous to ``amplifiers.AmplifierAutoDevice`` but with no
    Femto gain, no V-F converter and no counts.
``FX4DetectorControls``
    Binds a detector nickname to (electrometer, channel, autoranger), the way
    ``amplifiers.DetectorAmplifierAutorangeDevice`` bound (scaler, channel,
    Femto, autoranger).

Two hardware facts drive most of the design
-------------------------------------------
1. **The reading is gain-independent**, reported in pA.  Nothing downstream
   divides by a gain; transmission and data reduction are just ``diode / I0``.
   Range readbacks are diagnostics only.
2. **Range is per-device, not per-channel.**  All four channels digitise at the
   same range, and the sequence program's ``channel`` record selects which one
   it watches.  UPD (ch 1) and TRD (ch 4) share one FX4 and are never used at
   the same time, so plans must point ``channel`` at whichever is in use --
   see :func:`usaxs.plans.fx4_setup.select_fx4_channel`.

References
----------
- [Manufacturer](https://pyramid.tech/products/fx4)
- Copied and modified from (POLAR BITS)[https://github.com/BCDA-APS/polar-bits/blob/main/src/id4_common/devices/quadems.py].
- Consider this advice from (apstools)[https://bcda-aps.github.io/apstools/dev/examples/de_quadem_continuous.html].
"""

import logging
from collections import OrderedDict

from apsbits.core.instrument_init import oregistry
from bluesky import plan_stubs as bps
from bluesky.utils import plan
from ophyd import ADComponent
from ophyd import Component
from ophyd import Device
from ophyd import DynamicDeviceComponent
from ophyd import EpicsSignal
from ophyd import EpicsSignalRO
from ophyd import FormattedComponent
from ophyd import Kind
from ophyd import QuadEM
from ophyd import Signal
from ophyd.areadetector.plugins import PluginBase_V34
from ophyd.areadetector.plugins import StatsPlugin_V34
from ophyd.areadetector.trigger_mixins import SingleTrigger
from ophyd.quadem import QuadEMPort

logger = logging.getLogger(__name__)

NUM_AUTORANGE_RANGES = 5
"""Number of background records (``bkg0``..``bkg4``) in the sequence program."""

FX4_MINIMUM_SETTLING_TIME = 0.01
"""Shortest sensible pause after asking the sequence program to change range."""

class PluginMixin(PluginBase_V34):
    """Remove property attribute found in AD IOCs now."""

    _asyn_pipeline_configuration_names = None

class StatsPlugin(PluginMixin, StatsPlugin_V34):
    """Remove property attribute found in AD IOCs now."""

    _default_configuration_attrs = (
        StatsPlugin_V34._default_configuration_attrs
        + (
            "array_size",
            "blocking_callbacks",
            "color_mode",
            "data_type",
            "dimensions",
            "enable",
            "driver_version",
            "compute_statistics",
            "bgd_width",
            "compute_centroid",
            "centroid_threshold",
            "compute_profiles",
            "profile_average",
            "profile_centroid",
            "profile_cursor",
            "profile_size",
            "profile_threshold",
            "cursor",
            "compute_histogram",
            "hist_entropy",
            "hist_max",
            "hist_min",
            "hist_size",
            "histogram",
            "hist_above",
            "hist_below",
            "histogram_x",
        )
    )

    _default_read_attrs = StatsPlugin_V34._default_read_attrs + (
        "max_value",
        "max_xy.x",
        "max_xy.y",
        "mean_value",
        "min_value",
        "min_xy.x",
        "min_xy.y",
        "net",
        "total",
        "centroid.x",
        "centroid.y",
        "sigma_xy",
        "sigma.x",
        "sigma.y",
        "orientation",
        "kurtosis",
        "skew",
        "centroid_total",
        "eccentricity",
    )

    # These generates confusion as it's the exact same as sigma.x and .y
    sigma_x = None
    sigma_y = None

    # NOTE: auto-kind subscriptions are intentionally NOT installed in
    # __init__. The compute_* components are lazy ADComponents, so accessing
    # them at __init__ time triggers wait_for_connection() and breaks
    # ``make_devices(connect=False)`` when the IOC is off. Owning detectors
    # should call ``start_auto_kind()`` from their ``default_settings()`` (run
    # by ``connect_device`` after the connection is live) if they want
    # auto-updated kinds.

    def start_auto_kind(self):
        """Subscribe all compute signals to auto-update component kinds."""
        self.compute_statistics.subscribe(self._control_stats)
        self.compute_centroid.subscribe(self._control_centroid)
        self.compute_profiles.subscribe(self._control_profile)
        self.compute_histogram.subscribe(self._control_histogram)

    def stop_auto_kind(self):
        """Unsubscribe all compute signals from auto kind updates."""
        for item in (
            "compute_statistics",
            "compute_centroid",
            "compute_profiles",
            "compute_histogram",
        ):
            getattr(self, item).unsubscribe_all()

    def _control_stats(self, value, **kwargs):
        items = (
            "bgd_width",
            "max_value",
            "min_value",
            "max_xy",
            "max_xy.x",
            "max_xy.y",
            "min_xy",
            "min_xy.x",
            "min_xy.y",
            "total",
            "net",
            "mean_value",
            "sigma_value",
        )
        k = "normal" if value == "Yes" else "omitted"
        for item in items:
            getattr(self, item).kind = k

    def _control_centroid(self, value, **kwargs):
        items = (
            "centroid",
            "centroid.x",
            "centroid.y",
            "sigma_xy",
            "sigma",
            "sigma.x",
            "sigma.y",
            "centroid_total",
            "eccentricity",
            "orientation",
            "kurtosis",
            "skew",
        )
        k = "normal" if value == "Yes" else "omitted"
        for item in items:
            getattr(self, item).kind = k

    def _control_profile(self, value, **kwargs):
        items = [item for item in self.component_names if "profile" in item]
        k = "normal" if value == "Yes" else "omitted"
        for item in items:
            getattr(self, item).kind = k

    def _control_histogram(self, value, **kwargs):
        items = [item for item in self.component_names if "hist" in item]
        k = "normal" if value == "Yes" else "omitted"
        for item in items:
            getattr(self, item).kind = k

class StatsPluginQuadEM(StatsPlugin):
    """StatsPlugin variant for QuadEM that uses ``config`` kind by default.

    Auto-kind subscriptions from ``StatsPlugin.start_auto_kind`` are not
    installed here — QuadEM users want the stats plugin to stay at
    ``config`` regardless of which compute_* signals are enabled.

    Also adds the **time-series control** records used by fly scans.
    ``StatsPlugin_V34`` supplies the TS *data* arrays (``ts_mean_value``,
    ``ts_total``, ``ts_sigma``, ``ts_timestamp``) but not the records that arm
    and size the series -- in newer ADCore those live on a separate
    ``TimeSeriesPlugin``.  The FX4 IOC exposes them on the stats plugin itself
    (``Current1:TSControl`` etc.), matching the older layout.

    .. warning::
       The suffixes below are taken from ``docs/FX4_config_cheatsheet.md`` and
       have **not** been checked against the live IOC.  Depending on the ADCore
       build they may be ``Current1:TS:TSControl`` instead.  Confirm with::

           dbl "usxFX4:FX4:Current1:*" | grep -i ts
    """

    ts_control = ADComponent(EpicsSignal, "TSControl", kind="config", string=True)
    ts_num_points = ADComponent(EpicsSignal, "TSNumPoints", kind="config")
    ts_current_point = ADComponent(EpicsSignalRO, "TSCurrentPoint", kind="config")
    ts_acquire_mode = ADComponent(
        EpicsSignal, "TSAcquireMode", kind="config", string=True
    )
    ts_acquiring = ADComponent(EpicsSignalRO, "TSAcquiring", kind="omitted")

    def __init__(self, *args, **kwargs):
        """Initialize and force the plugin to ``config`` kind."""
        super().__init__(*args, **kwargs)
        self.kind = "config"

class QuadFX4(QuadEM):
    """
    QuadEM device with FX4 features.

    Example::

        fx4 = QuadFX4("usxFX4:FX4:", name="fx4")
    """
    conf = Component(QuadEMPort, port_name="FX4")

    # FX4-only: which logic level of the gate is the integrating level.
    # 0 = Positive (integrate while HIGH, read out on falling edge)
    # 1 = Negative (integrate while LOW, read out on rising edge)  <- ours
    # Not present in ophyd's QuadEM.  Ignored outside "Ext. bulb" mode.
    trigger_polarity = Component(
        EpicsSignal, "TriggerPolarity", kind="config", string=True
    )

    image = None  # image not supported
    current1 = Component(StatsPluginQuadEM, "Current1:")
    current2 = Component(StatsPluginQuadEM, "Current2:")
    current3 = Component(StatsPluginQuadEM, "Current3:")
    current4 = Component(StatsPluginQuadEM, "Current4:")

    sum_all = Component(StatsPluginQuadEM, "SumAll:")

    # The way the QuadEM support computes things is a bit complicated, so
    # will expose main screen here.

    sumall_mean = Component(EpicsSignalRO, "SumAll:MeanValue_RBV")
    sumall_fast = Component(EpicsSignalRO, "SumAllAve")
    sumall_sigma = Component(EpicsSignalRO, "SumAll:Sigma_RBV")

    sumx_mean = Component(EpicsSignalRO, "SumX:MeanValue_RBV")
    sumx_fast = Component(EpicsSignalRO, "SumXAve")
    sumx_sigma = Component(EpicsSignalRO, "SumX:Sigma_RBV")

    sumy_mean = Component(EpicsSignalRO, "SumY:MeanValue_RBV")
    sumy_fast = Component(EpicsSignalRO, "SumYAve")
    sumy_sigma = Component(EpicsSignalRO, "SumY:Sigma_RBV")

    diffx_mean = Component(EpicsSignalRO, "DiffX:MeanValue_RBV")
    diffx_fast = Component(EpicsSignalRO, "DiffXAve")
    diffx_sigma = Component(EpicsSignalRO, "DiffX:Sigma_RBV")

    diffy_mean = Component(EpicsSignalRO, "DiffY:MeanValue_RBV")
    diffy_fast = Component(EpicsSignalRO, "DiffYAve")
    diffy_sigma = Component(EpicsSignalRO, "DiffY:Sigma_RBV")

    posx_mean = Component(EpicsSignalRO, "PosX:MeanValue_RBV")
    posx_fast = Component(EpicsSignalRO, "PositionXAve")
    posx_sigma = Component(EpicsSignalRO, "PosX:Sigma_RBV")

    posy_mean = Component(EpicsSignalRO, "PosY:MeanValue_RBV")
    posy_fast = Component(EpicsSignalRO, "PositionYAve")
    posy_sigma = Component(EpicsSignalRO, "PosY:Sigma_RBV")

    def __init__(self, *args, **kwargs):
        """Initialize without triggering lazy EPICS access on the channels.

        The upstream ``QuadEM.__init__`` sets
        ``current{i}.mean_value.kind = Kind.hinted`` at instantiation, which
        forces a ``wait_for_connection()`` on each channel's lazy stats
        plugin. That breaks ``make_devices(connect=False)`` when the IOC is
        off. We bypass it here and re-apply the hint in
        ``_post_connect_setup`` once EPICS is live.
        """
        super(QuadEM, self).__init__(*args, **kwargs)
        self.stage_sigs.update([("acquire", 0), ("acquire_mode", 2)])
        self._acquisition_signal = self.acquire
        self._acquire_sub_cid = None

    def _post_connect_setup(self):
        """Apply hints that require EPICS connection."""
        for i in range(1, 5):
            getattr(self, f"current{i}").mean_value.kind = Kind.hinted

    # ------------------------------------------------------------------
    # Triggering without staging
    #
    # ``SingleTrigger.trigger()`` refuses to run unless the device is staged,
    # and installs the acquire-completion subscription only in ``stage()``.
    # Every USAXS call site does a bare ``bps.trigger(...)`` on an unstaged
    # device, because the ``ScalerCH`` this replaces allowed it (uascan_plan,
    # no_run_trigger_and_wait, the autoscale loop, sample_rotator_plans).
    # Rather than wrap a dozen plans in stage/unstage -- which would also
    # change what a suspender replays -- install the subscription on first use
    # and keep it.
    # ------------------------------------------------------------------

    def _ensure_acquire_subscription(self):
        """Install the acquire-completion callback once, and keep it."""
        if self._acquire_sub_cid is None:
            self._acquire_sub_cid = self._acquisition_signal.subscribe(
                self._acquire_changed
            )

    def trigger(self):
        """Trigger one acquisition.  Does not require the device to be staged.

        Writes ``Acquire = 1`` and returns a status that completes on the
        falling edge of ``Acquire``.

        For that edge to mean "the mean is ready", the stats plugins must have
        ``CallbacksBlock = Yes`` -- otherwise ``Acquire`` clears as soon as the
        driver is done and ``MeanValue_RBV`` may still hold the previous
        reading.  ``plans.fx4_setup.fx4_scaler_mode`` sets this.

        Returns
        -------
        ophyd.status.StatusBase
            Completes when the acquisition finishes.
        """
        self._ensure_acquire_subscription()
        self._status = self._status_type(self)
        self._acquisition_signal.put(1, wait=False)
        return self._status

    def stage(self):
        """Stage the device, keeping our permanent acquire subscription.

        Bypasses ``SingleTrigger.stage``, which would add a second, duplicate
        subscription that ``unstage`` would then remove -- leaving unstaged
        triggering broken afterwards.
        """
        self._ensure_acquire_subscription()
        return super(SingleTrigger, self).stage()

    def unstage(self):
        """Unstage the device without removing the acquire subscription."""
        return super(SingleTrigger, self).unstage()

    @property
    def preset_monitor(self):
        """
        Return the averaging_time signal as the count-time preset for scan
        plans.
        """
        return self.averaging_time

    def channel_stats(self, channel):
        """Return the stats plugin for a 1-based channel number.

        Parameters
        ----------
        channel : int
            Channel number, 1 to 4.

        Returns
        -------
        StatsPluginQuadEM
            The ``current<channel>`` plugin.
        """
        if channel not in (1, 2, 3, 4):
            raise ValueError(f"channel must be 1..4, given: {channel}")
        return getattr(self, f"current{channel}")


class FX4RangeConflictError(RuntimeError):
    """Raised when two channels on one FX4 are asked to autorange together.

    An FX4 has a single ``Range`` shared by all four channels (see the module
    docstring), so converging one channel necessarily de-converges another.
    Refusing is better than returning a plausible-looking wrong number.
    """


class FX4AutoscaleError(RuntimeError):
    """Raised when the FX4 autorange sequence program fails to converge."""


class FX4AutorangeSettings:
    """Values allowed for the sequence program's ``mode`` record."""

    automatic = "automatic"
    auto_background = "auto+background"
    manual = "manual"


class FX4BackgroundDevice(Device):
    """Dark-current records for one range index of the sequence program.

    The Femto-era ``AmplfierGainDevice`` also carried a ``gain<n>`` record.
    The FX4 sequence program has no such record -- the reading is
    gain-independent (module docstring) -- so only the background pair remains.
    """

    background = FormattedComponent(EpicsSignal, "{self.prefix}bkg{self._range_num}")
    background_error = FormattedComponent(
        EpicsSignal, "{self.prefix}bkgErr{self._range_num}"
    )

    def __init__(self, prefix, range_num=None, **kwargs):
        """Initialize for one range index.

        Parameters
        ----------
        prefix : str
            Sequence-program prefix, e.g. ``usxFX4:FX4:seq01:``.
        range_num : int
            Range index, 0 to ``NUM_AUTORANGE_RANGES - 1``.
        **kwargs
            Passed to ``Device``.
        """
        if range_num is None:
            raise ValueError("Must provide `range_num=` keyword argument.")
        self._range_num = range_num
        super().__init__(prefix, **kwargs)


def _background_subgroup(cls, nm, ranges):
    """Build the ``ranges`` DynamicDeviceComponent definition.

    Parameters
    ----------
    cls : type
        Device class for each range, normally ``FX4BackgroundDevice``.
    nm : str
        Attribute-name prefix, e.g. ``"range"``.
    ranges : iterable of int
        Range indices.

    Returns
    -------
    collections.OrderedDict
        Definition suitable for ``DynamicDeviceComponent``.
    """
    defn = OrderedDict()
    for i in ranges:
        defn[f"{nm}{i}"] = (cls, "", {"range_num": i})
    return defn


class FX4AutorangeDevice(Device):
    """Ophyd support for the FX4 autorange sequence program.

    Example::

        fx4_autorange = FX4AutorangeDevice("usxFX4:FX4:seq01:", name="...")

    Differences from the Femto-era ``amplifiers.AmplifierAutoDevice``, all of
    them consequences of the FX4 having no Femto amplifier, no V-F converter
    and no counts:

    ===================  ====================================================
    gone                 why
    ===================  ====================================================
    ``gain``             reading is gain-independent
    ``gain0``..``gain4``  same
    ``counts_per_volt``  no V-F converter
    ``lucounts``         no counts
    ``lurate``           no count rate
    ===================  ====================================================

    ===============  ========================================================
    new              meaning
    ===============  ========================================================
    ``channel``      **which FX4 channel this program watches** (1..4).  One
                     range serves all four channels, so this must be pointed
                     at whichever detector is in use.
    ``current``      the current the program is ranging on, pA
    ``mode_rdbk``    readback of ``mode``
    ``speed``        sequence-program loop speed
    ``debug``        sequence-program debug level
    ===============  ========================================================
    """

    # --- range selection ---
    reqrange = Component(EpicsSignal, "reqrange", kind="config")
    lurange = Component(EpicsSignalRO, "lurange", kind="normal")
    channel = Component(EpicsSignal, "channel", kind="config")

    # --- mode ---
    mode = Component(EpicsSignal, "mode", kind="config")
    mode_rdbk = Component(EpicsSignalRO, "modeRdbk", kind="config")
    selected = Component(EpicsSignal, "selected", kind="omitted")
    updating = Component(EpicsSignalRO, "updating", kind="omitted")

    # --- thresholds the IOC uses to decide when to change range ---
    # Tuned in EPICS and owned by the IOC.  Bluesky reads these but must NOT
    # write them: the plans used to push stale count-rate values from soft
    # signals at every scan, wiping the tuning (see PLAN.md Q18).
    gainU = Component(EpicsSignal, "gainU", kind="config")
    gainD = Component(EpicsSignal, "gainD", kind="config")

    # --- readings ---
    current = Component(EpicsSignalRO, "current", kind="normal")
    lucurrent = Component(EpicsSignalRO, "lucurrent", kind="normal")

    # --- dark currents, one pair per range ---
    ranges = DynamicDeviceComponent(
        _background_subgroup(
            FX4BackgroundDevice, "range", range(NUM_AUTORANGE_RANGES)
        )
    )

    # --- housekeeping ---
    speed = Component(EpicsSignal, "speed", kind="config")
    debug = Component(EpicsSignal, "debug", kind="omitted")

    # Sanity bounds for the Bluesky-side convergence check, in pA.  The IOC's
    # own gainU/gainD do the actual ranging; these only answer "did it settle
    # somewhere sensible, and is it not railed?".
    # TODO: set on the instrument -- placeholders until the FX4 ranges and
    # typical UPD/TRD currents are measured (PLAN.md section 4.1).
    max_current = Component(Signal, value=1.0e9, kind="config")
    min_current = Component(Signal, value=1.0e0, kind="config")

    settling_time = Component(Signal, value=0.08, kind="config")

    @plan
    def setRange(self, target):
        """Plan: request a range index from the sequence program.

        Parameters
        ----------
        target : int
            Range index, 0 to ``NUM_AUTORANGE_RANGES - 1``.

        Yields
        ------
        Bluesky messages consumed by the RunEngine.
        """
        if not 0 <= int(target) < NUM_AUTORANGE_RANGES:
            raise ValueError(
                f"range must be 0..{NUM_AUTORANGE_RANGES - 1}, given: {target}"
            )
        yield from bps.mv(self.reqrange, int(target))

    @plan
    def setChannel(self, channel):
        """Plan: point the sequence program at an FX4 channel.

        One ``Range`` serves all four channels, so this decides which detector
        the autoranger optimises for.  Everything else on the same FX4 is
        ranged incidentally and may be railed.

        Parameters
        ----------
        channel : int
            FX4 channel number, 1 to 4.

        Yields
        ------
        Bluesky messages consumed by the RunEngine.
        """
        if channel not in (1, 2, 3, 4):
            raise ValueError(f"channel must be 1..4, given: {channel}")
        yield from bps.mv(self.channel, channel)
        yield from bps.sleep(max(FX4_MINIMUM_SETTLING_TIME, self.settling_time.get()))

    @property
    def isUpdating(self):
        """Return True if the sequence program is actively changing range."""
        v = self.mode.get() in (1, FX4AutorangeSettings.auto_background)
        if v:
            v = self.updating.get() in (1, "Updating")
        return v


class FX4DetectorControls(Device):
    """Bind a detector nickname to (electrometer, channel, autoranger).

    The FX4-era counterpart of
    ``amplifiers.DetectorAmplifierAutorangeDevice``, which bound (scaler,
    scaler channel, Femto amplifier, autorange sequence program).  There is no
    scaler and no Femto here, and the autoranger is optional: a detector on a
    fixed range (I0 and I00 for now) passes ``autorange=None``.

    Declared in ``configs/*.yml``::

        usaxs.devices.fx4_quadem.FX4DetectorControls:
          - name: upd_controls
            nickname: UPD
            quadem: fx4
            channel: 1
            autorange: fx4_autorange
          - name: I0_controls
            nickname: I0
            quadem: fx42
            channel: 1
    """

    def __init__(self, nickname, quadem, channel, autorange=None, **kwargs):
        """Resolve the referenced devices from the registry.

        Parameters
        ----------
        nickname : str
            Human-readable detector name, e.g. ``"UPD"``.
        quadem : str
            Registry name of the ``QuadFX4``, e.g. ``"fx4"``.
        channel : int
            FX4 channel number, 1 to 4.
        autorange : str, optional
            Registry name of the ``FX4AutorangeDevice`` serving this channel.
            ``None`` means the detector runs at a fixed, manually set range and
            is skipped by the autoscale plans.
        **kwargs
            Passed to ``Device``.
        """
        if not isinstance(nickname, str):
            raise ValueError(
                "'nickname' should be of 'str' type,"
                f" received type: {type(nickname)}"
            )
        self.nickname = nickname
        self.quadem = oregistry[quadem]
        if not isinstance(self.quadem, QuadFX4):
            raise ValueError(
                "'quadem' should name a 'QuadFX4' type,"
                f" received type: {type(self.quadem)}"
            )

        self.channel_number = int(channel)
        self.stats = self.quadem.channel_stats(self.channel_number)
        self.signal = self.stats.mean_value

        self.auto = None
        if autorange is not None:
            self.auto = oregistry[autorange]
            if not isinstance(self.auto, FX4AutorangeDevice):
                raise ValueError(
                    "'autorange' should name an 'FX4AutorangeDevice' type,"
                    f" received type: {type(self.auto)}"
                )

        super().__init__("", **kwargs)

    @property
    def autoranged(self):
        """Return True if this detector has an autorange sequence program."""
        return self.auto is not None

    @property
    def count_time(self):
        """Return the electrometer's count-time signal (``AveragingTime``)."""
        return self.quadem.averaging_time

    def __repr__(self):
        """Return a short description naming the box and channel."""
        mode = "auto" if self.autoranged else "fixed range"
        return (
            f"<FX4DetectorControls {self.nickname}:"
            f" {self.quadem.name} ch{self.channel_number} ({mode})>"
        )
