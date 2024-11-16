"""
Run a temperature profile on the sample heater as a Bluesky plan.

This file defines a function (bluesky "plan") named
    ``planHeaterProcess()``
that runs the desired temperature profile schedule.
All configuration is communicated via EPICS PVs
which are interfaced here as ophyd EpicsSignal objects.
Other plans and functions are used to simplify the
interface in planHeaterProcess().

Called (via ``import``) from ``heater_profile_process.py``
(which is started/stopped/restarted from ``heater_profile_manager.sh``),
both of which are in directory ``~/.ipython/profile/bluesky/usaxs_support/``.

See https://github.com/APS-USAXS/ipython-usaxs/issues/482 for details.
"""

from apstools.devices import Linkam_CI94_Device
from apstools.devices import Linkam_T96_Device
from bluesky import plan_stubs as bps
from ophyd import EpicsSignal
from ophyd import EpicsSignalRO

import datetime
import pathlib
import random  # for testing
import time


SECOND = 1
MINUTE = 60 * SECOND
HOUR = 60 * MINUTE
DAY = 24 * HOUR
WEEK = 7 * DAY

# Create devices here so we remain independent of the instrument package.
linkam_exit = EpicsSignal("9idcLAX:bit14", name="exit_request_signal")
linkam_ci94 = Linkam_CI94_Device("9idcLAX:ci94:", name="linkam_ci94")
linkam_tc1 = Linkam_T96_Device("9idcLINKAM:tc1:", name="linkam_tc1")

# write output to log file in userDir, name=MMDD-HHmm-heater-log.txt
user_dir = EpicsSignalRO("9idcLAX:userDir", name="user_dir", string=True)

for o in (linkam_exit, linkam_ci94, linkam_tc1, user_dir):
    o.wait_for_connection()

log_file_name = pathlib.Path(user_dir.get()) / (
    datetime.datetime.now().strftime("%m%d-%H%M-heater-log.txt")
)

# make a common term for the ramp rate (devices use different names)
linkam_ci94.ramp = linkam_ci94.rate
linkam_tc1.ramp = linkam_tc1.ramprate

linkam = linkam_tc1     # choose which one#
#linkam = linkam_ci94     # choose which one

# set tolerance for "in position" (Python term, not an EPICS PV)
# note: done = |readback - setpoint| <= tolerance
linkam.temperature.tolerance.put(1.0)
# sync the "inposition" computation
linkam.temperature.cb_readback()

# easy access to the engineering units
linkam.units.put(
    linkam.temperature.readback.metadata["units"]
)


class HeaterStopAndHoldRequested(Exception):
    "Exception to stop the heater plan is stopping."


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
    units = linkam.units.get()[:1].upper()
    log_it(
        f"{linkam.name}"
        f" T={linkam.temperature.position:.1f}{units}"
        f" setpoint={linkam.temperature.setpoint.get():.1f}{units}"
        f" ramp:{linkam.ramp.get()}"
        f" settled: {linkam.temperature.inposition}"
        f" done: {linkam.temperature.done.get()}"
    )


def change_ramp_rate(value):
    """BS plan: change controller's ramp rate."""
    yield from check_for_exit_request(time.time())
    yield from bps.mv(linkam.ramp, value)
    log_it(
        f"Set {linkam.name} rate to {linkam.ramp.get():.0f} C/min"
    )


def check_for_exit_request(t0):
    """
    BS plan: Hold linkam at current temperature & exit planHeaterProcess().

    Raise ``StopHeaterPlan`` exception if exit was requested.  The 
    planHeaterProcess() will catch this and return.  Otherwise return ```None``

    Can't call linkam.temperature.stop() since that has blocking code.
    Implement that method here by holding current position.
    """
    # Watch for user exit request while waiting
    if linkam_exit.get() in (0, linkam_exit.enum_strs[0]):
        # no exit requested
        return

    # FIXME: Stopping? or holding at temperature?
    yield from bps.mv(linkam.temperature, linkam.temperature.position)
    minutes = (time.time() - t0) / 60
    log_it(
        "User requested exit during set"
        f" after {minutes:.2f}m."
        " Stopping the heater and holding at current temperature."
    )
    linkam_report()
    raise HeaterStopAndHoldRequested(f"Stop requested after {minutes:.2f}m")


def linkam_change_setpoint(value, wait=True):
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
    yield from check_for_exit_request(t0)
    yield from bps.mv(
        linkam.temperature.setpoint, value
    )
    if isinstance(linkam, Linkam_T96_Device):
        yield from bps.mv(
            linkam.temperature.actuate, "On"
        )
    log_it(
        f"Set {linkam.name} setpoint to"
        f" {linkam.temperature.setpoint.get():.2f} C"
    )
    if not wait:
        return

    checkpoint = time.time() + 60
    while not linkam.temperature.inposition:
        if time.time() >= checkpoint:
            checkpoint = time.time() + 60
            linkam_report()
        yield from check_for_exit_request(t0)
        yield from bps.sleep(.1)
    log_it(f"Done, that took {time.time()-t0:.2f}s")
    linkam_report()


def linkam_hold(duration):
    """BS plan: hold at temperature for the duration (s)."""
    log_it(f"{linkam.name} holding for {readable_time(duration)}")
    t0 = time.time()
    time_expires = t0 + duration
    while time.time() < time_expires:
        yield from check_for_exit_request(t0)
        yield from bps.sleep(.1)
    log_it(f"{linkam.name} holding period ended")
    linkam_report()


def planHeaterProcess():
    """BS plan: Run one temperature profile on the sample heater."""
    log_it(f"Starting planHeaterProcess() for {linkam.name}")
    linkam_report()

    try:
        # heating process starts
        yield from change_ramp_rate(20)  # TODO: value used in testing
        yield from linkam_change_setpoint(80)  # TODO: value used in testing
        # two hours = 2 * HOUR, two minutes = 2 * MINUTE
        random_testing_hold_time = (1*MINUTE + 12*SECOND)*random.random()  # TODO: value used in testing
        yield from linkam_hold(random_testing_hold_time)
        yield from change_ramp_rate(20)  # TODO: value used in testing
        yield from linkam_change_setpoint(40)  # TODO: value used in testing
        # heating process ends
    except HeaterStopAndHoldRequested:
        return

    # DEMO: signal for an orderly exit after first run
    log_it(f"Ending planHeaterProcess() for {linkam.name}")
    yield from bps.mv(linkam_exit, True)
