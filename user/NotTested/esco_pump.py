"""
BS plan to control esco syringe pump during data collection.
User wants to collect data, increate pressure by step, wait for short time,
collect data and keep doing this until some max pressure.
for device description see:
https://github.com/BCDA-APS/bluesky_training/issues/42#issuecomment-1306423475

///IMPORTANT: Assumes existence of ./heater_profile.py for MINUTE
load this way:

    %run -im user.esco_pump

* file:  ~/bluesky/user/esco_pump.py

* JIL, 2022-11-08 : first release
"""

# imports are here:
import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

import time

from bluesky import plan_stubs as bps
from ophyd import Component
from ophyd import Device
from ophyd import EpicsSignal
from ophyd import EpicsSignalRO
from ophyd import Signal

from usaxs.plans.plans_user_facing import saxsExp
from usaxs.plans.plans_user_facing import waxsExp
from usaxs.plans.plans_usaxs import USAXSscan
from usaxs.plans.command_list import after_command_list
from usaxs.plans.command_list import before_command_list
from usaxs.plans.plans_tune import preUSAXStune


# define conversions from seconds
SECOND = 1
MINUTE = 60 * SECOND
HOUR = 60 * MINUTE
DAY = 24 * HOUR
WEEK = 7 * DAY
# debug mode switch, may not be that useful in our case...
esco_debug = Signal(name="esco_debug", value=False)
#   In order to run as debug (without collecting data, only control pump) in command line run:
# esco_debug.put(True)


# define device. Only Pressure target, Pressure readback, and on/off needed.
class EscoPumpDev(Device):
    Pressure = Component(EpicsSignal, "PressureSP")
    PressureRBV = Component(EpicsSignalRO, "Pressure_RBV")
    # Refill = Component(EpicsSignal, "Refill")
    StartStop = Component(EpicsSignal, "Run", kind="omitted")


# should this be here or on line 95?
# create the Python object:
escoPump = EscoPumpDev("9idcSP:A:", name="escoPump")

# user can change this list of pressures
# Override this list using 'p_list=[]' keyword argument below.
PressureList = [
    1000,
    1500,
    2000,
    2500,
    3000,
    3500,
    3750,
    3500,
    3000,
    2500,
    2000,
    1500,
    1000,
]

# this is the function we will run:


def myEscoPlan(
    pos_X, pos_Y, thickness, scan_title, delay_minutes=10, p_list=None, md={}
):
    """
    Collect USAXS/SAXS/WAXS data in steps in pressure

    0. Atmospheric pressure start, collect data
    1. Increase pressure in steps, wait for defined time while collecting data
    2. Cycle through list of pressures
    3. Finish.

    reload by::

        %run -im user.esco_pump
    """
    # parameters definitions
    pressure_list = p_list or PressureList
    delayAtPressureinMin = delay_minutes
    # print(f"{pressure_list=}")
    # print(f"{delayAtPressureinMin=}")

    def getSampleName():
        return (
            f"{scan_title}"
            f"_{escoPump.PressureRBV.get():.0f}PSI"
            f"_{(time.time()-t0)/60:.0f}min"
        )

    def collectAllThree(debug=False):
        sampleMod = getSampleName()
        if debug:
            # for testing purposes, set debug=True
            print(sampleMod)
            yield from bps.sleep(10)
        else:
            md["title"] = sampleMod
            yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = getSampleName()
            md["title"] = sampleMod
            yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = getSampleName()
            md["title"] = sampleMod
            yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    # logger.info(f"Linkam controller PV prefix={linkam.prefix}")
    isDebugMode = esco_debug.get()

    if isDebugMode is not True:
        yield from before_command_list()  # this will run usual startup scripts for scans

    # Collect data at at conditions we are in now (atmospheric pressure?).
    t0 = time.time()  # mark start time of data collection.
    yield from collectAllThree(isDebugMode)

    # yield from bps.mv(escoPump.StartStop, 1)               # start the pump if it is running

    def _ramp_and_hold_measurement(pr):
        # print(f"{pr=}")
        yield from bps.mv(escoPump.Pressure, pr)  # next pressure
        # print("after put(pr)")
        logger.info(
            "Ramping pressure to %s PSI, collecting data", pr
        )  # for the log file
        checkpoint = (
            time.time() + delayAtPressureinMin * MINUTE
        )  # time to end  after``delayAtPressureinMin`` hold period
        # print(f"{checkpoint=}")
        yield from preUSAXStune()
        # print(f"{(checkpoint-time.time())=}")
        while time.time() < checkpoint:  # just wait...
            yield from collectAllThree(isDebugMode)  # USAXS, SAXS, WAXS

    # print("Starting pressure_list series...")
    for pr in pressure_list:
        # logger.info("Pressure selected %s", pr)
        yield from _ramp_and_hold_measurement(pr)

    logger.info("finished")  # record end.

    if isDebugMode is not True:
        yield from after_command_list()  # runs standard after scan scripts.
