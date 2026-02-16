"""
this is a PTC10 plan
reload by
...:  %run -im usaxs.user.ptc10_plan

* 2025-6-7 : JIL user mofdifications
"""

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

import time

from bluesky import plan_stubs as bps
from apsbits.core.instrument_init import oregistry
from ophyd import Signal


from usaxs.plans.plans_user_facing import saxsExp
from usaxs.plans.plans_user_facing import waxsExp
from usaxs.plans.plans_usaxs import USAXSscan
from usaxs.plans.command_list import after_command_list, sync_order_numbers
from usaxs.plans.command_list import before_command_list
from usaxs.utils.obsidian import appendToMdFile

ptc10 = oregistry["ptc10"]

ptc10_debug = Signal(name="ptc10_debug", value=False)
#   In order to run as debug (without collecting data, only control Linkam) in command line run:
# ptc10_debug.put(True)


# this is for myPTC10List and myPTC10HoldListlist of temperatures to go to.
# TemperatureList = [50,100,150,200,250,300,350,400,450,500,550,600,650,700,750,800,850,900,950,1000,1050,1100,500,35]
# SampleList = [[pos_X, pos_Y, thickness, scan_title]]
TemperatureList = [80]  # deg C
TimeList = [720]  # minutes
# [sx,sy,th,"sampleName"]
# assert len(TemperatureList) == len(TimeList)
# assert len(TemperatureList) == len(SampleList)


# edit this list with list fo samples. Each sample has new line as below
# [sx,sy,th,"sampleName"],

#For Andrew:
# RE(myPTC10PlanThreeStep(0,0,1.3,"sampleName", temp1C, rate1degC/min,delay1Sec, temp2,rate2,delay2,temp3, rate3,delay3))

# and

#edit the SampleList below, reload the file 
#  %run -im usaxs.user.ptc10_plan
#  and 
# RE(myPTC10HoldList(temp1C, delay1min))

SampleList = [
    [0, 0, 1.3, "LewatsmgN2bPos1"],
    [1, 0, 1.3, "LewatsmgN2bPos2"],
    [2, 0, 1.3, "LewatsmgN2bPos3"],
]

# utility functions to use in heater, ignore me...


