"""
BS plan template to control Linkam temperature during data collection same as spec used to do.

???: Assumes all objects from ./heater_profile.py are imported!
load this way:
    %run -im usaxs.user.linkam


* PRJ, 2022-01-22 : updated for new linkam support
* JIL, 2021-11-12 : modified to use updated before_command_list(), verify operations
* JIL, 2022-11-05 : 20ID test
* JIL, 2024-12-03 : 12ID check and fix. Needs testing
* JIL, 2025-05-28 : fixs for BITS
* JIL, 2025-7-14  : operations

limitations: uses new Linkam support only for tc1 with linux ioc

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
from ophyd import Signal
from usaxs.plans.command_list import sync_order_numbers

linkam_tc1 = oregistry["linkam_tc1"]

SECOND = 1
MINUTE = 60 * SECOND
HOUR = 60 * MINUTE
DAY = 24 * HOUR
WEEK = 7 * DAY

linkam_debug = Signal(name="linkam_debug", value=False)
#   In order to run as debug (without collecting data, only control Linkam) in command line run:
# linkam_debug.put(True)


# ***************************************************************
# DO NOT MODIFY THE TEMPLATE, COPY AND EDIT OR MAKE A NEW FILE...
def myLinkamPlan_template(
    pos_X, pos_Y, thickness, scan_title, temp1, rate1, delay1min, temp2, rate2, md={}
):
    """
    0. use linkam_tc1
    1. collect 40C (~RT) USAXS/SAXS/WAXS
    2. change temperature T to temp1 with rate1, does NOT collect USAXS/SAXS/WAXS while heating
    3. when temp1 reached, hold for delay delay1min minutes, collecting data repeatedly
    4. changes T to temp2 with rate2, does NOT collect USAXS/SAXS/WAXS while heating/cooling
    5. when temp2 reached, collect final data
    and it will end here...
    Temp is in C, delay is in minutes

    reload by
        %run -im user.linkam
    """

    # DO NOT CHANGE FOLLOWING METHODS
    # unless you need to remove WAXS or SAXS from scans...
    def setSampleName():
        return (
            f"{scan_title}"
            f"_{linkam.temperature.position:.0f}C"
            f"_{(time.time()-t0)/60:.0f}min"
        )

    def collectAllThree(debug=False):
        sampleMod = setSampleName()
        if debug:
            # for testing purposes, set debug=True
            print(sampleMod)
            yield from bps.sleep(20)
        else:
            md["title"] = sampleMod
            yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = setSampleName()
            md["title"] = sampleMod
            yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = setSampleName()
            md["title"] = sampleMod
            yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    def change_rate_and_temperature(rate, t, wait=False):
        yield from bps.mv(
            linkam.ramprate.setpoint, rate
        )  # ramp rate for next temperature change in degC/min
        yield from linkam.set_target(
            t, wait=wait
        )  # sets the temp of to t, wait = True waits until we get there (no data collection), wait = False does not wait and enables data collection

    # DO NOT CHANGE ABOVE METHODS
    # ***************************************************************

    linkam = linkam_tc1  # New Linkam from windows ioc (all except NIST 1500).
    isDebugMode = linkam_debug.get()

    # run usual startup scripts for scans.
    if isDebugMode is not True:
        yield from before_command_list()  # this will run usual startup scripts for scans

    # Collect data at 40C as Room temperature data.
    yield from change_rate_and_temperature(
        150, 40, wait=True
    )  # rate for next ramp, default 150C/min,sets the temp of to 40C, waits until we get there (no data collection)
    t0 = time.time()  # set this moment as the start time of data collection.
    yield from collectAllThree(isDebugMode)  # collect the data at RT

    # *******
    # Heating cycle 1 - ramp up and hold
    logger.info(f"Ramping temperature to {temp1} C")  # for the log file
    yield from change_rate_and_temperature(
        rate1, temp1, wait=True
    )  # set rate & temp this cycle, wait=True waits until we get there (no data collection)
    # yield from change_rate_and_temperature(rate1,temp1,wait=False)     # set rate & temp this cycle, wait=False contniues for data collection
    #   do we want to reset the time here again?
    t0 = time.time()  # set this moment as the start time of data collection.
    #   this will get actually run only if we used wait=False above, in which case we collect data while heating/cooling
    # while not linkam.temperature.inposition:                # data collection until we reach temp1.
    # checks only once per USAXS/SAXS/WAXS cycle, basically once each 1-2 minutes
    # yield from collectAllThree(isDebugMode)             # USAXS, SAXS, WAXS data collection

    # by now are at temp1 and should hold for delay1min:
    checkpoint = (
        time.time() + delay1min * 60
    )  # calculate time to end ``delay1min`` hold period
    logger.info(f"Reached temperature, now collecting data for {delay1min} minutes")
    # this collects data for delay1minm
    while (
        time.time() < checkpoint
    ):  # collects USAXS/SAXS/WAXS data while holding at temp1
        yield from collectAllThree(isDebugMode)

    # *******
    # Cooling cycle
    logger.info(
        f"Waited for {delay1min} minutes, now changing temperature to {temp2} C"
    )

    # set linkam conditions
    # yield from change_rate_and_temperature(rate2,temp2,wait=True)     # set rate & temp this cycle, wait=True waits until we get there (no data collection)
    yield from change_rate_and_temperature(
        rate2, temp2, wait=False
    )  # set rate & temp this cycle, wait=False contniues for data collection
    #   this will get actually run only if we used wait=False above, in which case we collect data while heating/cooling
    while not linkam.temperature.inposition:  # data collection until we reach temp2.
        # checks only once per USAXS/SAXS/WAXS cycle, basically once each 1-2 minutes
        yield from collectAllThree(isDebugMode)  # USAXS, SAXS, WAXS data collection
    logger.info(f"reached {temp2} C")  # record we reached temp2

    # End run data collection - after cooling
    yield from collectAllThree(
        isDebugMode
    )  # collect USAXS/SAXS/WAXS data at the end, typically temp2 is 40C
    logger.info("finished")  # record end.

    if isDebugMode is not True:
        yield from after_command_list()  # runs standard after scan scripts.
    # end of this template functio.

# def testTempControl(md={}):
#     def change_rate_and_temperature(rate, t, wait=False):
#         yield from bps.mv(
#             linkam.ramprate.setpoint, rate
#         )  # ramp rate for next temperature change in degC/min
#         yield from linkam.set_target(
#             t, wait=wait
#         )  # sets the temp of to t, wait = True waits until we get there (no data collection), wait = False does not wait and enables data collection

#     linkam = linkam_tc1  # New Linkam from windows ioc (all except NIST 1500).

#     yield from change_rate_and_temperature(20, 55, wait=True)



   

def FanTemperatureRamp(
    pos_X, pos_Y, thickness, scan_title, md={}
):
    """
    Collects data in steps form -40C to 400C 
    steps are 10C, rate is 40C/min
    4 data sets are collected at each temperature 
