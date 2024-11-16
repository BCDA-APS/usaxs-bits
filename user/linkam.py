"""
BS plan to control Linkam temperature during data collection same as spec used to do.

///IMPORTANT: Assumes all objects from ./heater_profile.py are imported!
///    %run -i heater_profile.py
load this way:

    %run -im user.linkam

* file: /USAXS_data/bluesky_plans/linkam.py
* aka:  ~/.ipython/user/linkam.py

* PRJ, 2022-01-22 : updated for new linkam support
* JIL, 2021-11-12 : modified to use updated before_command_list(), verify operations
* JIL, 2022-11-05 : 20ID test
"""

from user.heater_profile import change_ramp_rate
from user.heater_profile import linkam_change_setpoint
from user.heater_profile import MINUTE
import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

from bluesky import plan_stubs as bps
from ophyd import Signal
import time

from instrument.devices import linkam_ci94, linkam_tc1
from instrument.plans import SAXS, USAXSscan, WAXS
from instrument.plans import before_command_list, after_command_list

linkam_debug = Signal(name="linkam_debug",value=False)
#   In order to run as debug (without collecting data, only control Linkam) in command line run:
#linkam_debug.put(True)


def myLinkamPlan(pos_X, pos_Y, thickness, scan_title, temp1, rate1, delay1min, temp2, rate2, md={}):
    """
    TODO: Check code in /USAXS_data/bluesky_plans/linkam.py (this file)
     is using tc1, edit and reload if necessary ***

    0. use linkam_tc1
    1. collect 40C (~RT) USAXS/SAXS/WAXS
    2. change temperature T to temp1 with rate1, does NOT collect USAXS/SAXS/WAXS while heating
    3. when temp1 reached, hold for delay delay1min minutes, collecting data repeatedly
    4. changes T to temp2 with rate2, does NOT collect USAXS/SAXS/WAXS while heating/cooling
    5. when temp2 reached, collect final data
    and it will end here...
    Temp is in C, delay is in minutes

    reload by
    # %run -im user.linkam
    """

    def setSampleName():
        return (
            f"{scan_title}"
            f"_{linkam.temperature.position:.0f}C"
            f"_{(time.time()-t0)/60:.0f}min"
        )

    def collectAllThree(debug=False):
        sampleMod = setSampleName()
        if debug:
            #for testing purposes, set debug=True
            print(sampleMod)
            yield from bps.sleep(20)
        else:
            md["title"]=sampleMod
            yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = setSampleName()
            md["title"]=sampleMod
            yield from SAXS(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = setSampleName()
            md["title"]=sampleMod
            yield from WAXS(pos_X, pos_Y, thickness, sampleMod, md={})

    linkam = linkam_tc1     #New Linkam from windows ioc (all except NIST 1500).
    #linkam = linkam_ci94   #this is old TS1500 NIST from LAX
    #logger.info(f"Linkam controller PV prefix={linkam.prefix}")
    isDebugMode = linkam_debug.get()

    # TODO: what about HeaterStopAndHoldRequested?

    if isDebugMode is not True:
        yield from before_command_list()                #this will run usual startup scripts for scans

    # Collect data at 40C as Room temperature data.
    yield from change_ramp_rate(150)                    # for next ramp
    yield from linkam_change_setpoint(40, wait=True)    # sets the temp of to 40C, waits until we get there (no data collection)
    t0 = time.time()                                    # mark start time of data collection.
    yield from collectAllThree(isDebugMode)

    #Heating cycle 1 - ramp up and hold
    logger.info(f"Ramping temperature to {temp1} C")        # for the log file
    yield from change_ramp_rate(rate1)                      # next ramp at rate1 (deg C/min)
    yield from linkam_change_setpoint(temp1, wait=True)     # start ramp to temp1 (C)

    t0 = time.time()                                    # mark start time of data collection.

    #while not linkam.temperature.inposition:                # data collection until we reach temp1.
        # checks only once per USAXS/SAXS?WAXS cycle, basically once each 3-4 minutes
        #yield from collectAllThree(isDebugMode)             # USAXS, SAXS, WAXS

    checkpoint = time.time() + delay1min*MINUTE             # time to end ``delay1min`` hold period

    logger.info(f"Reached temperature, now collecting data for {delay1min} minutes")

    while time.time() < checkpoint:                         # collects USAXS/SAXS/WAXS data while holding at temp1
        yield from collectAllThree(isDebugMode)

    #Cooling cycle - cool down
    logger.info(f"Waited for {delay1min} minutes, now changing temperature to {temp2} C")

    yield from change_ramp_rate(rate2)                      # next ramp at rate2 (deg C/min)
    yield from linkam_change_setpoint(temp2, wait=True)    # start ramp to temp2 (C). Typically cooling period

    #while not linkam.temperature.inposition:                # data collection until we reach temp2.
    #    yield from collectAllThree(isDebugMode)

    logger.info(f"reached {temp2} C")                   # record we reached tmep2

    #End run data collection - after cooling
    yield from collectAllThree(isDebugMode)             #collect USAXS/SAXS/WAXS data at the end, typically temp2 is 40C

    logger.info(f"finished")                            #record end.

    if isDebugMode is not True:
       yield from after_command_list()                  # runs standard after scan scripts.


def fanLinkamPlan(pos_X, pos_Y, thickness, scan_title, temp1, rate1, delay1min, temp2, rate2, delay2min, md={}):
    """
    TODO: Check code in /USAXS_data/bluesky_plans/linkam.py (this file)
     is using tc1, edit and reload if necessary ***

    0. use linkam_tc1
    1. collect 40C (~RT) USAXS/SAXS/WAXS
    2. change temperature T to temp1 with rate1 do nto collect data (too fast)
    3. when temp1 reached, hold for delay temp1 minutes, collecting data repeatedly
    4. Cool down to 40C, collect data
    4. change T to temp2 with rate2, do not collect data, too fast
    5. when temp2 reached, hold for delay2min, collecting data
    6. cool down, collect final data
    and it will end here...
    Temp is in C, delay is in minutes

    reload by
    # %run -im user.linkam
    """

    def setSampleName():
        return (
            f"{scan_title}"
            f"_{linkam.temperature.position:.0f}C"
            f"_{(time.time()-t0)/60:.0f}min"
        )

    def collectAllThree(debug=False):
        sampleMod = setSampleName()
        if debug:
            #for testing purposes, set debug=True
            print(sampleMod)
            yield from bps.sleep(20)
        else:
            md["title"]=sampleMod
            yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = setSampleName()
            md["title"]=sampleMod
            yield from SAXS(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = setSampleName()
            md["title"]=sampleMod
            yield from WAXS(pos_X, pos_Y, thickness, sampleMod, md={})

    def change_rate_and_temperature(rate, t, wait=False):
        yield from change_ramp_rate(rate)
        yield from linkam_change_setpoint(t, wait=wait)

    linkam = linkam_tc1     #New Linkam from windows ioc (all except NIST 1500).
    #linkam = linkam_ci94   #this is old TS1500 NIST from LAX
    logger.info(f"Linkam controller PV prefix={linkam.prefix}")
    isDebugMode = linkam_debug.get()

    if isDebugMode is not True:
        yield from before_command_list()                #this will run usual startup scripts for scans

    # Collect data at 40C as Room temperature data.
    yield from change_rate_and_temperature(150, 40, wait=True)
    t0 = time.time()                                    # mark start time of data collection.
    yield from collectAllThree(isDebugMode)

    #Heating cycle 1 - ramp up and hold
    yield from change_rate_and_temperature(rate1, temp1, wait=True)
    logger.info("Ramped temperature to %s C", temp1)        # for the log file
    t0 = time.time()                                    # mark start time of data collection at temperature 1.

    checkpoint = time.time() + delay1min*MINUTE             # time to end ``delay1min`` hold period

    logger.info("Reached temperature, now collecting data for %s minutes", delay1min)

    while time.time() < checkpoint:                         # collects USAXS/SAXS/WAXS data while holding at temp1
        yield from collectAllThree(isDebugMode)

    ##Cooling cycle - cool down
    #logger.info("Waited for %s minutes, now changing temperature to 40 C", delay1min)
    #yield from change_rate_and_temperature(150, 40, wait=True)
    
    #logger.info("reached 40 C")                              # record we reached tmep2
    #yield from collectAllThree(isDebugMode)

    #cycle 2
    logger.info("Changing temperature to %s C", temp2)

    yield from change_rate_and_temperature(rate2, temp2, wait=True)
    
    logger.info("Ramped temperature to %s C", temp2)        # for the log file
    
    t0 = time.time()                                    # mark start time of data collection at temperature 2

    checkpoint = time.time() + delay2min*MINUTE             # time to end ``delay2min`` hold period

    logger.info("Reached temperature, now collecting data for %s minutes", delay2min)

    while time.time() < checkpoint:                         # collects USAXS/SAXS/WAXS data while holding at temp1
        yield from collectAllThree(isDebugMode)

    #Cooling cycle - cool down
    logger.info("Waited for %s minutes, now changing temperature to 40 C", delay2min)

    yield from change_rate_and_temperature(150, 40, wait=False)
 
    while not linkam.temperature.inposition:              # data collection until we reach temp2.
        yield from collectAllThree(isDebugMode)

    logger.info("reached 40 C")                           # record we reached tmep2

    #End run data collection - after cooling
    yield from collectAllThree(isDebugMode)             #collect USAXS/SAXS/WAXS data at the end, typically temp2 is 40C

    logger.info("finished")                            #record end.

    if isDebugMode is not True:
       yield from after_command_list()                  # runs standard after scan scripts.


def Fan718LinkamPlan(pos_X, pos_Y, thickness, scan_title, temp1, rate1, delay1min, temp2, rate2, delay2min, temp3, rate3, delay3min, md={}):
    """
    TODO: Check code in /USAXS_data/bluesky_plans/linkam.py (this file)
     is using tc1, edit and reload if necessary ***

    0. use linkam_tc1
    1. collect 40C (~RT) USAXS/SAXS/WAXS
    2. change temperature T to temp1 with rate1 do nto collect data (too fast)
    3. when temp1 reached, hold for delay temp1 minutes, collecting data repeatedly
    4. Cool down to 40C, collect data
    4. change T to temp2 with rate2, do not collect data, too fast
    5. when temp2 reached, hold for delay2min, collecting data
    6. cool down, collect final data
    and it will end here...
    Temp is in C, delay is in minutes

    reload by
    # %run -im user.linkam
    """

    def setSampleName():
        return (
            f"{scan_title}"
            f"_{linkam.temperature.position:.0f}C"
            f"_{(time.time()-t0)/60:.0f}min"
        )

    def collectAllThree(debug=False):
        sampleMod = setSampleName()
        if debug:
            #for testing purposes, set debug=True
            print(sampleMod)
            yield from bps.sleep(20)
        else:
            md["title"]=sampleMod
            yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = setSampleName()
            md["title"]=sampleMod
            yield from SAXS(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = setSampleName()
            md["title"]=sampleMod
            yield from WAXS(pos_X, pos_Y, thickness, sampleMod, md={})

    def change_rate_and_temperature(rate, t, wait=False):
        yield from change_ramp_rate(rate)
        yield from linkam_change_setpoint(t, wait=wait)

    linkam = linkam_tc1     #New Linkam from windows ioc (all except NIST 1500).
    #linkam = linkam_ci94   #this is old TS1500 NIST from LAX
    logger.info(f"Linkam controller PV prefix={linkam.prefix}")
    isDebugMode = linkam_debug.get()

    if isDebugMode is not True:
        yield from before_command_list()                #this will run usual startup scripts for scans

    # Collect data at 40C as Room temperature data.
    yield from change_rate_and_temperature(150, 40, wait=True)
    t0 = time.time()                                    # mark start time of data collection.
    yield from collectAllThree(isDebugMode)

    #Heating cycle 1 - ramp up and hold
    yield from change_rate_and_temperature(rate1, temp1, wait=True)
    logger.info("Ramped temperature to %s C", temp1)        # for the log file
    t0 = time.time()                                    # mark start time of data collection at temperature 1.

    checkpoint = time.time() + delay1min*MINUTE             # time to end ``delay1min`` hold period

    logger.info("Reached temperature, now collecting data for %s minutes", delay1min)

    while time.time() < checkpoint:                         # collects USAXS/SAXS/WAXS data while holding at temp1
        yield from collectAllThree(isDebugMode)

    ##Cooling cycle - cool down
    #logger.info("Waited for %s minutes, now changing temperature to 40 C", delay1min)
    #yield from change_rate_and_temperature(150, 40, wait=True)
    
    #logger.info("reached 40 C")                              # record we reached tmep2
    #yield from collectAllThree(isDebugMode)

    #cycle 2
    logger.info("Changing temperature to %s C", temp2)

    yield from change_rate_and_temperature(rate2, temp2, wait=True)
    
    logger.info("Ramped temperature to %s C", temp2)        # for the log file
    
    t0 = time.time()                                    # mark start time of data collection at temperature 2

    checkpoint = time.time() + delay2min*MINUTE             # time to end ``delay2min`` hold period

    logger.info("Reached temperature, now collecting data for %s minutes", delay2min)

    while time.time() < checkpoint:                         # collects USAXS/SAXS/WAXS data while holding at temp1
        yield from collectAllThree(isDebugMode)


 
    #cycle 3
    logger.info("Changing temperature to %s C", temp3)

    yield from change_rate_and_temperature(rate3, temp3, wait=False)
    
    while not linkam.temperature.inposition:              # data collection until we reach temp2.
          yield from collectAllThree(isDebugMode)
    
    logger.info("Ramped temperature to %s C", temp3)        # for the log file
    
    t0 = time.time()                                    # mark start time of data collection at temperature 2

    checkpoint = time.time() + delay3min*MINUTE             # time to end ``delay2min`` hold period

    logger.info("Reached temperature, now collecting data for %s minutes", delay3min)

    while time.time() < checkpoint:                         # collects USAXS/SAXS/WAXS data while holding at temp1
        yield from collectAllThree(isDebugMode)       

    #Cooling cycle - cool down
    logger.info("Waited for %s minutes, now changing temperature to 40 C", delay2min)

    yield from change_rate_and_temperature(150, 40, wait=False)
 
    while not linkam.temperature.inposition:              # data collection until we reach temp2.
        yield from collectAllThree(isDebugMode)

    logger.info("reached 40 C")                           # record we reached tmep2

    #End run data collection - after cooling
    yield from collectAllThree(isDebugMode)             #collect USAXS/SAXS/WAXS data at the end, typically temp2 is 40C

    logger.info("finished")                            #record end.

    if isDebugMode is not True:
       yield from after_command_list()                  # runs standard after scan scripts.

def FanCryoPlan(pos_X, pos_Y, thickness, scan_title, temp1, rate1, delay1min, temp2, rate2, delay2min, md={}):
    """
    TODO: Check code in /USAXS_data/bluesky_plans/linkam.py (this file)
     is using tc1, edit and reload if necessary ***

    0. use linkam_tc1
    1. collect 40C (~RT) USAXS/SAXS/WAXS
    2. change temperature T to temp1 with rate1 do nto collect data (too fast)
    3. when temp1 reached, hold for delay temp1 minutes, collecting data repeatedly
    4. Cool down to 40C, collect data
    4. change T to temp2 with rate2, do not collect data, too fast
    5. when temp2 reached, hold for delay2min, collecting data
    6. cool down, collect final data
    and it will end here...
    Temp is in C, delay is in minutes

    reload by
    # %run -im user.linkam
    """

    def setSampleName():
        return (
            f"{scan_title}"
            f"_{linkam.temperature.position:.0f}C"
            f"_{(time.time()-t0)/60:.0f}min"
        )

    def collectAllThree(debug=False):
        sampleMod = setSampleName()
        if debug:
            #for testing purposes, set debug=True
            print(sampleMod)
            yield from bps.sleep(20)
        else:
            md["title"]=sampleMod
            yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = setSampleName()
            md["title"]=sampleMod
            yield from SAXS(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = setSampleName()
            md["title"]=sampleMod
            yield from WAXS(pos_X, pos_Y, thickness, sampleMod, md={})


    def collectWAXSOnly(debug=False):
        sampleMod = setSampleName()
        if debug:
            print(sampleMod)
            yield from bps.sleep(20)
        else:
            md["title"]=sampleMod
            yield from WAXS(pos_X, pos_Y, thickness, sampleMod, md={})


    def change_rate_and_temperature(rate, t, wait=False):
        yield from change_ramp_rate(rate)
        yield from linkam_change_setpoint(t, wait=wait)

    linkam = linkam_tc1     #New Linkam from windows ioc (all except NIST 1500).
    #linkam = linkam_ci94   #this is old TS1500 NIST from LAX
    logger.info(f"Linkam controller PV prefix={linkam.prefix}")
    isDebugMode = linkam_debug.get()

    if isDebugMode is not True:
        yield from before_command_list()                #this will run usual startup scripts for scans

    # Collect data at 30C as Room temperature data.
    yield from change_rate_and_temperature(150, 30, wait=True)
    t0 = time.time()                                    # mark start time of data collection.
    yield from collectAllThree(isDebugMode)

    #Heating cycle 1 - ramp up and hold
    yield from change_rate_and_temperature(rate1, temp1, wait=False)
    
    while not linkam.temperature.inposition:              # data collection until we reach temp2.
        yield from collectWAXSOnly(isDebugMode)
        
        
    logger.info("Ramped temperature to %s C", temp1)        # for the log file
    t0 = time.time()                                    # mark start time of data collection at temperature 1.

     
    checkpoint = time.time() + delay1min*MINUTE             # time to end ``delay1min`` hold period

    logger.info("Reached temperature, now collecting data for %s minutes", delay1min)

    while time.time() < checkpoint:                         # collects USAXS/SAXS/WAXS data while holding at temp1
        yield from collectWAXSOnly(isDebugMode)



    #cycle 2
    logger.info("Changing temperature to %s C", temp2)

    yield from change_rate_and_temperature(rate2, temp2, wait=False)
    
    while not linkam.temperature.inposition:              # data collection until we reach temp2.
        yield from collectWAXSOnly(isDebugMode)
            
    logger.info("Ramped temperature to %s C", temp2)        # for the log file
    
    t0 = time.time()                                    # mark start time of data collection at temperature 2

    checkpoint = time.time() + delay2min*MINUTE             # time to end ``delay2min`` hold period

    logger.info("Reached temperature, now collecting data for %s minutes", delay2min)

    while time.time() < checkpoint:                         # collects USAXS/SAXS/WAXS data while holding at temp1
        yield from collectWAXSOnly(isDebugMode)

    #Cooling cycle - cool down
    logger.info("Waited for %s minutes, now changing temperature to 30 C", delay2min)

    yield from change_rate_and_temperature(150, 30, wait=False)
 
    while not linkam.temperature.inposition:              # data collection until we reach temp2.
        yield from collectWAXSOnly(isDebugMode)

    logger.info("reached 40 C")                           # record we reached tmep2

    #End run data collection - after cooling
    yield from collectAllThree(isDebugMode)             #collect USAXS/SAXS/WAXS data at the end, typically temp2 is 40C

    logger.info("finished")                            #record end.

    if isDebugMode is not True:
       yield from after_command_list()                  # runs standard after scan scripts.