def setheaterOff():
    """
    switches heater off
    """
    yield from bps.mv(
        ptc10.enable,
        "Off",  # power downptc10
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


# plans


def myPTC10HoldList(temp1, delay1min, md={}):
    """
    collect USAXS/SAXS/WAXS at RT
    set temperature of PTC10 to temp1 and heating rate to rate1Cmin
    start heating and wait until PTC10 heats to temp1
    Start loop, collecti USAXS/SAXS/WAXS for delay1 minutes
    in positions from SampleList, collecting USAXS/SAXS/WAXS for each item on SampleList
    """

    # needed customized functions to handle data collection.
    def getSampleName(inputTitle):
        """
        return the name of the sample
        """
        return f"{inputTitle}_{ptc10.position:.0f}C_{(time.time()-t0)/60:.0f}min"

    def collectAllThree(pos_X, pos_Y, thickness, scan_title, isDebugMode):
        """
        Collects USAXS/SAXS/WAXS data for given input conditions.
        """
        if isDebugMode is not True:
            yield from sync_order_numbers()
            sampleMod = getSampleName(scan_title)
            md["title"] = sampleMod
            yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = getSampleName(scan_title)
            md["title"] = sampleMod
            yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = getSampleName(scan_title)
            md["title"] = sampleMod
            yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
        else:
            # for testing purposes, set debug=True
            sampleMod = getSampleName(scan_title)
            logger.info(pos_X, pos_Y, thickness, scan_title)
            yield from bps.sleep(20)

    # this is the code which actually gets executed, starts here...
    # ****************************
    # check for debug mode
    isDebugMode = ptc10_debug.get()

    # data collection
    if isDebugMode is not True:
        yield from before_command_list()  # this will run usual startup scripts for scans
    else:
        logger.info("debug mode, would be running usual startup scripts for scans")
        yield from bps.sleep(5)

    # collect data at RT
    appendToMdFile("  ***  ")
    appendToMdFile(f"Collecting data for Sample {scan_title}")
    logger.info("using myPTC10HoldList")
    appendToMdFile("using myPTC10HoldList")
    logger.info(f"Collecting data at RT")
    t0 = time.time()
    for tmpVal in SampleList:
        pos_X, pos_Y, thickness, scan_title = tmpVal
        yield from collectAllThree(pos_X, pos_Y, thickness, scan_title, isDebugMode)  # collect RT data

    # ramp to temperature
    logger.info(f"Ramping temperature to {temp1} C")
    appendToMdFile(f"Ramping temperature to {temp1} C")
    yield from bps.mv(
        # ptc10.ramp, rate1Cmin / 60.0,       # user wants C/min, controller wants C/s
        ptc10.temperature.setpoint,temp1,     # Change the temperature and not wait
    )
    yield from setheaterOn()

    # wait until PTC10 heats to temp1
    while (not ptc10.temperature.inposition):  # sleep for now, check every 10 seconds. Change as needed.
        yield from bps.sleep(5)  # sleep for 10 seconds combined with loger info mid way
        logger.info(f"Still Ramping temperature to {temp1} C")
        yield from bps.sleep(5)
        # OR :
        # for tmpVal in SampleList:
        #     pos_X, pos_Y, thickness, scan_title = tmpVal
        #     yield from collectAllThree(pos_X, pos_Y, thickness, scan_title, isDebugMode)  # collect data during heating

    logger.info(f"Reached temperature {temp1} C, now collecting data for {delay1min} min")
    appendToMdFile(f"Reached temperature {temp1} C, now collecting data for {delay1min} min")

    # reset time in experiment here. This is the time we start collecting data.
    t0 = time.time()

    # Main data collection loop - for delay1min collect on each sample from the SampleList USAXS, SAXS, and WAXS
    while time.time() - t0 < delay1min * 60:  # collects data for delay1 seconds
        for tmpVal in SampleList:
            pos_X, pos_Y, thickness, scan_title = tmpVal
            yield from collectAllThree(pos_X, pos_Y, thickness, scan_title, isDebugMode)

    # done, switch off heater and be done
    yield from setheaterOff()

    if isDebugMode is not True:
        yield from after_command_list()  # runs standard after scan scripts.
    else:
        logger.info("debug mode, would be running standard after scan scripts.")

    appendToMdFile(f"Finished collecting data for Sample {scan_title}")
    appendToMdFile("  ***  ")
    logger.info("finished")



def myPTC10Loop(pos_X, pos_Y, thickness, scan_title, delayMin, md={}):
    """
    Collect USAXS/SAXS/WAXS for time delaySec
    Append to name time and temperature.
    PTC10 control is left to manual by user.
    To run example:
    RE(myPTC10Loop(0,0,1.28,"testExp",60*60*2))
    this will run sample in sx= 0, sy=0, thickness=1.28mm for 2 hours.
    Sample names will look similar to :  testExp_120C_25min

    reload by
    # %run -im user.ptc10_plan
    """

    def getSampleName():
        """
        return the name of the sample
        """
        return f"{scan_title}_{ptc10.position:.0f}C_{(time.time()-t0)/60:.0f}min"

    def collectAllThree(debug=False):
        yield from sync_order_numbers()
        md["title"] = sampleMod
        yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
        sampleMod = getSampleName()
        md["title"] = sampleMod
        yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
        sampleMod = getSampleName()
        md["title"] = sampleMod
        yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    yield from before_command_list()  # this will run usual startup scripts for scans

    t0 = time.time()

    appendToMdFile("  ***  ")
    appendToMdFile(f"Collecting data for Sample {scan_title}")
    logger.info("using myPTC10Loop")
    appendToMdFile("using myPTC10Loop")

    logger.info("Collecting data for %s min", delayMin)
    appendToMdFile(f"Collecting data for {delayMin} min")

    while time.time() - t0 < delayMin * 60:  # collects data for delay1 seconds
        yield from collectAllThree()

    logger.info("finished")

    yield from after_command_list()  # runs standard after scan scripts.

def myPTC10Step(pos_X, pos_Y, thickness, scan_title, startTC, endTC,stepTC, rateTmin, delayTimeMin, md={}):
    """
    Collects USAXS/SAXS/WAXS in steps from starT to endT steppnig by stepT
    at each condition it waits for detayTime and then collects USAXS/SAXS/WAXS
    at the end, switch off the heating and end. 

    Append to name time and temperature.

    To run example:
    RE(myPTC10Step(0,0,1.28,"testExp",30, 500, 10, 50, 2))
    this will run sample in sx= 0, sy=0, thickness=1.28mm in steps from 30 to 5500C, step is 10C.
    heating rate is 50C/min
    delay before measurement at temperature is 2 minutes. 
    Sample names will look similar to :  testExp_120C_25min

    reload by
    # %run -im user.ptc10_plan
    """

    def getSampleName():
        """
        return the name of the sample
        """
        return f"{scan_title}_{ptc10.position:.0f}C_{(time.time()-t0)/60:.0f}min"

    def collectAllThree(debug=False):
        yield from sync_order_numbers()
        md["title"] = sampleMod
        yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
        sampleMod = getSampleName()
        md["title"] = sampleMod
        yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
        sampleMod = getSampleName()
        md["title"] = sampleMod
        yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    logger.info("Collecting data for sample %s", scan_title)
    appendToMdFile("  ***  ")
    appendToMdFile(f"Collecting data for Sample {scan_title}")
    logger.info("using myPTC10Step")
    appendToMdFile("using myPTC10Step")

    yield from before_command_list()  # this will run usual startup scripts for scans

    t0 = time.time()

    yield from bps.mv(ptc10.ramp, rateTmin / 60.0)  # user wants C/min, controller wants C/s
    yield from setheaterOn()

    # Temperature loop - iterate from startTC to endTC with stepTC increments
    for currentTemp in range(startTC, endTC + stepTC, stepTC):
        logger.info(f"Setting temperature to {currentTemp} C")
        appendToMdFile(f"Setting temperature to {currentTemp} C")

        # Set temperature and wait to reach it
        yield from bps.mv(ptc10.temperature.setpoint, currentTemp)

        # Wait until temperature is reached
        while not ptc10.temperature.inposition:
            yield from bps.sleep(5)
            logger.info(f"Still ramping to {currentTemp} C")
            yield from bps.sleep(5)

        logger.info(f"Reached {currentTemp} C, waiting {delayTimeMin} min before collecting")
        appendToMdFile(f"Reached {currentTemp} C, waiting {delayTimeMin} min before collecting")

        # Wait for delayTimeMin before collecting
        yield from bps.sleep(delayTimeMin * 60)

        # Collect data at this temperature
        sampleMod = getSampleName()
        yield from collectAllThree()

    logger.info("finished")
    appendToMdFile(f"Temperature step measurements completed")

    yield from setheaterOff()
    yield from after_command_list()  # runs standard after scan scripts.



def myPTC10Plan(pos_X, pos_Y, thickness, scan_title, temp1, rate1, delay1, temp2, rate2, md={}):
    """
    collect RT USAXS/SAXS/WAXS - or not, change code
    change temperature T to temp1 with rate1
    collect USAXS/SAXS/WAXS while heating or sleep= change code...
    when temp1 reached, hold for delay1 seconds, collecting data repeatedly
    change T to temp2 with rate2
    collect USAXS/SAXS/WAXS while changing temp
    when temp2 reached collect final data
    and it will end here...

    reload by
    # %run -i ptc10_local
    """

    def getSampleName():
        """
        return the name of the sample
        """
        return f"{scan_title}_{ptc10.position:.0f}C_{(time.time()-t0)/60:.0f}min"

    def collectAllThree(debug=False):
        """
        documentation here
        """
        sampleMod = getSampleName()
        if debug:
            # for testing purposes, set debug=True
            print(sampleMod)
            yield from bps.sleep(20)
        else:
            yield from sync_order_numbers()
            md["title"] = sampleMod
            yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = getSampleName()
            md["title"] = sampleMod
            yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = getSampleName()
            md["title"] = sampleMod
            yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    def collectWAXS(debug=False):
        """
        documentation here
        """
        sampleMod = getSampleName()
        if debug:
            # for testing purposes, set debug=True
            print(sampleMod)
            yield from bps.sleep(20)
        else:
            md["title"] = sampleMod
            yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})


    appendToMdFile("  ***  ")
    appendToMdFile(f"Collecting data for Sample {scan_title}")
    logger.info("using myPTC10Plan")
    appendToMdFile("using myPTC10HPlan")

    yield from before_command_list()  # this will run usual startup scripts for scans
    t0 = time.time()
    yield from collectAllThree()  # collect RT data

    yield from bps.mv(
        ptc10.ramp, rate1 / 60.0
    )  # user wants C/min, controller wants C/s
    yield from bps.mv(
        ptc10.temperature.setpoint, temp1
    )  # Change the temperature and not wait
    yield from setheaterOn()

    logger.info(f"Ramping temperature to {temp1} C")
    appendToMdFile(f"Ramping temperature to {temp1} C")

    t0 = time.time()
    while (not ptc10.temperature.inposition):  # runs data collection until next temp or sleeps. Change as needed.
        #yield from bps.sleep(5)
        logger.info(f"Still Ramping temperature to {temp1} C")
        yield from collectAllThree()

    # logger.info("Reached temperature, now collecting data for %s minutes", delay1min)
    logger.info("Reached temperature, now collecting data for %s seconds", delay1)
    appendToMdFile(f"Reached temperature, now collecting data for {delay1} seconds")
    t1 = time.time()
    t0 = time.time()

    while time.time() - t1 < delay1:  # collects data for delay1 seconds
        # yield from bps.sleep(5)
        logger.info("Collecting data for %s ", delay1)
        yield from collectAllThree()

    logger.info("waited for %s seconds, now changing temperature to %s C", delay1, temp2)
    appendToMdFile(f"waited for {delay1} seconds, now changing temperature to {temp2} C")

    yield from bps.mv(ptc10.ramp, rate2 / 60.0)  # sets the rate of next ramp
    yield from bps.mv(ptc10.temperature, temp2)  # Change the temperature and wait to get there

    logger.info(f"reached {temp2} C")
    appendToMdFile(f"reached {temp2} C")
    yield from setheaterOff()

    yield from after_command_list()  # runs standard after scan scripts.

    logger.info("finished")


