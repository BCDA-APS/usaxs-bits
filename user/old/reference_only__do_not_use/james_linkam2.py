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
from instrument.plans import preUSAXStune
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

    # Heat to 400 @150C/min. Measure at 400C one USAXS/SAXS/WAXS.
    logger.info(f"Ramping temperature to {400} C")
    yield from bps.mv(linkam.rate, 150)  # sets the rate of next ramp
    yield from linkam.set_target(400, wait=False)  # sets the temp of next ramp
    yield from preUSAXStune()
    while not linkam.settled:  # runs data collection until next temp
        yield from bps.sleep(2)  # sleep until settled
    t0 = time.time()
    t1 = time.time()
    yield from collectAllThree()  # measure at 400C

    # “Resetting the sample” from initial condition, precipitation of fine gamma-prime

    #  Heat to 1060C at 10C/min. Recording SAXS/WAXS/USAXS [60 minutes]
    yield from bps.mv(linkam.rate, 10)  # sets the rate of next ramp
    yield from linkam.set_target(1170, wait=False)  # temp measuremnt
    t0 = time.time()
    t1 = time.time()
    logger.info(f"Ramping temperature to {1170} C")
    while not linkam.settled:  # runs data collection until next temp
        yield from collectAllThree()

    #  Hold at 1060C for 30min. Recording SAXS only [30 minutes]
    logger.info(f"Hold at temperature {1170} C")
    t0 = time.time()
    t1 = time.time()
    while time.time() - t0 < 30 * 60:  # collects data for 30 minutes
        yield from SAXS(pos_X, pos_Y, thickness, scan_title, md={})

    yield from sync_order_numbers()  # resync order numbers since we run only SAXs above.

    # Cool to 400C at 20C/min. Recording SAXS only [30 minutes]
    yield from bps.mv(linkam.rate, 20)  # sets the rate of next ramp
    yield from linkam.set_target(400, wait=False)  # temp measuremnt
    t0 = time.time()
    t1 = time.time()
    logger.info(f"Cooling temperature to {400} C")
    while not linkam.settled:  # runs data collection until next temp
        yield from SAXS(pos_X, pos_Y, thickness, scan_title, md={})

    yield from sync_order_numbers()  # resync order numbers since we run only SAXs above.

    #  USAXS/SAXS/WAXS one measurement at 400C
    yield from collectAllThree()

    # Coarsening kinetics

    #  Heat to 750C at 10C/min. Recording USAXS/SAXS/WAXS [30 minutes]
    yield from bps.mv(linkam.rate, 10)  # sets the rate of next ramp
    yield from linkam.set_target(772, wait=False)  # temp measuremnt
    t0 = time.time()
    t1 = time.time()
    logger.info(f"Ramping temperature to {750} C")
    while not linkam.settled:  # runs data collection until next temp
        yield from collectAllThree()

    #  Hold at 750 C for 5 hours, USAXS/SAXS/WAXS [300 minutes]
    logger.info(f"Hold at temperature {750} C")
    t0 = time.time()
    t1 = time.time()
    while time.time() - t0 < 5 * 60 * 60:  # collects data for 5 hours minutes
        yield from collectAllThree()

    #  Heat to 1060C at 10C/min. Recording USAXS/SAXS/WAXS [30 minutes]
    yield from bps.mv(linkam.rate, 10)  # sets the rate of next ramp
    yield from linkam.set_target(1170, wait=False)  # temp measuremnt
    t0 = time.time()
    t1 = time.time()
    logger.info(f"Ramping temperature to {1170} C")
    while not linkam.settled:  # runs data collection until next temp
        yield from collectAllThree()

    #  Hold at 1060C for 30mins. Recording SAXS only [30 minutes]
    logger.info(f"Hold at temperature {1170} C")
    t0 = time.time()
    t1 = time.time()
    while time.time() - t0 < 30 * 60:  # collects data for 30 minutes
        yield from SAXS(pos_X, pos_Y, thickness, scan_title, md={})

    yield from sync_order_numbers()  # resync order numbers since we run only SAXs above.

    #  Cool to 400C at 20C/min. Recording USAXS only [30 minutes]
    yield from bps.mv(linkam.rate, 20)  # sets the rate of next ramp
    yield from linkam.set_target(400, wait=False)  # temp measuremnt
    t0 = time.time()
    t1 = time.time()
    logger.info(f"Cooling temperature to {400} C")
    while not linkam.settled:  # runs data collection until next temp
        yield from USAXSscan(pos_X, pos_Y, thickness, scan_title, md={})

    yield from sync_order_numbers()  # resync order numbers since we run only SAXs above.

    #  Heat to 850C at 10C/min. Recording USAXS/SAXS/WAXS [40 minutes]
    yield from bps.mv(linkam.rate, 10)  # sets the rate of next ramp
    yield from linkam.set_target(889, wait=False)  # temp measuremnt
    t0 = time.time()
    t1 = time.time()
    logger.info(f"Ramping temperature to {850} C")
    while not linkam.settled:  # runs data collection until next temp
        yield from collectAllThree()

    #  Hold at 850 C for 4 hours, USAXS/SAXS/WAXS [240 minutes]
    logger.info(f"Hold at temperature {850} C")
    t0 = time.time()
    t1 = time.time()
    while time.time() - t0 < 4 * 60 * 60:  # collects data for 5 hours minutes
        yield from collectAllThree()

    #  Cool to 400C at 20C/min. Recording SAXS only [20 minutes]
    yield from bps.mv(linkam.rate, 20)  # sets the rate of next ramp
    yield from linkam.set_target(400, wait=False)  # temp measuremnt
    t0 = time.time()
    t1 = time.time()
    logger.info(f"Cooling temperature to {400} C")
    while not linkam.settled:  # runs data collection until next temp
        yield from SAXS(pos_X, pos_Y, thickness, scan_title, md={})

    yield from sync_order_numbers()  # resync order numbers since we run only SAXs above.

    #  Cool to RT at 150C/min.
    yield from bps.mv(linkam.rate, 150)  # sets the rate of next ramp
    yield from linkam.set_target(40, wait=False)  # temp measuremnt

    # done with main loop, we will cool next.
    t0 = time.time()
    t1 = time.time()

    # collecting data on cooling
    while not linkam.settled:  # runs data collection until next temp
        yield from collectAllThree()

    logger.info(f"reached {40} C")

    # cooling finished, get one more data set at final temperature.
    yield from collectAllThree()

    # run endof scan code.
    yield from after_command_list()

    resetSampleTitleFunction()

    # done...
    logger.info("finished")
