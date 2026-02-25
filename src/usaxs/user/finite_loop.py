"""
BS plan to run infinte data collection same as spec used to do.

load this way:

     %run -im usaxs.user.finite_loop

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
from usaxs.plans.command_list import after_command_list, sync_order_numbers
from usaxs.plans.command_list import before_command_list
from ophyd import Signal
from usaxs.utils.obsidian import recordFunctionRun

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


def larryLoop(numIterattions, yOffset, md={}):
    """
    Will run loop for number of iterations with yOffset shift in y
    Runs over list of positions 
    USAXS-SAXS-WAXS on pos1, then on pos2, etc until returns and starts from beggining

    over list of positions and names
    1. Correct the ListOfSamples
    2. reload by
    %run -im usaxs.user.finite_loop
    3. run:
    RE(larryLoop(50,0.06)) which will run 50 iterations with 0.06 yOffset =3mm total shift
    keep in mind that last y position is y0+20*0.1 - you moved each sample up by total 2mm
    yofset = totalYmotion/numItenrations
    """
    # ListOfSamples = [[pos_X, pos_Y, thickness, scan_title],
    ListOfSamples = [
        [42.9,  19.8, 0.48, "NaCl6m_LE"],  	    # Point1
        [43.9,  48.2, 0.48, "RbCl6m_LE"],  	    # Point1
        [44.9,  76.7, 0.48, "NaNO3p5m_LE"],  	    # Point1
        [43.3, 105.1, 0.48, "RbNO3p5m_LE"],  	    # Point1
        [89.0,  23.6, 0.48, "BoeNaCl6m_LE"],  		# Point2
        [89.0,  50.4, 0.48, "BoeRbCl6m_LE"],  		# Point2
        [88.8,  78.4, 0.48, "BoeNaNO3p5m_LE"],  	    # Point1
        [89.0, 105.8, 0.48, "BoeRbNO3p5m_LE"],  	    # Point1
    ]

    # ListOfSamples = [[ 66.4, 20, 4.0, "H3S2H"],	#tube 4
    #                 ]

    def setSampleName():
        return f"{scan_title}" f"_{i}"

    def collectAllThree(debug=False):
        if debug:
            # for testing purposes, set debug=True
            print(sampleMod)
            yield from bps.sleep(20)
        else:
            yield from sync_order_numbers()
            sampleMod = setSampleName()
            md["title"] = sampleMod
            yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = setSampleName()
            md["title"] = sampleMod
            yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = setSampleName()
            md["title"] = sampleMod
            yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    isDebugMode = loop_debug.get()
    #isDebugMode = False

    if isDebugMode is not True:
        yield from before_command_list()  # this will run usual startup scripts for scans

    t0 = time.time()  # mark start time of data collection.

    for i in range(numIterattions):
        logger.info("Starting iteration %s", i+1)

        for pos_X, pos_Yo, thickness, scan_title in ListOfSamples:
            pos_Y = pos_Yo + i * yOffset
            yield from collectAllThree(isDebugMode)

    logger.info("finished")  # record end.

    if isDebugMode is not True:
        yield from after_command_list()  # runs standard after scan scripts.


def myFiniteLoop(pos_X, pos_Y, thickness, scan_title, delay1minutes, md={}):
    """
    Will run finite loop
    delay1minutes - delay is in minutes

    reload by
    # %run -im usaxs.user.finite_loop

    run by
    RE(myFiniteLoop(0, 0, 1, "Sample", 20))
    """

    def setSampleName():
        return f"{scan_title}" f"_{((time.time()-t0)/60):.0f}min"

    def collectAllThree(debug=False):
        if debug:
            # for testing purposes, set debug=True
            print(sampleMod)
            yield from bps.sleep(20)
        else:
            yield from sync_order_numbers()
            sampleMod = setSampleName()
            md["title"] = sampleMod
            yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
            #sampleMod = setSampleName()
            md["title"]=sampleMod
            yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
            # sampleMod = setSampleName()
            # md["title"]=sampleMod
            # yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    isDebugMode = loop_debug.get()
    # isDebugMode = False

    if isDebugMode is not True:
        yield from before_command_list()  # this will run usual startup scripts for scans

    t0 = time.time()  # mark start time of data collection.

    checkpoint = (
        time.time() + delay1minutes * MINUTE
    )  # time to end ``delay1min`` hold period

    logger.info("Collecting data for %s minutes", delay1minutes)

    while (time.time() < checkpoint):  
        # collects USAXS/SAXS/WAXS data while holding at temp1
        yield from collectAllThree(isDebugMode)

    logger.info("finished")  # record end.

    if isDebugMode is not True:
        yield from after_command_list()  # runs standard after scan scripts.


def myTwoPosFiniteLoop(pos_XA,thicknessA, scan_titleA, pos_XB, thicknessB, scan_titleB, delay1minutes, md={}):
    """
    Will run finite loop at two positions in alternance using LAXm2 motor
    delay1minutes - delay is in minutes
    pos_XA and pos_XB are in mm - these are SAMX satge positions
    thicknessA and thicknessB are in mm

    reload by
    # %run -im usaxs.user.finite_loop

    run by
    RE(myTwoPosFiniteLoop(0, 1,"SampleA", 5, 2, "SampleB", 20))
    will run data collection at SAMX = 0 with thickness 1mm and sample name SampleA
    then at SAMX = 5 and thickness 2mm with SampleB name
    and will alternate between these two for delay1minutes time
    """
    from apsbits.core.instrument_init import oregistry
    samx = oregistry["LAXm2"]

    def setSampleName():
        return f"{scan_title}" f"_{((time.time()-t0)/60):.0f}min"

    def collectAllThree(debug=False):
        if debug:
            # for testing purposes, set debug=True
            print(sampleMod)
            yield from bps.sleep(20)
        else:
            yield from sync_order_numbers()
            sampleMod = setSampleName()
            md["title"] = sampleMod
            yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
            #sampleMod = setSampleName()
            md["title"]=sampleMod
            yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
            # sampleMod = setSampleName()
            # md["title"]=sampleMod
            # yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    isDebugMode = loop_debug.get()
    # isDebugMode = False

    if isDebugMode is not True:
        yield from before_command_list()  # this will run usual startup scripts for scans

    t0 = time.time()  # mark start time of data collection.

    checkpoint = (
        time.time() + delay1minutes * MINUTE
    )  # time to end ``delay1min`` hold period

    logger.info("Collecting data for %s minutes", delay1minutes)

    pos_X=0
    pos_Y=0
    
    while (time.time() < checkpoint):  
        # collects USAXS/SAXS/WAXS data while holding at temp1
        thickness=thicknessA
        scan_title = scan_titleA
        yield from bps.mv(samx, pos_XA) 
        yield from collectAllThree(isDebugMode)
        thickness=thicknessB
        scan_title = scan_titleB
        yield from bps.mv(samx, pos_XB) 
        yield from collectAllThree(isDebugMode)

    logger.info("finished")  # record end.

    if isDebugMode is not True:
        yield from after_command_list()  # runs standard after scan scripts.


def myFiniteMultiPosLoop(delay1minutes, md={}):
    """
    Will run finite loop for delay1minutes - delay is in minutes
    Runs over list of positions on one sample
    USAXS-SAXS-WAXS on pos1, then on pos2, etc until returns and starts from beggining

    over list of positions and names
    1. Correct the ListOfSamples
    2. reload by
    %run -im usaxs.user.finite_loop
    3. run:
    RE(myFiniteListLoop(20))

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

    def collectAllThree(debug=False):
        if debug:
            # for testing purposes, set debug=True
            print(sampleMod)
            yield from bps.sleep(20)
        else:
            yield from sync_order_numbers()
            sampleMod = setSampleName()
            md["title"] = sampleMod
            yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = setSampleName()
            md["title"] = sampleMod
            yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = setSampleName()
            md["title"] = sampleMod
            yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    isDebugMode = loop_debug.get()
    # isDebugMode = False

    if isDebugMode is not True:
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
            yield from collectAllThree(isDebugMode)

    logger.info("finished")  # record end.

    if isDebugMode is not True:
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

    def collectAllThree(debug=False):
        if debug:
            # for testing purposes, set debug=True
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

    isDebugMode = loop_debug.get()
    # isDebugMode = False

    if isDebugMode is not True:
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
        yield from collectAllThree(isDebugMode)
        counter += 1

    logger.info("finished")  # record end.

    if isDebugMode is not True:
        yield from after_command_list()  # runs standard after scan scripts.