def myPTC10PlanThreeStep(pos_X, pos_Y, thickness, scan_title, temp1, rate1, delay1, temp2, rate2,delay2,temp3, rate3, delay3, md={}):
    """
    collect RT USAXS/SAXS/WAXS - or not, change code
    change temperature T to temp1 with rate1
    collect USAXS/SAXS/WAXS while heating or sleep= change code...
    when temp1 reached, hold for delay1 seconds, collecting data repeatedly
    change T to temp2 with rate2, hold for delay2 seconds collect USAXS/SAXS/WAXS while changing temp and hold
    change T to temp3 with rate3 collect data while chaging temp, hold for delay3 collecting data data
    and it will end here...

    reload by
     %run -im usaxs.user.ptc10_plan
    run:
    RE(myPTC10PlanThreeStep(0,0,1.3,"sampleName", temp1C, rate1degC/min,delay1Sec, temp2,rate2,delay2,temp3, rate3,delay3))
    """

    def getSampleName():
        """
        return the name of the sample
        """
        return f"{scan_title}_{ptc10.position:.0f}C_{(time.time()-t0)/60:.0f}min"

    def collectAllThree(debug=False):
        """
        documentation here
        """
        sampleMod = getSampleName()
        if debug:
            # for testing purposes, set debug=True
            print(sampleMod)
            yield from bps.sleep(20)
        else:
            yield from sync_order_numbers()
            sampleMod = getSampleName()
            md["title"] = sampleMod
            yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = getSampleName()
            md["title"] = sampleMod
            yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = getSampleName()
            md["title"] = sampleMod
            yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    def collectWAXS(debug=False):
        """
        documentation here
        """
        sampleMod = getSampleName()
        if debug:
            # for testing purposes, set debug=True
            print(sampleMod)
            yield from bps.sleep(20)
        else:
            md["title"] = sampleMod
            yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
    
    appendToMdFile("  ***  ")
    appendToMdFile(f"Collecting data for Sample {scan_title}")
    logger.info("using myPTC10PlanThreeStep")
    appendToMdFile("using myPTC10PlanThreeStep")

    ## rt MEASUREMENTS
    yield from before_command_list()  # this will run usual startup scripts for scans
    t0 = time.time()
    yield from collectAllThree()  # collect RT data
    ## TEMP1 BLOCK
    yield from bps.mv(ptc10.ramp, rate1 / 60.0)  # user wants C/min, controller wants C/s
    yield from bps.mv(ptc10.temperature.setpoint, temp1)  # Change the temperature and not wait
    yield from setheaterOn()
    logger.info(f"Ramping temperature to {temp1} C")
    appendToMdFile(f"Ramping temperature to {temp1} C")
    t0 = time.time()    #SAMPLE NAME USES t0
    while (not ptc10.temperature.inposition):  # runs data collection until next temp or sleeps. Change as needed.
        # yield from bps.sleep(5)
        logger.info(f"Still Ramping temperature to {temp1} C")
        yield from collectAllThree()
    logger.info("Reached temperature, now collecting data for %s seconds", delay1)
    appendToMdFile(f"Reached temperature, now collecting data for {delay1} seconds")
    t1 = time.time()    # for delay time
    #t0 = time.time()    # for sample name
    while time.time() - t1 < delay1:  # collects data for delay1 seconds
        # yield from bps.sleep(5)
        logger.info("Collecting data for %s ", delay1)
        yield from collectAllThree()
    
    # TEMP2 BLOCK
    logger.info("waited for %s seconds, now changing temperature to %s C", delay1, temp2)
    appendToMdFile(f"waited for {delay1} seconds, now changing temperature to {temp2} C")
    yield from bps.mv(ptc10.ramp, rate2 / 60.0)  # sets the rate of next ramp
    yield from bps.mv(ptc10.setpoint, temp2)     # Change the temperature setpoint
    #t0 = time.time()    # used for sample name
    while (not ptc10.temperature.inposition):  # runs data collection until next temp or sleeps. Change as needed.
        #yield from bps.sleep(5)
        logger.info(f"Still Ramping temperature to {temp2} C")
        yield from collectAllThree()
    logger.info("Reached temperature, now collecting data for %s seconds", delay2)
    appendToMdFile(f"Reached temperature, now collecting data for {delay2} seconds")
    t1 = time.time()
    #t0 = time.time()
    while time.time() - t1 < delay2:  # collects data for delay2 seconds
        # yield from bps.sleep(5)
        logger.info("Collecting data for %s ", delay2)
        yield from collectAllThree()

    # TEMP3 BLOCK
    logger.info("waited for %s seconds, now changing temperature to %s C", delay2, temp3)
    appendToMdFile(f"waited for {delay2} seconds, now changing temperature to {temp3} C")
    yield from bps.mv(ptc10.ramp, rate3 / 60.0)  # sets the rate of next ramp
    yield from bps.mv(ptc10.setpoint, temp3)     # Change the temperature setpoint
    #t0 = time.time()
    while (not ptc10.temperature.inposition):  # runs data collection until next temp or sleeps. Change as needed.
        #yield from bps.sleep(5)
        logger.info(f"Still Ramping temperature to {temp3} C")
        yield from collectAllThree()
    logger.info("Reached temperature, now collecting data for %s seconds", delay3)
    appendToMdFile(f"Reached temperature, now collecting data for {delay3} seconds")
    t1 = time.time()
    #t0 = time.time()
    while time.time() - t1 < delay3:  # collects data for delay2 seconds
        # yield from bps.sleep(5)
        logger.info("Collecting data for %s ", delay3)
        yield from collectAllThree()
    logger.info(f"Done with {temp3} C")
    appendToMdFile(f"Finsihed measurements at {temp3} C")
    yield from setheaterOff()

    yield from after_command_list()  # runs standard after scan scripts.

    logger.info("finished")
    appendToMdFile(f"Heater run done")



