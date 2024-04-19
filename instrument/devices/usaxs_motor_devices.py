
"""
motor customizations
"""

__all__ = [
    'UsaxsMotorTunable',
]

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

from apstools.devices import AxisTunerMixin
from ophyd import Component, EpicsMotor, Signal, Device, PositionerBase
from ophyd.status import wait as status_wait

# TODO: check rest of the code for UsaxsMotor and replace with EpicsMotor 
# custom for any overrides (none now)
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
    tolerance = Component(Signal, value=-1, kind='config')
    move_latch = Component(Signal, value=0, kind="omitted")

    def _done_moving(self, success=True, timestamp=None, value=None, **kwargs):
        '''Call when motion has completed.  Runs ``SUB_DONE`` subscription.'''
        if self.move_latch.get():
            # print(f"{timestamp}: {self.name} marked done")
            if success:
                self._run_subs(sub_type=self.SUB_DONE, timestamp=timestamp,
                               value=value)

            self._run_subs(sub_type=self._SUB_REQ_DONE, success=success,
                           timestamp=timestamp)
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
                    self._done_moving(timestamp=timestamp,
                                      success=True,
                                      value=done_value)
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

class XXUsaxsMotor(EpicsMotor): ...

class UsaxsMotorTunable(AxisTunerMixin, EpicsMotor):
    width = Component(Signal, value=0, kind="config")

class UsaxsArMotorTunable(DeadbandMixin, UsaxsMotorTunable):
    tolerance = Component(Signal, value=0.000_01, kind="config")
    # AR guaranteed min step is 0.03 arc second, which is 0.000_008 degress. 
