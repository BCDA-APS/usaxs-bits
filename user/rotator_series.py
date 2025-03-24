"""
BS plan to run basic series on the PI rotator stage
load this way:

     %run -im user.rotator_series

* file: /USAXS_data/bluesky_plans/rotator_series.py
* aka:  ~/.ipython/user/rotator_series.py

* JIL, 2022-11-17 : first release
* JIL, 2022-11-18 : added different modes
"""

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

from bluesky import plan_stubs as bps
from instrument.plans import before_command_list, after_command_list
from instrument.plans import SAXS, USAXSscan, WAXS, preUSAXStune
from ophyd import Signal
from epics import caput,caget
import numpy as np
import time

#define conversions from seconds
SECOND = 1
MINUTE = 60 * SECOND
HOUR = 60 * MINUTE
DAY = 24 * HOUR
WEEK = 7 * DAY

ROTATOR_POSITION_PV = "usxPI:c867:c0:m1.VAL"

#debug mode switch, may not be that useful in our case...
loop_debug = Signal(name="loop_debug", value=False)
#   In order to run as debug (without collecting data, only run through loop) in command line run:
#loop_debug.put(True)

def rel_angle_series(pos_X, pos_Y, thickness, scan_title, angles, md={}):
    """
    Will run a sequence of measurements at angles

    reload by
    # %run -im user.finite_loop
    
    run by 
    RE(myFiniteLoop(0, 0, 1, "Sample", 20))
    """

    def setSampleName(angle):
        return (
            f"{scan_title}"
            f"_{angle}deg"
        )

    def collectAllThree(angle,debug=False):
        if debug:
            #for testing purposes, set debug=True
            print(sampleMod)
            yield from bps.sleep(20)
        else:
            sampleMod = setSampleName(angle)
            md["title"]=sampleMod
            yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
            #sampleMod = setSampleName()
            #md["title"]=sampleMod
            #yield from SAXS(pos_X, pos_Y, thickness, sampleMod, md={})
            #sampleMod = setSampleName()
            #md["title"]=sampleMod
            #yield from WAXS(pos_X, pos_Y, thickness, sampleMod, md={})

    isDebugMode = loop_debug.get()
    #isDebugMode = False

    if isDebugMode is not True:
        yield from before_command_list()                    #this will run usual startup scripts for scans

    rotator_current = caget(ROTATOR_POSITION_PV)

    rotator_positions = np.array(angles) + rotator_current
    for pos in rotator_positions:
        caput(ROTATOR_POSITION_PV,pos,wait=True)
        yield from bps.sleep(10)
        yield from collectAllThree(pos,isDebugMode)
    caput(ROTATOR_POSITION_PV,rotator_current)
    logger.info("finished")                                 #record end.

    if isDebugMode is not True:
       yield from after_command_list()                      # runs standard after scan scripts.