def myPTC10List(rate1Cmin, md={}):
    """
    collect RT USAXS/SAXS/WAXS
    varies temperature, time, and positions to values in TemperatureList, TimeList,SampleList
    wait until reach temp, select location from SampleList
    collect USAXS/SAXS/WAXS in input parameters pos_X, pos_Y, thickness, scan_title
    during time seconds, collecting data repeatedly
    """

    def getSampleName():
        """
        return the name of the sample
        """
        return f"{scan_title}_{ptc10.position:.0f}C_{(time.time()-t0)/60:.0f}min"

    def collectAllThree(debug=False):
        """
        documentation here
        """
        sampleMod = getSampleName()
        if debug:
            # for testing purposes, set debug=True
            print(sampleMod)
            yield from bps.sleep(20)
        else:
            yield from sync_order_numbers()
            sampleMod = getSampleName()
            md["title"] = sampleMod
            yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = getSampleName()
            md["title"] = sampleMod
            yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = getSampleName()
            md["title"] = sampleMod
            yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    isDebugMode = ptc10_debug.get()

    # TODO: what about HeaterStopAndHoldRequested?

    if isDebugMode is not True:
        yield from before_command_list()  # this will run usual startup scripts for scans
    appendToMdFile("  ***  ")
    appendToMdFile(f"Collecting data for Sample {scan_title}")
    logger.info("using myPTC10List")
    appendToMdFile("using myPTC10List")

    t0 = time.time()
    # yield from collectAllThree(isDebugMode)                    #collect RT data

    yield from bps.mv(
        ptc10.ramp, rate1Cmin / 60.0
    )  # user wants C/min, controller wants C/s

    for temp1, delay1, [pos_X, pos_Y, thickness, scan_title] in zip(
        TemperatureList, TimeList, SampleList, strict=False
    ):
        yield from bps.mv(
            ptc10.temperature.setpoint, temp1
        )  # Change the temperature and not wait
        yield from setheaterOn()

        logger.info(f"Ramping temperature to {temp1} C")
        appendToMdFile(f"Ramping temperature to {temp1} C")

        while (
            not ptc10.temperature.inposition
        ):  # runs data collection until next temp or sleeps. Change as needed.
            yield from bps.sleep(5)
            logger.info(f"Still Ramping temperature to {temp1} C")
            # yield from collectAllThree()
            yield from bps.sleep(5)

        # logger.info("Reached temperature, now collecting data for %s minutes", delay1min)
        logger.info("Reached temperature, now collecting data for %s min", delay1)
        appendToMdFile(f"Reached temperature, now collecting data for {delay1} min")    
        t1 = time.time()
        t0 = time.time()

        while time.time() - t1 < delay1 * 60:  # collects data for delay1 seconds
            # yield from bps.sleep(5)
            logger.info("Collecting data for %s min", delay1)
            yield from collectAllThree(isDebugMode)

    # yield from setheaterOff()

    if isDebugMode is not True:
        yield from after_command_list()  # runs standard after scan scripts.

    logger.info("finished")


