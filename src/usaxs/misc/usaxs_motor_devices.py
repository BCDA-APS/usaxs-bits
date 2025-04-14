"""
motor customizations

TunableEpicsMotor2 adds tuning of motor using lineup2 code

TunableEpicsMotor2WTolerance adds tolerance to TunableEpicsMotor2WTolerance
    .tolerance = 0.000_006 which is ~0.02 arc sec for AR stage. MR is 0.03 arc sec
    impact of tolerance on tuning shoudl be small for now.

"""

__all__ = [
    "TunableEpicsMotor2" "TunableEpicsMotor2WTolerance",
]


# from apstools.devices import AxisTunerMixin
from ophyd import Component
from ophyd import Device
from ophyd import EpicsMotor
from ophyd import PositionerBase
from ophyd import Signal
from ophyd.status import wait as status_wait


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
        self.points = points
        self.tune_range = tune_range
        self.peak_factor = peak_factor
        self.width_factor = width_factor
        self.feature = feature
        self.nscans = nscans
        self.signal_stats = signal_stats

    pre_tune_hook = None
    post_tune_hook = None



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