q
    reload by
        %run -im usaxs.user.linkam
    """

    # DO NOT CHANGE FOLLOWING METHODS
    # unless you need to remove WAXS or SAXS from scans...
    def setSampleName():
        return (
            f"{scan_title}"
            f"_{linkam.temperature.position:.0f}C"
            f"_{(time.time()-t0)/60:.0f}min"
        )

    def collectAllThree():
        sampleMod = setSampleName()
        md["title"] = sampleMod
        yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
        sampleMod = setSampleName()
        md["title"] = sampleMod
        yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
        sampleMod = setSampleName()
        md["title"] = sampleMod
        yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    def change_rate_and_temperature(rate, t, wait=False):
        yield from bps.mv(
            linkam.ramprate.setpoint, rate
        )  # ramp rate for next temperature change in degC/min
        yield from linkam.set_target(
            t, wait=wait
        )  # sets the temp of to t, wait = True waits until we get there (no data collection), wait = False does not wait and enables data collection

    # DO NOT CHANGE ABOVE METHODS
    # ***************************************************************

    linkam = linkam_tc1  # New Linkam from windows ioc (all except NIST 1500).

    # run usual startup scripts for scans.
    yield from before_command_list()  # this will run usual startup scripts for scans

    # Collect data at 4start temperature 
    temp0 = -40
    temp = -40
    iteration = 0
    while temp < 405 : 
        yield from change_rate_and_temperature(40, temp, wait=True)
        t0 = time.time()  # set this moment as the start time of data collection.
        yield from collectAllThree()  # collect the data at RT
        yield from collectAllThree()  # collect the data at RT
        yield from collectAllThree()  # collect the data at RT
        #yield from collectAllThree()  # collect the data at RT
        iteration +=1
        temp = temp0 + iteration*10
    # *******
    yield from change_rate_and_temperature(100, 20, wait=True)     
    t0 = time.time()  # set this moment as the start time of data collection.
    yield from collectAllThree()  # collect the data at RT

    yield from after_command_list()  # runs standard after scan scripts.
    # end of this template functio.



def fanLinkamPlan(
    pos_X,
    pos_Y,
    thickness,
    scan_title,
    temp1,
    rate1,
    delay1min,
    temp2,
    rate2,
    delay2min,
    md={},
):
    """
    TODO: Check code in /USAXS_data/bluesky_plans/linkam.py (this file)
     is using tc1, edit and reload if necessary ***

    0. use linkam_tc1
    1. collect 40C (~RT) USAXS/SAXS/WAXS
    2. change temperature T to temp1 with rate1 do not collect data (too fast)
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
            # for testing purposes, set debug=True
            print(sampleMod)
            yield from bps.sleep(20)
        else:
            md["title"] = sampleMod
            yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = setSampleName()
            md["title"] = sampleMod
            yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = setSampleName()
            md["title"] = sampleMod
            yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    def change_rate_and_temperature(rate, t, wait=False):
        yield from bps.mv(
            linkam.ramprate.setpoint, rate
        )  # ramp rate for next temperature change in degC/min
        yield from linkam.set_target(
            t, wait=wait
        )  # sets the temp of to t, wait = True waits until we get there (no data collection), wait = False does not wait and enables data collection

    linkam = linkam_tc1  # New Linkam from windows ioc (all except NIST 1500).
    logger.info(f"Linkam controller PV prefix={linkam.prefix}")
    isDebugMode = linkam_debug.get()

    if isDebugMode is not True:
        yield from before_command_list()  # this will run usual startup scripts for scans

    # Collect data at 40C as Room temperature data.
    yield from change_rate_and_temperature(
        150, 40, wait=True
    )  # rate for next ramp, default 150C/min,sets the temp of to 40C, waits until we get there (no data collection)
    t0 = time.time()  # set this moment as the start time of data collection.
    yield from collectAllThree(isDebugMode)  # collect the data at RT

    # Heating cycle 1 - ramp up and hold
    yield from change_rate_and_temperature(
        rate1, temp1, wait=True
    )  # change rate/T and wait until there, rate shoudl be high here.
    logger.info("Ramped temperature to %s C", temp1)  # for the log file
    t0 = time.time()  # mark start time of data collection at temperature 1.
    checkpoint = time.time() + delay1min * 60  # time to end ``delay1min`` hold period
    logger.info("Reached temperature, now collecting data for %s minutes", delay1min)
    while (
        time.time() < checkpoint
    ):  # collects USAXS/SAXS/WAXS data while holding at temp1
        yield from collectAllThree(isDebugMode)

    # Cooling cycle - cool down
    logger.info("Waited for %s minutes, now changing temperature to 40 C", delay1min)
    yield from change_rate_and_temperature(150, 40, wait=False)
    while not linkam.temperature.inposition:  # data collection until we reach 40C.
        yield from collectAllThree(isDebugMode)
    logger.info("reached 40 C")  # record we reached tmep2

    # cycle 2
    logger.info("Changing temperature to %s C", temp2)
    yield from change_rate_and_temperature(rate2, temp2, wait=True)
    logger.info("Ramped temperature to %s C", temp2)  # for the log file
    t0 = time.time()  # mark start time of data collection at temperature 2
    checkpoint = time.time() + delay2min * 60  # time to end ``delay2min`` hold period
    logger.info("Reached temperature, now collecting data for %s minutes", delay2min)
    while (
        time.time() < checkpoint
    ):  # collects USAXS/SAXS/WAXS data while holding at temp1
        yield from collectAllThree(isDebugMode)

    # Cooling cycle - cool down
    logger.info("Waited for %s minutes, now changing temperature to 40 C", delay2min)
    yield from change_rate_and_temperature(150, 40, wait=False)
    while not linkam.temperature.inposition:  # data collection until we reach 40C.
        yield from collectAllThree(isDebugMode)
    logger.info("reached 40 C")  # record we reached tmep2

    # End run data collection - after cooling
    yield from collectAllThree(
        isDebugMode
    )  # collect USAXS/SAXS/WAXS data at the end, typically temp2 is 40C
    logger.info("finished")  # record end.
    if isDebugMode is not True:
        yield from after_command_list()  # runs standard after scan scripts.


