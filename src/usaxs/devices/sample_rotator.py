
"""
rotate the sample with PI C867 motor
"""

__all__ = [
    "pi_c867",
    ]

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

from ophyd import Component, Device, EpicsSignal, EpicsSignalRO
from ophyd.status import Status
from ophyd.utils.epics_pvs import raise_if_disconnected


class SampleRotatorHoming(Device):

    forward = Component(EpicsSignal, ".HOMF", kind='omitted', auto_monitor=True)
    reverse = Component(EpicsSignal, ".HOMR", kind='omitted', auto_monitor=True)

    def set(self, value, timeout=10):
        """Find the Home pulse in either forward or reverse direction."""
        if not hasattr(self, value):
            raise KeyError(
                "either 'forward' or 'reverse'"
                f", not: '{value}'"
            )
        signal = getattr(self, value)

        st = Status(self, timeout=timeout)

        def put_cb(**kwargs):
            st._finished(success=True)

        signal.put(1, use_complete=True, callback=put_cb)
        st.wait(timeout=timeout)
        return st


class SampleRotator(Device):
    """
    Use an EPICS motor to rotate sample while collecting data.

    Rotate sample with appropriate speed while collecting data
    to integrate over same area on sample for each point.

    Do not interface with normal motor API, but add some of the attributes.

    This motor is intentionally NOT controlled by spec and
    presumably also is not in BS (as a motor). Pushing jog button
    starts rotation at speed which is setup in epics. Switching off
    and on (with resets) is needed since else epics runs out of
    counters and stops mid way.
    """
    home = Component(SampleRotatorHoming, "")
    jog_forward = Component(EpicsSignal, ".JOGF", kind='omitted', auto_monitor=True)
    jog_reverse = Component(EpicsSignal, ".JOGR", kind='omitted', auto_monitor=True)

    motor_done_move = Component(EpicsSignalRO, ".DMOV", kind='omitted', auto_monitor=True)
    motor_is_moving = Component(EpicsSignalRO, '.MOVN', kind='omitted', auto_monitor=True)
    motor_stop = Component(EpicsSignal, ".STOP", kind='omitted', auto_monitor=True)
    speed = Component(EpicsSignal, ".S", kind='config')
    user_readback = Component(EpicsSignalRO, '.RBV', kind='hinted', auto_monitor=True)
    velocity = Component(EpicsSignal, ".VELO", kind='config')

    @raise_if_disconnected
    def stop(self, *, success=False):
        self.motor_stop.put(1, wait=False)
        super().stop(success=success)


pi_c867 = SampleRotator("usxPI:c867:c0:m1", name="pi_c867")