def myPTC10List2(rate1Cmin, delay1min, md={}):
    """
    collect RT USAXS/SAXS/WAXS
    varies temperature T to temp1 from TemperatureList
    wait until reach temp1
    collect USAXS/SAXS/WAXS during delay1 seconds
    in positions from SampleList
    collecting data for each item on SampleList
    then runs followingt temperature from TemperatureList
    """

    def getSampleName():
        """
        return the name of the sample
        """
        return f"{scan_title}_{ptc10.position:.0f}C_{(time.time()-t0)/60:.0f}min"

    def collectAllThree(debug=False):
        """
        documentation here
        """
        sampleMod = getSampleName()
        if debug:
            # for testing purposes, set debug=True
            print(sampleMod)
            # print(pos_X)
            yield from bps.sleep(20)
        else:
            yield from sync_order_numbers()
            md["title"] = sampleMod
            # yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = getSampleName()
            md["title"] = sampleMod
            # yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = getSampleName()
            md["title"] = sampleMod
            yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    isDebugMode = ptc10_debug.get()

    # TODO: what about HeaterStopAndHoldRequested?

    appendToMdFile("  ***  ")
    appendToMdFile(f"Collecting data for Sample {scan_title}")
    logger.info("using myPTC10List2")
    appendToMdFile("using myPTC10List2")

    if isDebugMode is not True:
        yield from before_command_list()  # this will run usual startup scripts for scans

    t0 = time.time()
    for tmpVal in SampleList:
        pos_X, pos_Y, thickness, scan_title = tmpVal
        yield from collectAllThree(isDebugMode)  # collect RT data

    yield from bps.mv(
        ptc10.ramp, rate1Cmin / 60.0
    )  # user wants C/min, controller wants C/s

    for temp1 in TemperatureList:
        yield from bps.mv(
            ptc10.temperature.setpoint, temp1
        )  # Change the temperature and not wait
        yield from setheaterOn()

        logger.info(f"Ramping temperature to {temp1} C")
        appendToMdFile(f"Ramping temperature to {temp1} C")

        while (
            not ptc10.temperature.inposition
        ):  # runs data collection until next temp or sleeps. Change as needed.
            yield from bps.sleep(5)
            logger.info(f"Still Ramping temperature to {temp1} C")
            # yield from collectAllThree()
            yield from bps.sleep(5)

        # logger.info("Reached temperature, now collecting data for %s minutes", delay1min)
        logger.info("Reached temperature, now collecting data for %s min", delay1min)
        appendToMdFile(f"Reached temperature, now collecting data for {delay1min} min")
        t1 = time.time()

        while time.time() - t1 < delay1min * 60:  # collects data for delay1 seconds
            # yield from bps.sleep(5)
            logger.info("Collecting data for %s min", delay1min)
            for tmpVal in SampleList:
                pos_X, pos_Y, thickness, scan_title = tmpVal
                yield from collectAllThree(isDebugMode)

    # yield from setheaterOff()

    if isDebugMode is not True:
        yield from after_command_list()  # runs standard after scan scripts.

    logger.info("finished")