def Fan718LinkamPlan(
    pos_X,
    pos_Y,
    thickness,
    scan_title,
    temp1,
    rate1,
    delay1min,
    temp2,
    rate2,
    delay2min,
    temp3,
    rate3,
    delay3min,
    md={},
):
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
            # for testing purposes, set debug=True
            print(sampleMod)
            yield from bps.sleep(20)
        else:
            md["title"] = sampleMod
            yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = setSampleName()
            md["title"] = sampleMod
            yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = setSampleName()
            md["title"] = sampleMod
            yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    def change_rate_and_temperature(rate, t, wait=False):
        yield from bps.mv(
            linkam.ramprate.setpoint, rate
        )  # ramp rate for next temperature change in degC/min
        yield from linkam.set_target(
            t, wait=wait
        )  # sets the temp of to t, wait = True waits until we get there (no data collection), wait = False does not wait and enables data collection

    linkam = linkam_tc1  # New Linkam from windows ioc (all except NIST 1500).
    logger.info(f"Linkam controller PV prefix={linkam.prefix}")
    isDebugMode = linkam_debug.get()

    if isDebugMode is not True:
        yield from before_command_list()  # this will run usual startup scripts for scans

    # Collect data at 40C as Room temperature data.
    yield from change_rate_and_temperature(150, 40, wait=True)
    t0 = time.time()  # mark start time of data collection.
    yield from collectAllThree(isDebugMode)

    # Heating cycle 1 - ramp up and hold
    yield from change_rate_and_temperature(rate1, temp1, wait=True)
    logger.info("Ramped temperature to %s C", temp1)  # for the log file
    t0 = time.time()  # mark start time of data collection at temperature 1.
    checkpoint = time.time() + delay1min * 60  # time to end ``delay1min`` hold period
    logger.info("Reached temperature, now collecting data for %s minutes", delay1min)
    while (
        time.time() < checkpoint
    ):  # collects USAXS/SAXS/WAXS data while holding at temp1
        yield from collectAllThree(isDebugMode)

    ##Cooling cycle - cool down
    # logger.info("Waited for %s minutes, now changing temperature to 40 C", delay1min)
    # yield from change_rate_and_temperature(150, 40, wait=True)
    # logger.info("reached 40 C")                              # record we reached tmep2
    # yield from collectAllThree(isDebugMode)

    # cycle 2
    logger.info("Changing temperature to %s C", temp2)
    yield from change_rate_and_temperature(rate2, temp2, wait=True)
    logger.info("Ramped temperature to %s C", temp2)  # for the log file
    t0 = time.time()  # mark start time of data collection at temperature 2
    checkpoint = time.time() + delay2min * 60  # time to end ``delay2min`` hold period
    logger.info("Reached temperature, now collecting data for %s minutes", delay2min)
    while (
        time.time() < checkpoint
    ):  # collects USAXS/SAXS/WAXS data while holding at temp1
        yield from collectAllThree(isDebugMode)

    # cycle 3
    logger.info("Changing temperature to %s C", temp3)
    yield from change_rate_and_temperature(rate3, temp3, wait=False)
    while not linkam.temperature.inposition:  # data collection until we reach temp2.
        yield from collectAllThree(isDebugMode)
    logger.info("Ramped temperature to %s C", temp3)  # for the log file
    t0 = time.time()  # mark start time of data collection at temperature 2
    checkpoint = time.time() + delay3min * 60  # time to end ``delay2min`` hold period
    logger.info("Reached temperature, now collecting data for %s minutes", delay3min)
    while (
        time.time() < checkpoint
    ):  # collects USAXS/SAXS/WAXS data while holding at temp1
        yield from collectAllThree(isDebugMode)

    # Cooling cycle - cool down
    logger.info("Waited for %s minutes, now changing temperature to 40 C", delay2min)
    yield from change_rate_and_temperature(150, 40, wait=False)
    while not linkam.temperature.inposition:  # data collection until we reach temp2.
        yield from collectAllThree(isDebugMode)
    logger.info("reached 40 C")  # record we reached tmep2

    # End run data collection - after cooling
    yield from collectAllThree(
        isDebugMode
    )  # collect USAXS/SAXS/WAXS data at the end, typically temp2 is 40C

    logger.info("finished")  # record end.

    if isDebugMode is not True:
        yield from after_command_list()  # runs standard after scan scripts.


