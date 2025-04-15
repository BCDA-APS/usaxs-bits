"""
Linkam temperature controllers: T96 (tc1)
"""

import time

# from apstools.devices import PVPositionerSoftDoneWithStop
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


# first we need to redefine Linkam_T96_Device to add some methods we really want to use.
# then we define the instance we are going to use here.

# new device definition
### now we can define our instance...


"""
Linkam temperature controllers
This is modified version of APS tools devices code
for new linkam TC1 version
++++++++++++++++++++++++++++++

.. autosummary::

   ~Linkam_T96_Device
"""


# this makes temperature to automatically start heating when changed
class T96Temperature(PVPositionerSoftDone):
    """Temperature control component for Linkam T96 device.

    This class extends PVPositionerSoftDone to provide temperature control functionality
    with automatic heating activation when the temperature is changed.
    """

    actuate = Component(EpicsSignal, "STARTHEAT", kind="config", string=True)
    actuate_value = "On"


class Linkam_T96_Device(Device):
    """
    Linkam model T96 temperature controller
    Linux ioc version

    EXAMPLE::

        tc1 = Linkam_T96("IOC:tc1:", name="tc1")

    to get temperature, ramprate etc:
    linkam_tc1.temperature.position which returns the current T in C

    """

    # use linkam.temperature.position to get the value, this is positoner...
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
        """Initialize the Linkam T96 device.

        Args:
            *args: Variable length argument list.
            **kwargs: Arbitrary keyword arguments.
        """
        super().__init__(*args, **kwargs)

        # temperature component is the main value
        self.temperature.name = self.name

    # these are unused or old things we are not using
    # # #ramp_at_limit = Component(EpicsSignalRO, "rampAtLimit_RBV", kind="omitted")
    # stage_config = Component(EpicsSignalRO, "STAGE:CONFIG", kind="omitted")
    # status_error = Component(EpicsSignalRO, "CTRLLR:ERR", kind="omitted")
    # vacuum = Component(EpicsSignal, "VACUUM:SET", kind="omitted")
    # vacuum_at_limit = Component(EpicsSignalRO, "VACUUM", kind="omitted")
    # # #vacuum_limit_readback = Component(
    #     EpicsSignalWithRBV, "vacuumLimit", kind="omitted"
    # )
    # vacuum_status = Component(EpicsSignalRO, "STAT:VAC:CNTRL", kind="omitted")  # calc
    # controller_config = Component(EpicsSignalRO, "CONFIG", kind="omitted")
    # controller_status = Component(EpicsSignalRO, "STATUS", kind="omitted")
    # humidity = Component(EpicsSignalRO, "HUMIDITY", kind="omitted")
    # lnp_mode = Component(EpicsSignal, "LNP_MODE:SET", kind="omitted")
    # lnp_speed = Component(EpicsSignalWithRBV, "LNP_SPEED:SET", kind="omitted")
    # lnp_status = Component(EpicsSignalRO, "STAT:LNP:PUMPING", kind="omitted")
    # vacuum = Component(EpicsSignalRO, "VACUUM", kind="omitted")

    # alias("$(P):CTRLLR:ERR", "$(PA)$(TA):controllerError_RBV")
    # alias("$(P):CONFIG", "$(PA)$(TA):controllerConfig_RBV")
    # alias("$(P):STATUS", "$(PA)$(TA):controllerStatus_RBV")
    # alias("$(P):STAGE:CONFIG", "$(PA)$(TA):stageConfig_RBV")
    # alias("$(P):TEMP", "$(PA)$(TA):temperature_RBV")
    # alias("$(P):STARTHEAT", "$(PA)$(TA):heating")
    # alias("$(P):RAMPRATE:SET", "$(PA)$(TA):rampRate")
    # alias("$(P):RAMPRATE", "$(PA)$(TA):rampRate_RBV")
    # alias("$(P):SETPOINT:SET", "$(PA)$(TA):rampLimit")
    # alias("$(P):SETPOINT", "$(PA)$(TA):rampLimit_RBV")
    # alias("$(P):POWER", "$(PA)$(TA):heaterPower_RBV")
    # alias("$(P):LNP_SPEED", "$(PA)$(TA):lnpSpeed_RBV")
    # alias("$(P):LNP_MODE:SET", "$(PA)$(TA):lnpMode")
    # alias("$(P):LNP_SPEED:SET", "$(PA)$(TA):lnpSpeed")


class My_Linkam_T96_Device(Linkam_T96_Device):
    """
    Linkam model T96 temperature controller
    Linux ioc version
    add additional methods on this device

    EXAMPLE::

        tc1 = My_Linkam_T96_Device("IOC:tc1:", name="tc1")

    to get temperature, ramprate etc:
    linkam_tc1.temperature.position which returns the current T in C

    """

    def readable_time(self, duration, rounding=2):
        """
        Return a string representation of the duration.
        EXAMPLES::
            readable_time(425) --> '7m 5s'
            readable_time(1425) --> '23m 45s'
            readable_time(21425) --> '5h 57m 5s'
            readable_time(360) --> '6m'
            readable_time(62.123) --> '1m 2.12s'
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

    # def log_it(self, text):
    #     """Cheap, lazy way to add to log file.  Gotta be better way..."""
    #     if not log_file_name.exists():
    #         # create the file and header
    #         with open(log_file_name, "w") as f:
    #             f.write(f"# file: {log_file_name}\n")
    #             f.write(f"# created: {datetime.datetime.now()}\n")
    #             f.write(f"# from: {__file__}\n")
    #     with open(log_file_name, "a") as f:
    #         # write the payload
    #         dt = datetime.datetime.now()
    #         # ISO-8601 format time, ms precision
    #         iso8601 = dt.isoformat(sep=" ", timespec="milliseconds")
    #         f.write(f"{iso8601}: {text}\n")

    def linkam_report(self):
        """Report current values for selected controller."""
        # assuming units are "Celsius"
        units = self.units.get()[:1].upper()
        self.log_it(
            f"{self.name}"
            f" T={self.temperature.position:.1f}{units}"
            f" setpoint={self.temperature.setpoint.get():.1f}{units}"
            f" ramp:{self.ramp.setpoint.get()}"
            f" settled: {self.temperature.inposition}"
            f" done: {self.temperature.done.get()}"
        )

    def set_target(self, value, wait=True):
        """
        BS plan: change the temperature setpoint and wait for inposition.
        To change temperature and wait:
        bps.mv(linkam.temperature, value)
        Turns on heater power (if it was off).
        To just change temperature, do not wait (hint: use the setpoint directly):
        bps.mv(linkam.temperature.setpoint, value)
        Does NOT turn on heater power.
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
        """BS plan: hold at temperature for the duration (s)."""
        self.log_it(f"{self.name} holding for {self.readable_time(duration)}")
        t0 = time.time()
        time_expires = t0 + duration
        while time.time() < time_expires:
            yield from bps.sleep(0.5)
        self.linkam_report()