def FanPTC10Plan(pos_X, pos_Y, thickness, scan_title, temp1, rate1, delay1, temp2, rate2, md={}):
    """
    collect RT USAXS/SAXS/WAXS - or not, change code
    change temperature T to temp1 with rate1
    collect WAXS while heating or sleep= change code...
    when temp1 reached, hold for delay1 seconds, collecting data repeatedly
    change T to temp2 with rate2
    collect USAXS/SAXS/WAXS while changing temp
    when temp2 reached collect final data
    and it will end here...

    reload by
    # %run -i ptc10_local
    """

    def getSampleName():
        """
        return the name of the sample
        """
        return f"{scan_title}_{ptc10.position:.0f}C_{(time.time()-t0)/60:.0f}min"

    def collectAllThree(debug=False):
        """
        documentation here
        """
        sampleMod = getSampleName()
        if debug:
            # for testing purposes, set debug=True
            print(sampleMod)
            yield from bps.sleep(20)
        else:
            yield from sync_order_numbers()
            md["title"] = sampleMod
            yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = getSampleName()
            md["title"] = sampleMod
            yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = getSampleName()
            md["title"] = sampleMod
            yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    def collectWAXS(debug=False):
        """
        documentation here
        """
        sampleMod = getSampleName()
        if debug:
            # for testing purposes, set debug=True
            print(sampleMod)
            yield from bps.sleep(20)
        else:
            md["title"] = sampleMod
            yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    appendToMdFile("  ***  ")
    appendToMdFile(f"Collecting data for Sample {scan_title}")
    logger.info("using FanPTC10Plan")
    appendToMdFile("using FanPTC10Plan")

    yield from before_command_list()  # this will run usual startup scripts for scans
    t0 = time.time()
    yield from collectAllThree()  # collect RT data

    yield from bps.mv(
        ptc10.ramp, rate1 / 60.0
    )  # user wants C/min, controller wants C/s
    yield from bps.mv(
        ptc10.temperature.setpoint, temp1
    )  # Change the temperature and not wait
    yield from setheaterOn()

    logger.info(f"Ramping temperature to {temp1} C")
    appendToMdFile(f"Ramping temperature to {temp1} C")

    while (
        not ptc10.temperature.inposition
    ):  # runs data collection until next temp or sleeps. Change as needed.
        # yield from bps.sleep(5)
        logger.info(f"Still Ramping temperature to {temp1} C")
        yield from collectWAXS()

    # logger.info("Reached temperature, now collecting data for %s minutes", delay1min)
    logger.info("Reached temperature, now collecting data for %s seconds", delay1)
    appendToMdFile(f"Reached temperature, now collecting data for {delay1} seconds")
    t1 = time.time()

    while time.time() - t1 < delay1 * 60:  # collects data for delay1 seconds
        logger.info("Collecting data for %s ", delay1)
        yield from collectAllThree()

    logger.info("waited for %s seconds, now changing temperature to %s C", rate2, temp2)
    appendToMdFile(f"waited for {delay1} seconds, now changing temperature to {temp2} C")

    yield from bps.mv(ptc10.ramp, rate2 / 60.0)  # sets the rate of next ramp
    yield from bps.mv(
        ptc10.temperature.setpoint, temp2
    )  # Change the temperature and NOT wait to get there

    while (
        not ptc10.temperature.inposition
    ):  # runs data collection until next temp or sleeps. Change as needed.
        logger.info(f"Still Ramping temperature to {temp2} C")
        yield from collectWAXS()

    logger.info(f"reached {temp2} C")
    appendToMdFile(f"reached {temp2} C")
    yield from collectAllThree()

    yield from setheaterOff()

    yield from after_command_list()  # runs standard after scan scripts.

    logger.info("finished")


