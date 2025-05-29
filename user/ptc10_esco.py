"""
this is a PTC10 plan with esco pump support
reload by
# %run -im user.ptc10_esco
"""

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

import time

from bluesky import plan_stubs as bps
from apsbits.core.instrument_init import oregistry

from usaxs.plans.plans_user_facing import saxsExp
from usaxs.plans.plans_user_facing import waxsExp
from usaxs.plans.plans_usaxs import USAXSscan
from usaxs.plans.command_list import after_command_list
from usaxs.plans.command_list import before_command_list
from usaxs.plans.plans_tune import preUSAXStune
from ophyd import Component
from ophyd import Device
from ophyd import EpicsSignal
from ophyd import EpicsSignalRO
from ophyd import Signal

ptc10  = oregistry["ptc10"]

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

# utility functions to use in heater


def setheaterOff():
    """
    switches heater off
    """
    yield from bps.mv(
        ptc10.enable,
        "Off",  # power down
        ptc10.pid.pidmode,
        "Off",  # Stop pid loop also
    )


def setheaterOn():
    """
    switches heater on
    """
    yield from bps.mv(
        ptc10.enable,
        "On",  # power up
        ptc10.pid.pidmode,
        "On",  # Start pid loop also
    )


# define device. Only Pressure target, Pressure readback, and on/off needed.
class EscoPumpDev(Device):
    Pressure = Component(EpicsSignal, "PressureSP")
    PressureRBV = Component(EpicsSignalRO, "Pressure_RBV")
    # Refill = Component(EpicsSignal, "Refill")
    StartStop = Component(EpicsSignal, "Run", kind="omitted")


# create the Python object:
escoPump = EscoPumpDev("9idcSP:A:", name="escoPump")

# user can change this list of pressures
# Override this list using 'p_list=[]' keyword argument below.
# PressureList = [1000,1500,2000]
# TemperatureList = [200,300,400]
PressureTempList = [
    [875, 35],
    [875, 60],
    [875, 80],
    [875, 100],
    [875, 120],
    [875, 150],
    [875, 180],
    [900, 180],
    [900, 180],
    [900, 180],
    [1000, 180],
    [1100, 180],
    [1100, 180],
    [1100, 180],
    [950, 180],
    [900, 180],
    [900, 35],
]


