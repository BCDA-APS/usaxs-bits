"""
FX4, a QuadEM device

- [Manufacturer](https://pyramid.tech/products/fx4?srsltid=AfmBOopEl09IDYHWT7y9fWXEt_lyWIPq9h34qcLBBXz_nupw8dw-Gep3)
- Copied and modified from (POLAR BITS)[https://github.com/BCDA-APS/polar-bits/blob/main/src/id4_common/devices/quadems.py].
- Consider this advice from (apstools)[https://bcda-aps.github.io/apstools/dev/examples/de_quadem_continuous.html].
"""

from ophyd import Component
from ophyd import EpicsSignalRO
from ophyd import Kind
from ophyd import QuadEM
from ophyd.quadem import QuadEMPort
from ophyd.areadetector.plugins import PluginBase_V34
from ophyd.areadetector.plugins import StatsPlugin_V34

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
    """

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

    def _post_connect_setup(self):
        """Apply hints that require EPICS connection."""
        for i in range(1, 5):
            getattr(self, f"current{i}").mean_value.kind = Kind.hinted

    @property
    def preset_monitor(self):
        """
        Return the averaging_time signal as the count-time preset for scan
        plans.
        """
        return self.averaging_time