def Fan174Plan(
    pos_X,
    pos_Y,
    thickness,
    scan_title,
    temp1,
    rate1,
    delay1min,
    temp2,
    rate2,
    delay2min,
    md={},
):
    """
    TODO: Check code in /USAXS_data/bluesky_plans/linkam.py (this file)
     is using tc1, edit and reload if necessary ***

    0. use linkam_tc1
    1. collect 30C (~RT) USAXS/SAXS/WAXS
    2. change temperature T to temp1 with rate1, collect WAXS data during this time
    3. when temp1 reached, hold for delay temp1 minutes, collecting data repeatedly, 5xWAXS, USAXS, SAXS, repeat
    4. Cool down to temp2, collecting WAXS data
    5. Collect final data
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
        md["title"] = sampleMod
        yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
        sampleMod = setSampleName()
        md["title"] = sampleMod
        yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
        sampleMod = setSampleName()
        md["title"] = sampleMod
        yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
        sampleMod = setSampleName()
        md["title"] = sampleMod
        yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
        sampleMod = setSampleName()
        md["title"] = sampleMod
        yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
        md["title"] = sampleMod
        yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
        sampleMod = setSampleName()
        md["title"] = sampleMod
        yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    def collectWAXSOnly(debug=False):
        sampleMod = setSampleName()
        md["title"] = sampleMod
        yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    def change_rate_and_temperature(rate, t, wait=False):
        yield from bps.mv(
            linkam.ramprate.setpoint, rate
        )  # ramp rate for next temperature change in degC/min
        yield from linkam.set_target(
            t, wait=wait
        )  # sets the temp of to t, wait = True waits until we get there (no data collection), wait = False does not wait and enables data collection

    linkam = linkam_tc1  # New Linkam from windows ioc (all except NIST 1500).
    logger.info(f"Linkam controller PV prefix={linkam.prefix}")
    isDebugMode = linkam_debug.get()

    # data collection starts here...
    if isDebugMode is not True:
        yield from before_command_list()  # this will run usual startup scripts for scans

    t0 = time.time()  # mark start time of data collection.
    # Collect data at 30C as Room temperature data.
    yield from change_rate_and_temperature(10, 30, wait=True)
    yield from collectAllThree(isDebugMode)
    t0 = time.time()  # mark start time of data collection.

    # Heating cycle 1 - ramp up and hold
    yield from change_rate_and_temperature(rate1, temp1, wait=False)
    while not linkam.temperature.inposition:  # data collection until we reach temp2.
        yield from collectWAXSOnly(isDebugMode)

    yield from sync_order_numbers()

    logger.info("Ramped temperature to %s C", temp1)  # for the log file
    t0 = time.time()  # mark start time of data collection at temperature 1.
    checkpoint = time.time() + delay1min * 60  # time to end ``delay1min`` hold period
    logger.info("Reached temperature, now collecting data for %s minutes", delay1min)
    while (
        time.time() < checkpoint
    ):  # collects USAXS/SAXS/WAXS data while holding at temp1
        yield from collectAllThree(isDebugMode)

    # cycle 2
    logger.info("Changing temperature to %s C", temp2)
    yield from change_rate_and_temperature(rate2, temp2, wait=False)
    while not linkam.temperature.inposition:  # data collection until we reach temp2.
        yield from collectWAXSOnly(isDebugMode)
    logger.info("Ramped temperature to %s C", temp2)  # for the log file
    # t0 = time.time()                                        # mark start time of data collection at temperature 2
    # checkpoint = time.time() + delay2min*60             # time to end ``delay2min`` hold period
    # logger.info("Reached temperature, now collecting data for %s minutes", delay2min)
    # while time.time() < checkpoint:                         # collects USAXS/SAXS/WAXS data while holding at temp1
    #    yield from collectWAXSOnly(isDebugMode)

    # Cooling cycle - cool down
    # logger.info("Waited for %s minutes, now changing temperature to 30 C", delay2min)
    # yield from change_rate_and_temperature(150, 30, wait=False)
    # while not linkam.temperature.inposition:              # data collection until we reach temp2.
    #    yield from collectWAXSOnly(isDebugMode)
    # logger.info("reached 40 C")                           # record we reached tmep2

    # End run data collection - after cooling
    yield from sync_order_numbers()
    yield from collectAllThree(
        isDebugMode
    )  # collect USAXS/SAXS/WAXS data at the end, typically temp2 is 40C

    logger.info("finished")  # record end.

    if isDebugMode is not True:
        yield from after_command_list()  # runs standard after scan scripts.


def Fan625Plan(
    pos_X, pos_Y, thickness, scan_title, temp1, rate1, delay1min, temp2, rate2, md={}
):
    """
    TODO: Check code in /USAXS_data/bluesky_plans/linkam.py (this file)
     is using tc1, edit and reload if necessary ***

    0. use linkam_tc1
    1. collect 40C (~RT) USAXS/SAXS/WAXS
    2. change temperature T to temp1 with rate1, collect WAXS data during this time
    3. when temp1 reached, hold for delay temp1 minutes, collecting data repeatedly, USAXS, SAXS, WAXS, repeat
    4. Cool down to temp2, collecting WAXS data
    5. Collect final data
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
        yield from sync_order_numbers()
        sampleMod = setSampleName()
        md["title"] = sampleMod
        yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
        sampleMod = setSampleName()
        md["title"]=sampleMod
        yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
        sampleMod = setSampleName()
        md["title"] = sampleMod
        yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    def collectWAXSOnly(debug=False):
        sampleMod = setSampleName()
        md["title"] = sampleMod
        yield from WAXS(pos_X, pos_Y, thickness, sampleMod, md={})

    def change_rate_and_temperature(rate, t, wait=False):
        yield from bps.mv(
            linkam.ramprate.setpoint, rate
        )  # ramp rate for next temperature change in degC/min
        yield from linkam.set_target(
            t, wait=wait
        )  # sets the temp of to t, wait = True waits until we get there (no data collection), wait = False does not wait and enables data collection

    linkam = linkam_tc1  # New Linkam from windows ioc (all except NIST 1500).
    logger.info(f"Linkam controller PV prefix={linkam.prefix}")
    isDebugMode = linkam_debug.get()

    # data collection starts here...
    if isDebugMode is not True:
        yield from before_command_list()  # this will run usual startup scripts for scans

    t0 = time.time()  # mark start time of data collection.
    # Collect data at 30C as Room temperature data.
    yield from change_rate_and_temperature(10, 40, wait=True)
    yield from collectAllThree(isDebugMode)
    t0 = time.time()  # mark start time of data collection.

    # Heating cycle 1 - ramp up and hold
    yield from change_rate_and_temperature(rate1, temp1, wait=False)
    while not linkam.temperature.inposition:  # data collection until we reach temp2.
        yield from collectWAXSOnly(isDebugMode)

    logger.info("Ramped temperature to %s C", temp1)  # for the log file
    t0 = time.time()  # mark start time of data collection at temperature 1.
    checkpoint = time.time() + delay1min * 60  # time to end ``delay1min`` hold period
    logger.info("Reached temperature, now collecting data for %s minutes", delay1min)
    while (
        time.time() < checkpoint
    ):  # collects USAXS/SAXS/WAXS data while holding at temp1
        yield from collectAllThree(isDebugMode)

    # cycle 2
    logger.info("Changing temperature to %s C", temp2)
    yield from change_rate_and_temperature(rate2, temp2, wait=False)
    while not linkam.temperature.inposition:  # data collection until we reach temp2.
        yield from collectWAXSOnly(isDebugMode)
    logger.info("Ramped temperature to %s C", temp2)  # for the log file

    yield from collectAllThree(
        isDebugMode
    )  # collect USAXS/SAXS/WAXS data at the end, typically temp2 is 40C

    logger.info("finished")  # record end.

    if isDebugMode is not True:
        yield from after_command_list()  # runs standard after scan scripts.


