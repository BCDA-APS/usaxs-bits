"""
Linkam temperature controllers: T96 (tc1)
"""

__all__ = [
    'linkam_tc1',
    ]

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

import warnings
import datetime
import pathlib
import random  # for testing
import timefrom ophyd import Component
from ophyd import Device
from ophyd import EpicsSignal
from ophyd import EpicsSignalRO
from ophyd import EpicsSignalWithRBV
from ophyd import Signalfrom .linkam_support import Linkam_T96_Device
from bluesky import plan_stubs as bps

SECOND = 1
MINUTE = 60 * SECOND
HOUR = 60 * MINUTE
DAY = 24 * HOUR
WEEK = 7 * DAY
# write output to log file in userDir, name=MMDD-HHmm-heater-log.txt
user_dir = EpicsSignalRO("usxLAX:userDir", name="user_dir", string=True)

log_file_name = pathlib.Path(user_dir.get()) / (
    datetime.datetime.now().strftime("%m%d-%H%M-heater-log.txt")
)

# first we need to redefine Linkam_T96_Device to add some methods we really want to use.
# then we define the instance we are going to use here. 

# new device definition

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
    def readable_time(duration, rounding=2):
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

        days = int((duration - known) / DAY)
        known += days * DAY

        hours = int((duration - known) / HOUR)
        known += hours * HOUR

        minutes = int((duration - known) / MINUTE)
        known += minutes * MINUTE

        seconds = round(duration - known, rounding)
        db = dict(w=weeks, d=days, h=hours, m=minutes, s=seconds)

        s = [
            f"{v}{k}"
            for k, v in db.items()
            if v != 0
        ]
        return " ".join(s)


    def log_it(text):
        """Cheap, lazy way to add to log file.  Gotta be better way..."""
        if not log_file_name.exists():
            # create the file and header
            with open(log_file_name, "w") as f:
                f.write(f"# file: {log_file_name}\n")
                f.write(f"# created: {datetime.datetime.now()}\n")
                f.write(f"# from: {__file__}\n")
        with open(log_file_name, "a") as f:
            # write the payload
            dt = datetime.datetime.now()
            # ISO-8601 format time, ms precision
            iso8601 = dt.isoformat(sep=" ", timespec='milliseconds')
            f.write(f"{iso8601}: {text}\n")


    def linkam_report():
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


 
    def set_target(value, wait=True):
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
            self.temperature.setpoint, value,
            self.temperature.actuate, "On"
        )
        self.log_it(
            f"Set {self.name} setpoint to"
            f" {self.temperature.setpoint.get():.2f} C"
        )
        if not wait:
            return

        checkpoint = time.time() + 60
        while not self.temperature.inposition:
            if time.time() >= checkpoint:
                checkpoint = time.time() + 60
                self.linkam_report()
            yield from bps.sleep(.1)
        self.log_it(f"Done, that took {time.time()-t0:.2f}s")
        self.linkam_report()


    def linkam_hold(duration):
        """BS plan: hold at temperature for the duration (s)."""
        self.log_it(f"{self.name} holding for {self.readable_time(duration)}")
        t0 = time.time()
        time_expires = t0 + duration
        while time.time() < time_expires:
            yield from bps.sleep(.5)
        self.log_it(f"{linkam.name} holding period ended")
        self.linkam_report()


### now we can define our instance... 

linkam_tc1 = My_Linkam_T96_Device("usxLINKAM:tc1:", name="linkam_tc1")

try:
    linkam_tc1.wait_for_connection()
except Exception as exc:
    warnings.warn(f"Linkam controller {linkam_tc1.name} not connected.")


if linkam_tc1.connected:
    # set tolerance for "in position" (Python term, not an EPICS PV)
    # note: done = |readback - setpoint| <= tolerance
    linkam_tc1.temperature.tolerance.put(1.0)

    # sync the "inposition" computation
    linkam_tc1.temperature.cb_readback()

    # easy access to the engineering units
    linkam_tc1.units.put(linkam_tc1.temperature.readback.metadata["units"])
    linkam_tc1.ramp = linkam_tc1.ramprate


#### this is old code likely unneeded
#for _o in (linkam_ci94, linkam_tc1):
# for _o in (linkam_tc1,):
#     try:
#         _o.wait_for_connection()
#     except Exception as exc:
#         warnings.warn(f"Linkam controller {_o.name} not connected.")
#         break

#     # set tolerance for "in position" (Python term, not an EPICS PV)
#     # note: done = |readback - setpoint| <= tolerance
#     _o.temperature.tolerance.put(1.0)

#     # sync the "inposition" computation
#     _o.temperature.cb_readback()

#     # easy access to the engineering units
#     _o.units.put(
#         _o.temperature.readback.metadata["units"]
#     )

# make a common term for the ramp rate (devices use different names)
#if linkam_ci94.connected:
#    linkam_ci94.ramp = linkam_ci94.rate
#if linkam_tc1.connected:
#    linkam_tc1.ramp = linkam_tc1.ramprate
