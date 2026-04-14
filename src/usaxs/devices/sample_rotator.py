"""
Sample rotator device for the 12-ID-E USAXS instrument (PI C867 motor).

The sample rotator continuously jogs the sample at a preset speed while data
are collected, averaging over the same sample area at each scan point.  It is
intentionally not part of the normal Bluesky motor API — rotation is started
by asserting a jog PV and stopped by writing to the stop PV.

Note
----
The motor counter in the EPICS IOC can overflow if left running too long;
occasional stop/reset cycles are required to prevent it from halting mid-scan.
"""

from ophyd import Component
from ophyd import Device
from ophyd import EpicsSignal
from ophyd import EpicsSignalRO
from ophyd.status import Status
from ophyd.utils.epics_pvs import raise_if_disconnected


class SampleRotatorHoming(Device):
    """Sub-device that exposes the motor ``HOMF`` / ``HOMR`` homing signals.

    ``forward`` — trigger a forward home search (``.HOMF``).
    ``reverse`` — trigger a reverse home search (``.HOMR``).
    """

    forward = Component(EpicsSignal, ".HOMF", kind="omitted", auto_monitor=True)
    reverse = Component(EpicsSignal, ".HOMR", kind="omitted", auto_monitor=True)

    def set(self, value: str, timeout: float = 10) -> Status:
        """Trigger a home search and return a Status that completes when done.

        Parameters
        ----------
        value : str
            Either ``"forward"`` or ``"reverse"``.
        timeout : float
            Maximum seconds to wait for the home move to complete.

        Returns
        -------
        ophyd.status.Status
            Completed status object.

        Raises
        ------
        KeyError
            If *value* is not ``"forward"`` or ``"reverse"``.
        """
        if not hasattr(self, value):
            raise KeyError("either 'forward' or 'reverse'" f", not: '{value}'")
        signal = getattr(self, value)

        st = Status(self, timeout=timeout)

        def put_cb(**kwargs) -> None:
            st._finished(success=True)

        signal.put(1, use_complete=True, callback=put_cb)
        st.wait(timeout=timeout)
        return st


class SampleRotator(Device):
    """EPICS motor used to rotate the sample continuously during data collection.

    Exposes jog, stop, homing, and readback signals from a standard EPICS motor
    record without implementing the full positioner interface.  The rotation
    speed is configured in EPICS; only jog-start / jog-stop is controlled here.

    ``home``          — homing sub-device (:class:`SampleRotatorHoming`).
    ``jog_forward``   — assert to start forward continuous rotation (``.JOGF``).
    ``jog_reverse``   — assert to start reverse continuous rotation (``.JOGR``).
    ``motor_done_move``— True when the motor is not moving (``.DMOV``).
    ``motor_is_moving``— True while the motor is moving (``.MOVN``).
    ``motor_stop``    — write 1 to stop motion immediately (``.STOP``).
    ``speed``         — current motor speed (``.S``).
    ``user_readback`` — current angular position (``.RBV``).
    ``velocity``      — motor velocity setting (``.VELO``).
    """

    home = Component(SampleRotatorHoming, "")
    jog_forward = Component(EpicsSignal, ".JOGF", kind="omitted", auto_monitor=True)
    jog_reverse = Component(EpicsSignal, ".JOGR", kind="omitted", auto_monitor=True)

    motor_done_move = Component(EpicsSignalRO, ".DMOV", kind="omitted", auto_monitor=True)
    motor_is_moving = Component(EpicsSignalRO, ".MOVN", kind="omitted", auto_monitor=True)
    motor_stop = Component(EpicsSignal, ".STOP", kind="omitted", auto_monitor=True)
    speed = Component(EpicsSignal, ".S", kind="config")
    user_readback = Component(EpicsSignalRO, ".RBV", kind="hinted", auto_monitor=True)
    velocity = Component(EpicsSignal, ".VELO", kind="config")

    @raise_if_disconnected
    def stop(self, *, success: bool = False) -> None:
        """Stop rotation immediately by writing 1 to the motor stop PV."""
        self.motor_stop.put(1, wait=False)
        super().stop(success=success)
