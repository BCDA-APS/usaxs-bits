"""
Linkam T96 temperature controller support for the 12-ID-E USAXS instrument.

Provides two ophyd device classes:

``Linkam_T96_Device``
    Base device wrapping the Linux-IOC version of the Linkam T96 controller.
    Uses :class:`~apstools.devices.PVPositionerSoftDone` for temperature,
    ramp rate, LNP pump, vacuum, and humidity axes.

``My_Linkam_T96_Device``
    Subclass adding convenience Bluesky plans (``set_target``, ``hold``) and
    utility methods (``readable_time``, ``linkam_report``).

Typical usage::

    tc1 = My_Linkam_T96_Device("IOC:tc1:", name="tc1")
    # current temperature
    tc1.temperature.position
"""

import time

from apstools.devices import PVPositionerSoftDone
from bluesky import plan_stubs as bps
from ophyd import Component
from ophyd import Device
from ophyd import EpicsSignal
from ophyd import EpicsSignalRO
from ophyd import Signal

SECOND = 1
MINUTE = 60 * SECOND
HOUR = 60 * MINUTE
DAY = 24 * HOUR
WEEK = 7 * DAY


class T96Temperature(PVPositionerSoftDone):
    """PVPositionerSoftDone subclass that starts heating when the setpoint moves.

    Adds an ``actuate`` signal (``STARTHEAT``) set to ``"On"`` automatically
    whenever the positioner moves, so the controller begins ramping without
    requiring a separate command.
    """

    actuate = Component(EpicsSignal, "STARTHEAT", kind="config", string=True)
    actuate_value = "On"


class Linkam_T96_Device(Device):
    """Base ophyd device for the Linkam T96 temperature controller (Linux IOC).

    Use ``temperature.position`` to read the current temperature in °C.
    Use ``ramprate.position`` to read the current ramp rate.

    All positioner axes use :class:`~apstools.devices.PVPositionerSoftDone`
    with separate ``*_RBV`` (readback) and ``*:SET`` (setpoint) PVs.
    """

    controller_name = "Linkam T96"
    temperature = Component(
        T96Temperature,
        "",
        readback_pv="TEMP",
        setpoint_pv="SETPOINT:SET",
        tolerance=1.0,
        kind="hinted",
    )
    ramprate = Component(
        PVPositionerSoftDone,
        "",
        readback_pv="RAMPRATE",
        setpoint_pv="RAMPRATE:SET",
        tolerance=1.0,
        kind="hinted",
    )
    units = Component(Signal, value="C", kind="config")
    controller_error = Component(EpicsSignalRO, "CTRLLR:ERR", kind="omitted")
    heater_power = Component(EpicsSignalRO, "POWER", kind="omitted")
    lnp_mode = Component(
        PVPositionerSoftDone,
        "",
        readback_pv="LNP_MODE",
        setpoint_pv="LNP_MODE:SET",
        # tolerance=1.0,
        kind="omitted",
    )
    lnp_speed = Component(
        PVPositionerSoftDone,
        "",
        readback_pv="LNP_SPEED",
        setpoint_pv="LNP_SPEED:SET",
        # tolerance=1.0,
        kind="omitted",
    )
    pressure = Component(EpicsSignalRO, "PRESSURE", kind="omitted")
    vacuum = Component(
        PVPositionerSoftDone,
        "",
        readback_pv="VACUUM",
        setpoint_pv="VACUUM:SET",
        # tolerance=1.0,
        kind="omitted",
    )
    humidity = Component(
        PVPositionerSoftDone,
        "",
        readback_pv="HUMIDITY",
        setpoint_pv="HUMIDITY:SET",
        # tolerance=1.0,
        kind="omitted",
    )

    def __init__(self, *args, **kwargs):
        """Alias ``temperature.name`` to the device name for cleaner logging."""
        super().__init__(*args, **kwargs)
        self.temperature.name = self.name


class My_Linkam_T96_Device(Linkam_T96_Device):
    """Linkam T96 device with convenience Bluesky plans and reporting helpers.

    Adds ``set_target``, ``hold``, ``readable_time``, and ``linkam_report``
    on top of :class:`Linkam_T96_Device`.
    """

    def readable_time(self, duration, rounding=2):
        """Return a human-readable string for *duration* seconds.

        Examples::

            readable_time(425)    -> '7m 5s'
            readable_time(1425)   -> '23m 45s'
            readable_time(21425)  -> '5h 57m 5s'
            readable_time(360)    -> '6m'
            readable_time(62.123) -> '1m 2.12s'

        Parameters
        ----------
        duration : float
            Time in seconds.
        rounding : int
            Decimal places for the seconds field.
        """
        weeks = int(duration / WEEK)
        known = weeks * WEEK

        days = (duration - known) // DAY
        known += days * DAY

        hours = (duration - known) // HOUR
        known += hours * HOUR

        minutes = (duration - known) // MINUTE
        known += minutes * MINUTE

        seconds = round(duration - known, rounding)
        db = dict(w=weeks, d=days, h=hours, m=minutes, s=seconds)

        s = [f"{v}{k}" for k, v in db.items() if v != 0]
        return " ".join(s)

    def log_it(self, text):
        """No-op stub — logging to a file is not yet implemented."""
        pass

    def linkam_report(self):
        """No-op stub — periodic status reporting is not yet implemented."""
        pass

    def set_target(self, value, wait=True):
        """Bluesky plan: move to *value* °C and optionally wait until settled.

        Sets both ``temperature.setpoint`` and ``temperature.actuate`` (``"On"``)
        in one ``bps.mv`` call so the controller starts heating immediately.

        To move without turning on the heater use ``bps.mv`` on the setpoint
        directly::

            yield from bps.mv(tc1.temperature.setpoint, value)

        Parameters
        ----------
        value : float
            Target temperature in °C.
        wait : bool
            If True (default), poll until ``temperature.inposition`` is True,
            logging progress every 60 s via ``linkam_report``.

        Yields
        ------
        Bluesky messages.
        """
        t0 = time.time()
        yield from bps.mv(
            self.temperature.setpoint, value, self.temperature.actuate, "On"
        )
        self.log_it(
            f"Set {self.name} setpoint to" f" {self.temperature.setpoint.get():.2f} C"
        )
        if not wait:
            return

        checkpoint = time.time() + 60
        while not self.temperature.inposition:
            if time.time() >= checkpoint:
                checkpoint = time.time() + 60
                self.linkam_report()
            yield from bps.sleep(0.1)
        self.log_it(f"Done, that took {time.time()-t0:.2f}s")
        self.linkam_report()

    def hold(self, duration):
        """Bluesky plan: hold at the current temperature for *duration* seconds.

        Parameters
        ----------
        duration : float
            Hold time in seconds.

        Yields
        ------
        Bluesky messages.
        """
        self.log_it(f"{self.name} holding for {self.readable_time(duration)}")
        t0 = time.time()
        time_expires = t0 + duration
        while time.time() < time_expires:
            yield from bps.sleep(0.5)
        self.linkam_report()

    def __init__(self, *args, **kwargs):
        """Set tolerance, sync inposition, and read engineering units from EPICS."""
        super().__init__(*args, **kwargs)
        self.temperature.tolerance.put(1.0)
        self.temperature.cb_readback()  # sync the "inposition" computation
        self.units.put(self.temperature.readback.metadata["units"])

    @property
    def ramp(self):
        """Alias for ``ramprate`` (convenience shorthand)."""
        return self.ramprate
