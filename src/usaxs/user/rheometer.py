"""
BS plan to run infinte data collection same as spec used to do.

load this way:

     %run -im usaxs.user.rheometer

* file: /USAXS_data/bluesky_plans/finite_loop.py
* aka:  ~/.ipython/user/finite_loop.py

* JIL, 2022-11-17 : first release
* JIL, 2022-11-18 : added different modes
* JIL, 2025-5-28 : fixs for BITS
* JIL, 7/9/2025 user changes
"""

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

import time

from bluesky import plan_stubs as bps
from usaxs.plans.plans_user_facing import saxsExp
from usaxs.plans.plans_user_facing import waxsExp
from usaxs.plans.plans_usaxs import USAXSscan
from usaxs.plans.plans_tune import preUSAXStune
from usaxs.plans.command_list import after_command_list, sync_order_numbers
from usaxs.plans.command_list import before_command_list
from ophyd import Signal
from usaxs.utils.obsidian import appendToMdFile, recordFunctionRun
from epics import caput
from ophyd import Component, Device, EpicsSignal, EpicsMotor, EpicsSignalRO


# define conversions from seconds
SECOND = 1
MINUTE = 60 * SECOND
HOUR = 60 * MINUTE
DAY = 24 * HOUR
WEEK = 7 * DAY

# debug mode switch, may not be that useful in our case...
loop_debug = Signal(name="loop_debug", value=False)
#   In order to run as debug (without collecting data, only run through loop) in command line run:
# loop_debug.put(True)

galil_voltage = EpicsSignal("usxRIO:GalilAo1_SP.VAL",name="galil_voltage")  


def rheoLoop(scan_title, delay1minutes, md={}):
    """
    Will run finite loop
    delay1minutes - delay is in minutes

    reload by
    # %run -im usaxs.user.finite_loop

    run by
    RE(myFiniteLoop(0, 0, 1, "Sample", 20))
    """
    pos_X =0
    pos_Y =0  
    thickness = 1.0
    
    def setSampleName():
        return f"{scan_title}" f"_{((time.time()-t0)/60):.0f}min"

    def collectAllThree():
            yield from bps.mv(galil_voltage,5)
            yield from sync_order_numbers()
            yield from preUSAXStune()
            sampleMod = setSampleName()
            md["title"] = sampleMod
            yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
            #sampleMod = setSampleName()
            md["title"]=sampleMod
            yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
            # sampleMod = setSampleName()
            # md["title"]=sampleMod
            # yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
            yield from bps.mv(galil_voltage,0)
            yield from bps.sleep(1)

    
    yield from before_command_list()  # this will run usual startup scripts for scans
    # here goes user stuff

    t0 = time.time()  # mark start time of data collection.
    
    checkpoint = (
        time.time() + delay1minutes * MINUTE
    )  # time to end ``delay1min`` hold period

    logger.info("Collecting data for %s minutes", delay1minutes)
    appendToMdFile(f"Measuring sample {scan_title} for {delay1minutes} minutes")

    while (time.time() < checkpoint):  
        # collects USAXS/SAXS data while holding at temp1
        yield from collectAllThree()

    logger.info("finished")  # record end.
    
    
    
    #end of user stuff above
    yield from after_command_list()  # runs standard after scan scripts.