# this is the function we will run:
def myPTC10EscoPlan(pos_X, pos_Y, thickness, scan_title, delay_minutes=10, md={}):
    """
    Collect USAXS/SAXS/WAXS data in steps in pressure

    0. Atmospheric pressure start, collect data
    1. Increase pressure in steps, wait for defined time (delay_minutes) while collecting data
    2. Cycle through list of pressures/temperatures, collect data
    3. Finish.

    """
    # parameters definitions
    # pressure_list = PressureList
    # temperature_list = TemperatureList
    # print(f"{pressure_list=}")
    # print(f"{delayAtPressureinMin=}")

    def getSampleName():
        return (
            f"{scan_title}"
            f"_{ptc10.position:.0f}C_"
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

    def _ramp_and_hold_measurement(pr, tc):
        """
        This internal function will:
        1. Set pressure on ESCO pump to new pressure pr
        2. Set PTC10 temp to tc
        3. run preUSAXStune
        4. Measure USAXS-SAXS-WAXS for all the delay time.
        """
        yield from bps.mv(escoPump.Pressure, pr)  # move to pressure pr
        #   Set the PTC10 target, it needs to be passed in as parameter or read from some list. Here we call it temp1
        yield from bps.mv(
            ptc10.temperature.setpoint, tc
        )  # Change the temperature and not wait
        #   Switch on heater, just in case.
        yield from setheaterOn()
        #   Just loging to command line.
        logger.info(f"Ramping temperature to {tc} C")
        logger.info(
            "Ramping pressure to %s PSI, collecting data", pr
        )  # for the log file
        while (
            not ptc10.temperature.inposition
        ):  # runs data collection until next temp or sleeps. Change as needed.
            yield from bps.sleep(5)
            logger.info(f"Still Ramping temperature to {tc} C")
        # yield from bps.sleep(5)
        #    logger.info(f"Still changing pressure to {tc} C")
        # yield from bps.sleep(10)                                           #delay of 10 seconds
        checkpoint = (
            time.time() + delay_minutes * MINUTE
        )  # time to end  after``delayAtPressureinMin`` hold period
        yield from preUSAXStune()
        while time.time() < checkpoint:  # just wait...
            yield from collectAllThree(isDebugMode)  # USAXS, SAXS, WAXS

    #      Here we actually run stuff...
    #   Check if in debugger mode. See above, but if in debugger mode, it will not run instrument, just ESCO and PTC10
    isDebugMode = esco_debug.get()

    if isDebugMode is not True:
        yield from before_command_list()  # this will run usual startup scripts for scans - in NOT in debug mode.

    #      Collect data at at conditions we are in now (whatever ESCO pressure and PCT10 temperature are)
    #   start time
    t0 = time.time()  # mark start time of data collection.
    #   Measure USAXS-SAXS-WAXS
    yield from collectAllThree(isDebugMode)
    #   Start ESCO pump
    yield from bps.mv(escoPump.StartStop, 1)  # start the pump if it is not running
    #      PTC10 controls
    #   Set PTC10 rate, this is 30 deg/min in C/seconds
    # yield from bps.mv(ptc10.ramp, 30/60.0)                        # set rate, user wants C/min, controller wants C/s
    #   Set the PTC10 target, it needs to be passed in as parameter or read from some list. Here we call it temp1
    # yield from bps.mv(ptc10.temperature.setpoint, temp1)          #Change the temperature and not wait
    #   Switch on heater, just in case.
    # yield from setheaterOn()
    #   Just loging to command line.
    # logger.info(f"Ramping temperature to {temp1} C")

    #   this collects data while PT10 is raming up
    # while not ptc10.temperature.inposition:                        #runs data collection until next temp or sleeps. Change as needed.
    # yield from bps.sleep(5)                                    #not sure why we had 5 seconds sleep here, but is examplel how to do it.
    # logger.info(f"Still Ramping temperature to {temp1} C")     #this is not im portant line, just logging in command line.
    # yield from collectAllThree()                               #this would collect data.

    # print("Starting pressure_list series...")
    #   This collects data over list of pressures. List is passed as parameter or default one is defined in the file.
    for pr in PressureTempList:
        p, t = pr
        yield from _ramp_and_hold_measurement(p, t)

    logger.info("finished")  # record end.

    #   If not in debug mode, this will run after scan decorations
    if isDebugMode is not True:
        yield from after_command_list()  # runs standard after scan scripts.


# def myPTC10Loop(pos_X, pos_Y, thickness, scan_title, totalTimeSec, md={}):
#     """
#     Collect USAXS/SAXS/WAXS for time delaySec
#     Append to name time and temperature.
#     PTC10 control is left to manual by user.
#     To run example:
#     RE(myPTC10Loop(0,0,1.28,"testExp",60*60*2))
#     this will run sample in sx= 0, sy=0, thickness=1.28mm for 2 hours.
#     Sample names will look similar to :  testExp_120C_25min

#     reload by
#     # %run -im user.ptc10_plan
#     """

#     def getSampleName():
#         """
#         return the name of the sample
#         """
#         return f"{scan_title}_{ptc10.position:.0f}C_{(time.time()-t0)/60:.0f}min"

#     def collectAllThree(debug=False):
#         """
#         documentation here
#         """
#         sampleMod = getSampleName()
#         if debug:
#             #for testing purposes, set debug=True
#             print(sampleMod)
#             yield from bps.sleep(20)
#         else:
#             md["title"]=sampleMod
#             yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
#             sampleMod = getSampleName()
#             md["title"]=sampleMod
#             yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
#             sampleMod = getSampleName()
#             md["title"]=sampleMod
#             yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

#     yield from before_command_list()                #this will run usual startup scripts for scans

#     t0 = time.time()

#     logger.info("Collecting data for %s sec",delaySec)

#     while time.time()-t0 < delaySec:                          # collects data for delay1 seconds
#         yield from collectAllThree()

#     logger.info(f"finished")

#     yield from after_command_list()                  # runs standard after scan scripts.


# def myPTC10Plan(pos_X, pos_Y, thickness, scan_title, temp1, rate1, delay1, temp2, rate2, md={}):
#     """
#     collect RT USAXS/SAXS/WAXS - or not, change code
#     change temperature T to temp1 with rate1
#     collect USAXS/SAXS/WAXS while heating or sleep= change code...
#     when temp1 reached, hold for delay1 seconds, collecting data repeatedly
#     change T to temp2 with rate2
#     collect USAXS/SAXS/WAXS while changing temp
#     when temp2 reached collect final data
#     and it will end here...

#     reload by
#     # %run -i ptc10_local
#     """
#     def getSampleName():
#         """
#         return the name of the sample
#         """
#         return f"{scan_title}_{ptc10.position:.0f}C_{(time.time()-t0)/60:.0f}min"

#     def collectAllThree(debug=False):
#         """
#         documentation here
#         """
#         sampleMod = getSampleName()
#         if debug:
#             #for testing purposes, set debug=True
#             print(sampleMod)
#             yield from bps.sleep(20)
#         else:
#             md["title"]=sampleMod
#             yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
#             sampleMod = getSampleName()
#             md["title"]=sampleMod
#             yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
#             sampleMod = getSampleName()
#             md["title"]=sampleMod
#             yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

#     yield from before_command_list()                #this will run usual startup scripts for scans
#     t0 = time.time()
#     yield from collectAllThree()                    #collect RT data

#     yield from bps.mv(ptc10.ramp, 30/60.0)           # user wants C/min, controller wants C/s
#     yield from bps.mv(ptc10.temperature.setpoint, temp1)                #Change the temperature and not wait
#     yield from setheaterOn()

#     logger.info(f"Ramping temperature to {temp1} C")

#     while not ptc10.temperature.inposition:                      #runs data collection until next temp or sleeps. Change as needed.
#         yield from bps.sleep(5)
#         logger.info(f"Still Ramping temperature to {temp1} C")
#         #yield from collectAllThree()

#     #logger.info("Reached temperature, now collecting data for %s minutes", delay1min)
#     logger.info("Reached temperature, now collecting data for %s seconds", delay1)
#     t1 = time.time()

#     while time.time()-t1 < delay1:                          # collects data for delay1 seconds
#         #yield from bps.sleep(5)
#         logger.info(f"Collecting data for %s ",delay1)
#         yield from collectAllThree()

#     logger.info("waited for %s seconds, now changing temperature to %s C", delay1, temp2)

#     yield from bps.mv(ptc10.ramp, rate2/60.0)                  #sets the rate of next ramp
#     yield from bps.mv(ptc10.temperature, temp2)                #Change the temperature and wait to get there

#     logger.info(f"reached {temp2} C")
#     yield from setheaterOff()

#     yield from after_command_list()                  # runs standard after scan scripts.

#     logger.info(f"finished")
#  yield from collectAllThree(isDebugMode)