def FanPTC10OvernightPlan(pos_X, pos_Y, thickness, scan_title, temp1, rate1, delay1, temp2, rate2, md={}):
    """
    collect RT USAXS/SAXS/WAXS - or not, change code
    change temperature T to temp1 with rate1
    collect WAXS while heating or sleep= change code...
    when temp1 reached, hold for delay1 seconds, collecting data repeatedly
    change T to temp2 with rate2
    collect USAXS/SAXS/WAXS while changing temp
    when temp2 reached collect final data
    and it will end here...

    reload by
    # %run -i ptc10_local
    """

    def getSampleName():
        """
        return the name of the sample
        """
        return f"{scan_title}_{ptc10.position:.0f}C_{(time.time()-t0)/60:.0f}min"

    def collectAllThree(debug=False):
        """
        documentation here
        """
        sampleMod = getSampleName()
        if debug:
            # for testing purposes, set debug=True
            print(sampleMod)
            yield from bps.sleep(20)
        else:
            yield from sync_order_numbers()
            md["title"] = sampleMod
            yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = getSampleName()
            md["title"] = sampleMod
            yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = getSampleName()
            md["title"] = sampleMod
            yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    def collectWAXS(debug=False):
        """
        documentation here
        """
        sampleMod = getSampleName()
        if debug:
            # for testing purposes, set debug=True
            print(sampleMod)
            yield from bps.sleep(20)
        else:
            md["title"] = sampleMod
            yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    appendToMdFile("  ***  ")
    appendToMdFile(f"Collecting data for Sample {scan_title}")
    logger.info("using FanPTC10OvernightPlan")
    appendToMdFile("using FanPTC10OvernightPlan")

    # run #1
    yield from before_command_list()  # this will run usual startup scripts for scans
    t0 = time.time()
    yield from collectAllThree()  # collect RT data

    yield from bps.mv(
        ptc10.ramp, rate1 / 60.0
    )  # user wants C/min, controller wants C/s
    yield from bps.mv(
        ptc10.temperature.setpoint, temp1
    )  # Change the temperature and not wait
    yield from setheaterOn()

    logger.info(f"Ramping temperature to {temp1} C")
    appendToMdFile(f"Ramping temperature to {temp1} C")

    while (
        not ptc10.temperature.inposition
    ):  # runs data collection until next temp or sleeps. Change as needed.
        # yield from bps.sleep(5)
        logger.info(f"Still Ramping temperature to {temp1} C")
        yield from collectWAXS()

    # logger.info("Reached temperature, now collecting data for %s minutes", delay1min)
    logger.info("Reached temperature, now collecting data for %s seconds", delay1)
    appendToMdFile(f"Reached temperature, now collecting data for {delay1} seconds")
    t1 = time.time()

    while time.time() - t1 < delay1 * 60:  # collects data for delay1 seconds
        logger.info("Collecting data for %s ", delay1)
        yield from collectAllThree()

    logger.info("waited for %s seconds, now changing temperature to %s C", rate2, temp2)
    appendToMdFile(f"waited for {delay1} seconds, now changing temperature to {temp2} C")

    yield from bps.mv(ptc10.ramp, rate2 / 60.0)  # sets the rate of next ramp
    yield from bps.mv(
        ptc10.temperature.setpoint, temp2
    )  # Change the temperature and NOT wait to get there

    while (
        not ptc10.temperature.inposition
    ):  # runs data collection until next temp or sleeps. Change as needed.
        logger.info(f"Still Ramping temperature to {temp2} C")
        yield from collectAllThree()

    logger.info(f"reached {temp2} C")
    appendToMdFile(f"reached {temp2} C")
    yield from collectAllThree()
    # run2
    t0 = time.time()
    yield from collectAllThree()  # collect RT data

    yield from bps.mv(
        ptc10.ramp, rate1 / 60.0
    )  # user wants C/min, controller wants C/s
    yield from bps.mv(
        ptc10.temperature.setpoint, temp1
    )  # Change the temperature and not wait

    logger.info(f"Ramping temperature to {temp1} C")
    appendToMdFile(f"Ramping temperature to {temp1} C")

    while (
        not ptc10.temperature.inposition
    ):  # runs data collection until next temp or sleeps. Change as needed.
        # yield from bps.sleep(5)
        logger.info(f"Still Ramping temperature to {temp1} C")
        yield from collectWAXS()

    # logger.info("Reached temperature, now collecting data for %s minutes", delay1min)
    logger.info("Reached temperature, now collecting data for %s seconds", delay1)
    appendToMdFile(f"Reached temperature, now collecting data for {delay1} seconds")
    t1 = time.time()

    while time.time() - t1 < delay1 * 60:  # collects data for delay1 seconds
        logger.info("Collecting data for %s ", delay1)
        yield from collectAllThree()

    logger.info("waited for %s seconds, now changing temperature to %s C", rate2, temp2)
    appendToMdFile(f"waited for {delay1} seconds, now changing temperature to {temp2} C")

    yield from bps.mv(ptc10.ramp, rate2 / 60.0)  # sets the rate of next ramp
    yield from bps.mv(
        ptc10.temperature.setpoint, temp2
    )  # Change the temperature and NOT wait to get there

    while (
        not ptc10.temperature.inposition
    ):  # runs data collection until next temp or sleeps. Change as needed.
        logger.info(f"Still Ramping temperature to {temp2} C")
        yield from collectWAXS()

    logger.info(f"reached {temp2} C")
    appendToMdFile(f"reached {temp2} C")
    yield from collectAllThree()
    # run3
    t0 = time.time()
    yield from collectAllThree()  # collect RT data

    yield from bps.mv(
        ptc10.ramp, rate1 / 60.0
    )  # user wants C/min, controller wants C/s
    yield from bps.mv(
        ptc10.temperature.setpoint, temp1
    )  # Change the temperature and not wait

    logger.info(f"Ramping temperature to {temp1} C")
    appendToMdFile(f"Ramping temperature to {temp1} C")

    while (
        not ptc10.temperature.inposition
    ):  # runs data collection until next temp or sleeps. Change as needed.
        # yield from bps.sleep(5)
        logger.info(f"Still Ramping temperature to {temp1} C")
        yield from collectWAXS()

    # logger.info("Reached temperature, now collecting data for %s minutes", delay1min)
    logger.info("Reached temperature, now collecting data for %s seconds", delay1)
    appendToMdFile(f"Reached temperature, now collecting data for {delay1} seconds")
    t1 = time.time()

    while time.time() - t1 < delay1 * 60:  # collects data for delay1 seconds
        logger.info("Collecting data for %s ", delay1)
        yield from collectAllThree()

    logger.info("waited for %s seconds, now changing temperature to %s C", rate2, temp2)
    appendToMdFile(f"waited for {delay1} seconds, now changing temperature to {temp2} C")

    yield from bps.mv(ptc10.ramp, rate2 / 60.0)  # sets the rate of next ramp
    yield from bps.mv(
        ptc10.temperature.setpoint, temp2
    )  # Change the temperature and NOT wait to get there

    while (
        not ptc10.temperature.inposition
    ):  # runs data collection until next temp or sleeps. Change as needed.
        logger.info(f"Still Ramping temperature to {temp2} C")
        yield from collectWAXS()

    logger.info(f"reached {temp2} C")
    appendToMdFile(f"reached {temp2} C")
    
    yield from collectAllThree()

    yield from setheaterOff()

    yield from after_command_list()  # runs standard after scan scripts.
    appendToMdFile(f"Finished collecting data for Sample {scan_title}")
    appendToMdFile("  ***  ")
    logger.info("finished")
