"""
Linkam plan for James Coakley experiments 2021-01.

Load this into a bluesky console session with::

    %run -i -m james_linkam

Note:
Use option is "-i -m" and no trailing ".py".  Loads as
a *module*.  The directory is already on the search path.
"""

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)


import time

from bluesky import plan_stubs as bps
from instrument.devices import linkam_ci94
from instrument.plans import SAXS
from instrument.plans import WAXS
from instrument.plans import USAXSscan
from instrument.plans import after_command_list
from instrument.plans import before_command_list
from instrument.plans import sync_order_numbers
from instrument.plans.command_list import *
from instrument.utils import resetSampleTitleFunction
from instrument.utils import setSampleTitleFunction
from usaxs_support.surveillance import instrument_archive

# NOTE NOTE NOTE NOTE NOTE NOTE
# this plan's name is custom!
# NOTE NOTE NOTE NOTE NOTE NOTE


def jamesLinkamPlan(pos_X, pos_Y, thickness, scan_title, md={}):
    """
    collect RT USAXS/SAXS/WAXS
    change temperature T to temp1 with rate1
    collect USAXS/SAXS/WAXS while heating

    reload by
    # %run -i -m linkam
    """

    def myTitleFunction(title):
        return f"{title}_{linkam.value:.0f}C_{(time.time()-t1)/60:.0f}min"

    def collectAllThree(debug=False):
        if debug:
            # for testing purposes, set debug=True
            sampleMod = myTitleFunction(scan_title)
            print(sampleMod)
            yield from bps.sleep(20)
        else:
            yield from USAXSscan(pos_X, pos_Y, thickness, scan_title, md={})
            yield from SAXS(pos_X, pos_Y, thickness, scan_title, md={})
            yield from WAXS(pos_X, pos_Y, thickness, scan_title, md={})

    summary = (
        "Linkam USAXS/SAXS/WAXS heating sequence\n"
        f"james_LinkamPlan(pos_X={pos_X}, pos_Y={pos_Y},thickness={thickness},"
        f"sample_name={scan_title}"
    )
    instrument_archive(summary)

    setSampleTitleFunction(myTitleFunction)
    yield from sync_order_numbers()  # resync order numbers since we run only SAXs above.

    # Linkam device choice
    # linkam = linkam_tc1     # Linkam T96, 600, 1500V, 350V
    linkam = linkam_ci94  # Linkam 1500 using old controller.
    logger.info(f"Linkam controller PV prefix={linkam.prefix}")
    # this runs start of scan code...
    yield from before_command_list(md={})

    # Room temp measurement 30C
    t0 = time.time()
    t1 = time.time()
    yield from bps.mv(linkam.rate, 150)  # sets the rate of next ramp
    yield from linkam.set_target(30, wait=False)  # sets the temp of next ramp
    # TODO here: start Linkam somehow, if it is off, it stays off...
    yield from collectAllThree()
    # yield from mode_USAXS()

    # Heat to 560C @150C/min. Measure at 550C one USAXS/SAXS/WAXS.
    logger.info(f"Ramping temperature to {566} C")
    yield from bps.mv(linkam.rate, 150)  # sets the rate of next ramp
    yield from linkam.set_target(566, wait=False)  # sets the temp of next ramp
    while not linkam.settled:  # runs data collection until next temp
        yield from bps.sleep(2)  # sleep until settled
    t0 = time.time()
    t1 = time.time()
    yield from collectAllThree()  # measure at 250C

    # Heat to 1060C @ 150C/min with 1 USAXS/SAXS/WAXS measurement, then wait to achieve temp
    # Hold at 1060C/20 minutes (solutionize). Measure USAXS/SAXS/WAXS
    yield from bps.mv(linkam.rate, 150)  # sets the rate of next ramp
    yield from linkam.set_target(1170, wait=False)  # temp measuremnt
    t1 = time.time()
    logger.info(f"Ramping temperature to {1170} C")
    yield from collectAllThree()  # measure on heating
    while not linkam.settled:  # runs data collection until next temp
        yield from bps.sleep(2)  # sleep until settled
    t0 = time.time()
    t1 = time.time()
    # this is solutionize.
    logger.info(f"Solutionize at temperature {1170} C")
    while time.time() - t0 < 20 * 60:  # collects data for 20 minutes
        yield from collectAllThree()
    # done with solutionize
    # Cool at 20 C/min to 566C, with continuous in-situ SAXS ONLY
    yield from bps.mv(linkam.rate, 20)  # sets the rate of next ramp
    yield from linkam.set_target(566, wait=False)  # temp measuremnt
    t1 = time.time()
    logger.info(f"Cooling at 20deg/C temperature to {566} C")
    while not linkam.settled:  # runs data collection until next temp
        yield from SAXS(pos_X, pos_Y, thickness, scan_title, md={})

    yield from sync_order_numbers()  # resync order numbers since we run only SAXs above.
    yield from collectAllThree()

    for rate in (20, 10, 5, 2):
        # Heat to 1060C @ 150C/min with 1 USAXS/SAXS/WAXS measurement, then wait to achieve temp
        # Hold at 1060C/20 minutes (solutionize). Measure USAXS/SAXS/WAXS
        yield from bps.mv(linkam.rate, 150)  # sets the rate of next ramp
        yield from linkam.set_target(1170, wait=False)  # set temperature
        t1 = time.time()
        logger.info(f"Ramping temperature to {1170} C")
        yield from collectAllThree()  # measure while ramping to 1060C
        while not linkam.settled:  # runs data collection until next temp
            yield from bps.sleep(2)  # sleep until settled
        t0 = time.time()
        t1 = time.time()
        # this is solutionize.
        logger.info(f"Solutionize at temperature {1170} C")
        while time.time() - t0 < 20 * 60:  # collects data for 20 minutes
            yield from collectAllThree()
        # Cool at rate C/min to 560C, with continuous data collection
        yield from bps.mv(linkam.rate, rate)  # sets the rate of next ramp
        yield from linkam.set_target(566, wait=False)  # temp measuremnt
        t1 = time.time()
        logger.info(f"Cooling at {rate} deg/C temperature to {566} C")
        while not linkam.settled:  # runs data collection until next temp
            yield from collectAllThree()

        yield from collectAllThree()  # last scan at 560C

    # now the annealing at different tremperatuers
    for temp in (772, 830, 889, 950):
        # Heat to 1060C @ 150C/min with 1 USAXS/SAXS/WAXS measurement, then wait to achieve temp
        # Hold at 1060C/20 minutes (solutionize). Measure USAXS/SAXS/WAXS
        yield from bps.mv(linkam.rate, 150)  # sets the rate of next ramp
        yield from linkam.set_target(1170, wait=False)  # set temperature
        t1 = time.time()
        logger.info(f"Ramping temperature to {1170} C")
        yield from collectAllThree()  # measure while ramping to 1060C
        while not linkam.settled:  # runs data collection until next temp
            yield from bps.sleep(2)  # sleep until settled
        t0 = time.time()
        t1 = time.time()
        # this is solutionize.
        logger.info(f"Solutionize at temperature {1170} C")
        while time.time() - t0 < 20 * 60:  # collects data for 20 minutes
            yield from collectAllThree()
        # Cool at 20 C/min to 560C, with continuous data collection
        yield from bps.mv(linkam.rate, 20)  # sets the rate of next ramp
        yield from linkam.set_target(566, wait=False)  # temp measuremnt
        t1 = time.time()
        logger.info(f"Cooling at {20} deg/C temperature to {566} C")
        while not linkam.settled:  # runs data collection until next temp
            yield from collectAllThree()

        yield from collectAllThree()  # last scan at 560C
        ## one temp block...
        yield from bps.mv(linkam.rate, 150)  # sets the rate of next ramp
        yield from linkam.set_target(temp, wait=False)  # temp measuremnt
        t1 = time.time()
        logger.info(f"Ramping temperature to {temp} C")
        while not linkam.settled:  # runs data collection until next temp
            yield from bps.sleep(2)  # sleep until settled
        t0 = time.time()
        t1 = time.time()
        # this is main loop where we collect data at temperature temp.
        while time.time() - t0 < 2 * 60 * 60:  # collects data for 2 hours
            yield from collectAllThree()

    # done with main loop, we will cool next.
    t0 = time.time()
    t1 = time.time()
    yield from linkam.set_target(50, wait=False)  # sets the temp of next ramp

    # collecting data on cooling
    while not linkam.settled:  # runs data collection until next temp
        yield from collectAllThree()

    logger.info(f"reached {50} C")

    # cooling finished, get one more data set at final temperature.
    yield from collectAllThree()

    # run endof scan code.
    yield from after_command_list()

    resetSampleTitleFunction()

    # done...
    logger.info("finished")
