"""
BS plan to run infinte data collection same as spec used to do.

load this way:

     %run -im usaxs.user.jun_loop

    Then execute as :
    RE(junFiniteMultiPosLoop(delay1minutes))

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
from usaxs.plans.command_list import after_command_list
from usaxs.plans.command_list import before_command_list
from ophyd import Signal

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


def junFiniteMultiPosLoop(delay1minutes, md={}):
    """
    Will run finite loop for delay1minutes - delay is in minutes
    Runs over list of positions on each sample
    USAXS-SAXS-WAXS on pos1, then on pos2, etc until returns and starts from beggining

    over list of positions and names
    1. Correct the ListOfSamples
    2. reload by
    %run -im usaxs.user.jun_loop
    3. run:
    RE(junFiniteMultiPosLoop(20))   #will iterate over teh list for 20 minutes

    """
    # ListOfSamples = [[pos_X, pos_Y, thickness, scan_title],
    ListOfSamples = [
    
        [15, 58, 4.0, "water_blank"],  	                    # Point1
        [25, 58, 4.0, "Z_15mgmL_DPEG_1p5mgmL_36hr"],  		# Point2
        [35, 58, 4.0, "Z_15mgmL_DPEG_3mgmL_36hr"], 	        # Point3
        [45, 58, 4.0, "Z_15mgmL_DPEG_4p5mgmL_36hr"], 		# Point4
        [55, 58, 4.0, "Z_15mgmL_DPEG_6gmL_36hr"], 	        # Point5
        [65, 58, 4.0, "Z_15mgmL_DPEG_6p75mgmL_36hr"], 	    # Point6
        [75, 58, 4.0, "Z_15mgmL_DPEG_7p5mgmL_36hr"], 	    # Point7
        [85, 58, 4.0, "Z_15mgmL_DPEG_3mgmL_47C_14hr"], 	    # Point8
        [95, 58, 4.0, "Z_15mgmL_DPEG_4p5mgmL_47C_14hr"], 	# Point9
        [105, 58, 4.0, "Z_15mgmL_DPEG_6p75mgmL_47C_14hr"], 	# Point10
        [115, 58, 4.0, "Z_15mgmL_DPEG_50mgmL_14hr"], 	    # Point11
	
    ]

    # ListOfSamples = [[ 66.4, 20, 4.0, "H3S2H"],	#tube 4
    #                 ]

    def setSampleName():
        return f"{scan_title}" f"_{(time.time()-t0)/60:.0f}min"

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

    yield from before_command_list()  # this will run usual startup scripts for scans

    t0 = time.time()  # mark start time of data collection.

    checkpoint = (
        time.time() + delay1minutes * MINUTE
    )  # time to end ``delay1min`` hold period

    logger.info("Collecting data for %s minutes", delay1minutes)

    while (
        time.time() < checkpoint
    ):  # collects USAXS/SAXS/WAXS data while holding at temp1
        for pos_X, pos_Y, thickness, scan_title in ListOfSamples:
            yield from collectAllThree()

    logger.info("finished")  # record end.

    yield from after_command_list()  # runs standard after scan scripts.


def myFiniteListLoop(delay1minutes, StartTime, md={}):
    """
    Will run finite loop for delay1minutes - delay is in minutes
    over list of positions and names
    Runs all USAXS, then all SAXS, and then all WAXS
    1. Correct the ListOfSamples
    2. reload by
    %run -im user.finite_loop
    3. run:
    RE(myFiniteListLoop(20))

    """
    # ListOfSamples = [[pos_X, pos_Y, thickness, scan_title],
    ListOfSamples = [
        [100, 160, 1.0, "BlankLE"],  # tube 4
        [139, 100.6, 0.686, "RbCl6mLE"],  # tube 3
        [139, 160.3, 0.658, "NaCl6mLE"],  # tube 2
        [179.6, 100.6, 0.684, "BoehRbCl6mLE"],  # tube 1
        [178.8, 161.0, 0.654, "BoehNaCl6mLE"],  # tube 1
    ]

    # ListOfSamples = [[ 66.4, 20, 4.0, "H3S2H"],	#tube 4
    #                 ]

    def setSampleName(scan_titlePar):
        # return f"{scan_titlePar}" f"_{(time.time()-t0+(StartTime*60))/60:.0f}min"
        return f"{scan_titlePar}" f"_{counter}"

    def collectAllThree():
        for pos_X, pos_Y, thickness, sampleName in ListOfSamples:
            sampleMod = setSampleName(sampleName)
            md["title"] = sampleMod
            yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})

        for pos_X, pos_Y, thickness, sampleName in ListOfSamples:
            sampleMod = setSampleName(sampleName)
            md["title"] = sampleMod
            yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

        for pos_X, pos_Y, thickness, sampleName in ListOfSamples:
            sampleMod = setSampleName(sampleName)
            md["title"] = sampleMod
            yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    yield from before_command_list()  # this will run usual startup scripts for scans

    t0 = time.time()  # mark start time of data collection.

    counter = 0

    checkpoint = (
        time.time() + delay1minutes * MINUTE
    )  # time to end ``delay1min`` hold period

    logger.info("Collecting data for %s minutes", delay1minutes)

    while (
        time.time() < checkpoint
    ):  # collects USAXS/SAXS/WAXS data while holding at temp1
        yield from collectAllThree()
        counter += 1

    logger.info("finished")  # record end.

    yield from after_command_list()  # runs standard after scan scripts.
