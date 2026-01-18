"""
this is a PTC10 plan
reload by
...:  %run -im usaxs.user.ptc10_planG

* 2025-6-7 : JIL user modifications
** add appendToMdFile calls to log temperature changes - not done yet. 
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
from usaxs.plans.command_list import after_command_list
from usaxs.plans.command_list import before_command_list
from usaxs.utils.obsidian import appendToMdFile

ptc10 = oregistry["ptc10"]

ptc10_debug = Signal(name="ptc10_debug", value=False)
#   In order to run as debug (without collecting data, only control Linkam) in command line run:
# ptc10_debug.put(True)
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


def myPTC10Plan(
    pos_X, pos_Y, thickness, scan_title, temp1, rate1, delay1min, md={}
):
    """
    collect RT USAXS/SAXS/WAXS - or not, change code
    change temperature T to temp1 with rate1
    do not collect USAXS/SAXS/WAXS while heating or sleep= change code...
    when temp1 reached, hold for delay1min minutes, collecting data repeatedly
    switch off heater
    collect USAXS/SAXS/WAXS while changing temp to RT
    and it will end here...

    reload by
    # %run -im usaxs.user.ptc10_planG
    """

    def getSampleName():
        """
        return the name of the sample
        """
        return f"{scan_title}_{ptc10.position:.0f}C_{(time.time()-t1)/60:.0f}min"

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
            md["title"] = sampleMod
            yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = getSampleName()
            md["title"] = sampleMod
            yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = getSampleName()
            md["title"] = sampleMod
            yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})


    yield from before_command_list()  # this will run usual startup scripts for scans
    t1 = time.time()
    yield from collectAllThree()  # collect RT data

    yield from bps.mv(
        ptc10.ramp, rate1 / 60.0
    )  # user wants C/min, controller wants C/s
    yield from bps.mv(
        ptc10.temperature.setpoint, temp1
    )  # Change the temperature and not wait
    yield from setheaterOn()

    logger.info(f"Ramping temperature to {temp1} C")

    while (
        not ptc10.temperature.inposition
    ):  # runs data collection until next temp or sleeps. Change as needed.
        yield from bps.sleep(5)
 
    # logger.info("Reached temperature, now collecting data for %s minutes", delay1min)
    logger.info("Reached temperature, now collecting data for %s minutes", delay1min)
    t1 = time.time()

    while time.time() - t1 < delay1min*60:  # collects data for delay1min*60 seconds
        # yield from bps.sleep(5)
        logger.info("Collecting data for %s ", delay1min)
        yield from collectAllThree()

    logger.info("waited for %s seconds, now swithing off heater", delay1min*60)
    
    yield from setheaterOff()

    while ptc10.position > 40:
        logger.info("Collecting data until cold ")
        yield from collectAllThree()


    yield from after_command_list()  # runs standard after scan scripts.

    logger.info("finished")

