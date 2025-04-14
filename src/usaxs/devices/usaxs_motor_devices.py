"""
motor customizations

TunableEpicsMotor2 adds tuning of motor using lineup2 code

TunableEpicsMotor2WTolerance adds tolerance to TunableEpicsMotor2WTolerance
    .tolerance = 0.000_006 which is ~0.02 arc sec for AR stage. MR is 0.03 arc sec
    impact of tolerance on tuning shoudl be small for now.

"""

# from apstools.devices import AxisTunerMixin
from apstools.plans import lineup2
from ophyd import Component
from ophyd import Device
from ophyd import EpicsMotor
from ophyd import PositionerBase
from ophyd import Signal
from ophyd.status import wait as status_wait

from . import scaler0


class TunableEpicsMotor2(EpicsMotor):
    """
    Enhance EpicsMotor with parameters for automatic alignment.

    Example::

        uuids = yield from motor.tune()

    retunrs list of uuids for the tune scans (default 1)
    this list can be plotted using plotxy() from APStools

    """

    def __init__(
        self,
        *args,
        detectors: list = None,
        tune_range: Signal = None,
        points: int = 31,
        peak_factor: float = 2.5,
        width_factor: float = 0.8,
        feature: str = "centroid",
        nscans: int = 1,
        signal_stats=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)  # default EpicsaMotor setup
        self.detectors = detectors
        self.points = points
        self.tune_range = tune_range
        self.peak_factor = peak_factor
        self.width_factor = width_factor
        self.feature = feature
        self.nscans = nscans
        self.signal_stats = signal_stats

    pre_tune_hook = None
    post_tune_hook = None

    def tune(self, md=None):
        _md = {}
        _md.update(md or {})

        def _inner():
            if self.pre_tune_hook is not None:
                yield from self.pre_tune_hook()

            # TODO: if self.signal_stats is None, create one and use it
            print(self.detectors)
            yield from lineup2(
                # self.detectors,
                [scaler0],
                self,  # this motor is the mover
                -self.tune_range.get(),  # rel_start
                self.tune_range.get(),  # rel_end
                self.points,
                peak_factor=self.peak_factor,
                width_factor=self.width_factor,
                feature=self.feature,
                nscans=self.nscans,
                signal_stats=self.signal_stats,
                md=_md,
            )
            # TODO: Need to report from signal_stats
            # Motor: m1
            # ========== ==================
            # statistic  noisy
            # ========== ==================
            # n          11
            # centroid   0.8237310041584432
            # sigma      0.6472728236075987
            # x_at_max_y 0.90963
            # max_y      7549.789982466793
            # min_y      22.338609615249936
            # mean_y     872.4897763435542
            # stddev_y   2236.733696611285
            # ========== ==================

            if self.post_tune_hook is not None:
                yield from self.post_tune_hook()

        return (yield from _inner())


# copied from https://github.com/NSLS-II-SST/sst_base/blob/5c019a3f0feb9032cfa1c5a5e84b9322eb5b309d/sst_base/positioners.py#L8-L72


class DeadbandMixin(Device, PositionerBase):
    """
    Should be the leftmost class in the inheritance list so that it grabs move first!
    Must be combined with either EpicsMotor or PVPositioner, or some other class
    that has a done_value attribute
    An EpicsMotor subclass that has an absolute tolerance for moves.
    If the readback is within tolerance of the setpoint, the MoveStatus
    is marked as finished, even if the motor is still settling.
    This prevents motors with long, but irrelevant, settling times from
    adding overhead to scans.
    """

    tolerance = Component(Signal, value=-1, kind="config")
    move_latch = Component(Signal, value=0, kind="omitted")

    def _done_moving(self, success=True, timestamp=None, value=None, **kwargs):
        """Call when motion has completed.  Runs ``SUB_DONE`` subscription."""
        if self.move_latch.get():
            # print(f"{timestamp}: {self.name} marked done")
            if success:
                self._run_subs(sub_type=self.SUB_DONE, timestamp=timestamp, value=value)

            self._run_subs(
                sub_type=self._SUB_REQ_DONE, success=success, timestamp=timestamp
            )
            self._reset_sub(self._SUB_REQ_DONE)
            self.move_latch.put(0)

    def move(self, position, wait=True, **kwargs):
        tolerance = self.tolerance.get()

        if tolerance < 0:
            self.move_latch.put(1)
            return super().move(position, wait=wait, **kwargs)
        else:
            status = super().move(position, wait=False, **kwargs)
            setpoint = position
            done_value = getattr(self, "done_value", 1)

            def check_deadband(value, timestamp, **kwargs):
                if abs(value - setpoint) < tolerance:
                    self._done_moving(
                        timestamp=timestamp, success=True, value=done_value
                    )
                else:
                    pass
                    # print(f"{timestamp}: {self.name}, {value} not within {tolerance} of {setpoint}")

            def clear_deadband(*args, timestamp, **kwargs):
                # print(f"{timestamp}: Ran deadband clear for {self.name}")
                self.clear_sub(check_deadband, event_type=self.SUB_READBACK)

            self.subscribe(clear_deadband, event_type=self._SUB_REQ_DONE, run=False)
            self.move_latch.put(1)
            self.subscribe(check_deadband, event_type=self.SUB_READBACK, run=True)

            try:
                if wait:
                    status_wait(status)
            except KeyboardInterrupt:
                self.stop()
                raise

            return status


class TunableEpicsMotor2WTolerance(DeadbandMixin, TunableEpicsMotor2):
    tolerance = Component(Signal, value=0.000_006, kind="config")
    # AR guaranteed min step is 0.02 arc second, which is 0.000_0055 degress.
    # MR guarranteed min step is 0.03 arc second, which is 0.000_0083 dgrees
    # set .tolerance same for AR and MR, for step scans AR resolution is more important.
    # this has small impact on tunes and no impact on flyscans.
