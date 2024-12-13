"""
BS plan to run infinte data collection same as spec used to do.

load this way:

     %run -im user.finite_loop

* file: /USAXS_data/bluesky_plans/finite_loop.py
* aka:  ~/.ipython/user/finite_loop.py

* JIL, 2022-11-17 : first release
"""

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

from bluesky import plan_stubs as bps
from instrument.plans import before_command_list, after_command_list
from instrument.plans import SAXS, USAXSscan, WAXS, preUSAXStune
from ophyd import Signal
import time

#define conversions from seconds
SECOND = 1
MINUTE = 60 * SECOND
HOUR = 60 * MINUTE
DAY = 24 * HOUR
WEEK = 7 * DAY

#debug mode switch, may not be that useful in our case...
loop_debug = Signal(name="loop_debug", value=False)
#   In order to run as debug (without collecting data, only run through loop) in command line run:
#loop_debug.put(True)

def myFiniteLoop(pos_X, pos_Y, thickness, scan_title, delay1minutes, md={}):
    """
    Will run finite loop 
    delay1minutes - delay is in minutes

    reload by
    # %run -im user.finite_loop
    """

    def setSampleName():
        return (
            f"{scan_title}"
            f"_{(time.time()-t0)/60:.0f}min"
        )

    def collectAllThree(debug=False):
        if debug:
            #for testing purposes, set debug=True
            print(sampleMod)
            yield from bps.sleep(20)
        else:
            sampleMod = setSampleName()
            md["title"]=sampleMod
            yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = setSampleName()
            md["title"]=sampleMod
            yield from SAXS(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = setSampleName()
            md["title"]=sampleMod
            yield from WAXS(pos_X, pos_Y, thickness, sampleMod, md={})

    isDebugMode = loop_debug.get()
    #isDebugMode = False

    if isDebugMode is not True:
        yield from before_command_list()                    #this will run usual startup scripts for scans

    t0 = time.time()                                        # mark start time of data collection.
 
    checkpoint = time.time() + delay1minutes*MINUTE         # time to end ``delay1min`` hold period

    logger.info("Collecting data for %s minutes", delay1minutes)

    while time.time() < checkpoint:                         # collects USAXS/SAXS/WAXS data while holding at temp1
        yield from collectAllThree(isDebugMode)

    logger.info("finished")                                 #record end.

    if isDebugMode is not True:
       yield from after_command_list()                      # runs standard after scan scripts.



def myFiniteListLoop(delay1minutes, md={}):
    """
    Will run finite loop for delay1minutes - delay is in minutes

    over list of positions and names
    
    reload by
    # %run -im user.finite_loop
    """
    #ListOfSamples = [[pos_X, pos_Y, thickness, scan_title],
    ListOfSamples = [[60, 100, 1.0, "OPC1"],
                     [80,  40, 1.0, "PLC1"],
                     [80,  160, 0, "Blank_CEM"],
                     [20, 80, 0.75, "sly2Top"],
                     [39.7, 80, 0.75, "sly1Top"],
                     [20, 100, 0.75, "sly2B"],
                     [39.8, 100, 0.75, "sly1B"],
                     [20.1, 120, 0.75, "sly2C"],
                     [40, 120, 0.75, "sly1C"],
                     [20.2, 140, 0.75, "sly2D"],
                     [40.2, 140, 0.75, "sly1D"],
                     [20.3, 160, 0.75, "sly2E"],
                     [40.4, 159, 0.75, "sly1E"],
                     [99.1, 180, 0, "CapBLANK"],
                     [80, 180, 0, "airBLANK"],
                     [59, 100, 1.0, "OPC2"],
                     [81,  40, 1.0, "PLC2"],
                     [80,  160, 0, "Blank_CEM"],
                     [20, 80, 0.75, "sly2Top"],
                     [39.7, 80, 0.75, "sly1Top"],
                     [20, 100, 0.75, "sly2B"],
                     [39.8, 100, 0.75, "sly1B"],
                     [20.1, 120, 0.75, "sly2C"],
                     [40, 120, 0.75, "sly1C"],
                     [20.2, 140, 0.75, "sly2D"],
                     [40.2, 140, 0.75, "sly1D"],
                     [20.3, 160, 0.75, "sly2E"],
                     [40.4, 159, 0.75, "sly1E"],
                     [99.1, 180, 0, "CapBLANK"],
                     [80, 180, 0, "airBLANK"],
                     [61, 100, 1.0, "OPC3"],
                     [80,  39, 1.0, "PLC3"],
                     [80,  161, 0, "Blank_CEM"],
                     [20, 80, 0.75, "sly2Top"],
                     [39.7, 80, 0.75, "sly1Top"],
                     [20, 100, 0.75, "sly2B"],
                     [39.8, 100, 0.75, "sly1B"],
                     [20.1, 120, 0.75, "sly2C"],
                     [40, 120, 0.75, "sly1C"],
                     [20.2, 140, 0.75, "sly2D"],
                     [40.2, 140, 0.75, "sly1D"],
                     [20.3, 160, 0.75, "sly2E"],
                     [40.4, 159, 0.75, "sly1E"],
                     [99.1, 180, 0, "CapBLANK"],
                     [80, 180, 0, "airBLANK"],
                     [60,  99, 1.0, "OPC4"],
                     [80,  38, 1.0, "PLC4"],
                     [80,  159, 0, "Blank_CEM"],
                     [20, 80, 0.75, "sly2Top"],
                     [39.7, 80, 0.75, "sly1Top"],
                     [20, 100, 0.75, "sly2B"],
                     [39.8, 100, 0.75, "sly1B"],
                     [20.1, 120, 0.75, "sly2C"],
                     [40, 120, 0.75, "sly1C"],
                     [20.2, 140, 0.75, "sly2D"],
                     [40.2, 140, 0.75, "sly1D"],
                     [20.3, 160, 0.75, "sly2E"],
                     [40.4, 159, 0.75, "sly1E"],
                     [99.1, 180, 0, "CapBLANK"],
                     [80, 180, 0, "airBLANK"],
                     [79,  160, 0, "Blank_CEM"],
                     [61, 98, 1.0, "OPC5"],
                     [81,  39, 1.0, "PLC5"],
                     [20, 80, 0.75, "sly2Top"],
                     [39.7, 80, 0.75, "sly1Top"],
                     [20, 100, 0.75, "sly2B"],
                     [39.8, 100, 0.75, "sly1B"],
                     [20.1, 120, 0.75, "sly2C"],
                     [40, 120, 0.75, "sly1C"],
                     [20.2, 140, 0.75, "sly2D"],
                     [40.2, 140, 0.75, "sly1D"],
                     [20.3, 160, 0.75, "sly2E"],
                     [40.4, 159, 0.75, "sly1E"],
                     [99.1, 180, 0, "CapBLANK"],
                     [80, 180, 0, "airBLANK"],
                     [59,  98, 1.0, "OPC6"],
                     [81,  40, 1.0, "PLC6"],
                     [80,  160, 0, "Blank_CEM"],
                     [20, 80, 0.75, "sly2Top"],
                     [39.7, 80, 0.75, "sly1Top"],
                     [20, 100, 0.75, "sly2B"],
                     [39.8, 100, 0.75, "sly1B"],
                     [20.1, 120, 0.75, "sly2C"],
                     [40, 120, 0.75, "sly1C"],
                     [20.2, 140, 0.75, "sly2D"],
                     [40.2, 140, 0.75, "sly1D"],
                     [20.3, 160, 0.75, "sly2E"],
                     [40.4, 159, 0.75, "sly1E"],
                     [99.1, 180, 0, "CapBLANK"],
                     [80, 180, 0, "airBLANK"],
                     ]

    def setSampleName(scan_titlePar):
        return (
            f"{scan_titlePar}"
            f"_{(time.time()-t0)/60:.0f}min"
        )

    def collectAllThree(debug=False):
        if debug:
            #for testing purposes, set debug=True
            for pos_X, pos_Y, thickness, sampleName in ListOfSamples:
                sampleMod = setSampleName(sampleName)
                print(sampleMod)
                print(pos_X)
                print(pos_Y)
                print(thickness)
                yield from bps.sleep(1)
        else:
            for pos_X, pos_Y, thickness, sampleName in ListOfSamples:
                sampleMod = setSampleName(sampleName)
                md["title"]=sampleMod
                yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
            
            for pos_X, pos_Y, thickness, sampleName in ListOfSamples:
                sampleMod = setSampleName(sampleName)
                md["title"]=sampleMod
                yield from SAXS(pos_X, pos_Y, thickness, sampleMod, md={})
            
            for pos_X, pos_Y, thickness, sampleName in ListOfSamples:
                sampleMod = setSampleName(sampleName)
                md["title"]=sampleMod
                yield from WAXS(pos_X, pos_Y, thickness, sampleMod, md={})

    isDebugMode = loop_debug.get()
    #isDebugMode = False

    if isDebugMode is not True:
        yield from before_command_list()                    #this will run usual startup scripts for scans

    t0 = time.time()                                        # mark start time of data collection.
 
    checkpoint = time.time() + delay1minutes*MINUTE         # time to end ``delay1min`` hold period

    logger.info("Collecting data for %s minutes", delay1minutes)

    while time.time() < checkpoint:                         # collects USAXS/SAXS/WAXS data while holding at temp1
        yield from collectAllThree(isDebugMode)

    logger.info("finished")                                 #record end.

    if isDebugMode is not True:
       yield from after_command_list()                      # runs standard after scan scripts.