def myLinkamPlan(
    pos_X, pos_Y, thickness, scan_title, temp1, temp2, delay2min, md={}
):
    """
    0. use linkam_tc1
    1. collect 40C (~RT) USAXS/SAXS/WAXS
    2. change temperature T to temp1 with 40deg/min, does NOT collect USAXS/SAXS/WAXS while heating
    3. when temp1 reached, hold for 5 minutes, collecting data repeatedly
    4. changes T to temp2 with 30deg/min, does NOT collect USAXS/SAXS/WAXS while heating/cooling
    5. when temp2 reached, collect data for delay2min
    2. change temperature T to temp1 with 40deg/min, does NOT collect USAXS/SAXS/WAXS while heating
    3. when temp1 reached, hold for 5 minutes, collecting data repeatedly
    4. changes T to temp2 with 2deg/min, does NOT collect USAXS/SAXS/WAXS while heating/cooling
    5. when temp2 reached, collect data for delay2min
    
    and it will end here...
    Temp is in C, delay is in minutes

    reload by
        %run -im user.linkam
    run as :
        RE(myLinkamPlan(0, 0, 1.5, "test", 320, 260, 260))
    """

    # DO NOT CHANGE FOLLOWING METHODS
    # unless you need to remove WAXS or SAXS from scans...
    def setSampleName():
        return (
            f"{scan_title}"
            f"_{linkam.temperature.position:.0f}C"
            f"_{(time.time()-t0)/60:.0f}min"
        )

    def collectAllThree(debug=False):
        sampleMod = setSampleName()
        if debug:
            # for testing purposes, set debug=True
            print(sampleMod)
            yield from bps.sleep(20)
        else:
            md["title"] = sampleMod
            yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = setSampleName()
            md["title"] = sampleMod
            yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = setSampleName()
            md["title"] = sampleMod
            yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    def change_rate_and_temperature(rate, t, wait=False):
        yield from bps.mv(
            linkam.ramprate.setpoint, rate
        )  # ramp rate for next temperature change in degC/min
        yield from linkam.set_target(
            t, wait=wait
        )  # sets the temp of to t, wait = True waits until we get there (no data collection), wait = False does not wait and enables data collection

    # DO NOT CHANGE ABOVE METHODS
    # ***************************************************************

    # define name of the Linkam from linux ioc (all except NIST 1500).
    linkam = linkam_tc1
    isDebugMode = linkam_debug.get()

    # run usual startup scripts for scans.
    if isDebugMode is not True:
        yield from before_command_list()  # this will run usual startup scripts for scans

    # Collect data at 40C as Room temperature data.
    yield from change_rate_and_temperature(
        40, 40, wait=True
    )  # rate for next ramp, default 150C/min,sets the temp of to 40C, waits until we get there (no data collection)
    t0 = time.time()  # set this moment as the start time of data collection.
    yield from collectAllThree(isDebugMode)  # collect the data at RT

    # *******
    # Heating cycle 1 - ramp up and hold
    logger.info(f"Ramping temperature to {temp1} C")  # for the log file
    yield from change_rate_and_temperature(
        40, temp1, wait=True
    )  # set rate & temp this cycle, wait=True waits until we get there (no data collection)
    # yield from change_rate_and_temperature(rate1,temp1,wait=False)     # set rate & temp this cycle, wait=False contniues for data collection
    #   do we want to reset the time here again?
    t0 = time.time()  # set this moment as the start time of data collection.
    # by now are at temp1 and should hold for delay1min:
    checkpoint = time.time() + 5 * 60  # calculate time to end ``delay1min`` hold period
    logger.info("Reached temperature, now collecting data for 5 minutes")
    # this collects data for delay1minm
    while (time.time() < checkpoint):  # collects USAXS/SAXS/WAXS data while holding at temp1
        yield from collectAllThree(isDebugMode)

    # *******
    # second cycle
    # logger.info(f"Waited for {delay1min} minutes, now changing temperature to {temp2} C")

    # set linkam conditions
    yield from change_rate_and_temperature(
        30, temp2, wait=True
    )  # set rate & temp this cycle, wait=True waits until we get there (no data collection)
    # yield from change_rate_and_temperature(10,temp2,wait=False)     # set rate & temp this cycle, wait=False contniues for data collection
    #   this will get actually run only if we used wait=False above, in which case we collect data while heating/cooling
    # while not linkam.temperature.inposition:                # data collection until we reach temp2.
    # checks only once per USAXS/SAXS/WAXS cycle, basically once each 1-2 minutes
    # yield from collectAllThree(isDebugMode)             # USAXS, SAXS, WAXS data collection
    logger.info(f"reached {temp2} C")  # record we reached temp2

    t0 = time.time()  # set this moment as the start time of data collection.
    # by now are at temp1 and should hold for delay1min:
    checkpoint = (
        time.time() + delay2min * 60
    )  # calculate time to end ``delay1min`` hold period
    # this collects data for delay2min
    while (time.time() < checkpoint):  # collects USAXS/SAXS/WAXS data while holding at temp1
        yield from collectAllThree(isDebugMode)


    # *******
    # Heating cycle 2 - ramp up and hold
    logger.info(f"Ramping temperature to {temp1} C")  # for the log file
    yield from change_rate_and_temperature(
        40, temp1, wait=True
    )  # set rate & temp this cycle, wait=True waits until we get there (no data collection)
    t0 = time.time()  # set this moment as the start time of data collection.
    checkpoint = time.time() + 5 * 60  # calculate time to end ``delay1min`` hold period
    logger.info("Reached temperature, now collecting data for 5 minutes")
    # this collects data for delay1minm
    while (time.time() < checkpoint):  # collects USAXS/SAXS/WAXS data while holding at temp1
        yield from collectAllThree(isDebugMode)

    # *******
    # second cycle
    # logger.info(f"Waited for {delay1min} minutes, now changing temperature to {temp2} C")

    # set linkam conditions
    yield from change_rate_and_temperature(
        2, temp2, wait=True
    )  # set rate & temp this cycle, wait=True waits until we get there (no data collection)
    # yield from change_rate_and_temperature(10,temp2,wait=False)     # set rate & temp this cycle, wait=False contniues for data collection
    #   this will get actually run only if we used wait=False above, in which case we collect data while heating/cooling
    # while not linkam.temperature.inposition:                # data collection until we reach temp2.
    # checks only once per USAXS/SAXS/WAXS cycle, basically once each 1-2 minutes
    # yield from collectAllThree(isDebugMode)             # USAXS, SAXS, WAXS data collection
    logger.info(f"reached {temp2} C")  # record we reached temp2

    t0 = time.time()  # set this moment as the start time of data collection.
    # by now are at temp1 and should hold for delay1min:
    checkpoint = (
        time.time() + delay2min * 60
    )  # calculate time to end ``delay1min`` hold period
    # this collects data for delay2min
    while (time.time() < checkpoint):  # collects USAXS/SAXS/WAXS data while holding at temp1
        yield from collectAllThree(isDebugMode)

    yield from change_rate_and_temperature(
        30, 25, wait=False
    )  # set rate & temp this cycle, wait=False contniues for data collection

    logger.info("finished")  # record end.

    if isDebugMode is not True:
        yield from after_command_list()  # runs standard after scan scripts.
