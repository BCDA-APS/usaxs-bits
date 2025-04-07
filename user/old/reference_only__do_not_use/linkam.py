# this is a Linkam plan

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)


import time

from bluesky import plan_stubs as bps
from instrument.devices import linkam_ci94
from instrument.plans import SAXS
from instrument.plans import WAXS
from instrument.plans import USAXSscan


def myLinkamPlan(
    pos_X, pos_Y, thickness, scan_title, temp1, rate1, delay1, temp2, rate2, md={}
):
    """
    collect RT USAXS/SAXS/WAXS
    change temperature T to temp1 with rate1
    collect USAXS/SAXS/WAXS while heating
    when temp1 reached, hold for delay1 seconds, collecting data repeatedly
    change T to temp2 with rate2
    collect USAXS/SAXS/WAXS while heating
    when temp2 reached, hold for delay2 seconds, collecting data repeatedly
    collect final data
    and it will end here...

    reload by
    # %run -m linkam
    """

    def setSampleName():
        return f"{scan_title}_{linkam.value:.0f}C_{(time.time()-t0)/60:.0f}min"

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
            yield from SAXS(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = setSampleName()
            md["title"] = sampleMod
            yield from WAXS(pos_X, pos_Y, thickness, sampleMod, md={})

    # linkam = linkam_tc1
    linkam = linkam_ci94
    logger.info(f"Linkam controller PV prefix={linkam.prefix}")

    t0 = time.time()
    yield from collectAllThree()

    yield from bps.mv(linkam.rate, rate1)  # sets the rate of next ramp
    yield from linkam.set_target(temp1, wait=False)  # sets the temp of next ramp
    logger.info(f"Ramping temperature to {temp1} C")

    while not linkam.settled:  # runs data collection until next temp
        yield from collectAllThree()

    logger.info(f"Reached temperature, now collecting data for {delay1} seconds")
    t1 = time.time()

    while time.time() - t1 < delay1:  # collects data for delay1 seconds
        yield from collectAllThree()

    logger.info(f"waited for {delay1} seconds, now ramping temperature to {temp2} C")

    yield from bps.mv(linkam.rate, rate2)  # sets the rate of next ramp
    yield from linkam.set_target(temp2, wait=False)  # sets the temp of next ramp

    while not linkam.settled:  # runs data collection until next temp
        yield from collectAllThree()

    logger.info(f"reached {temp2} C")

    yield from collectAllThree()

    logger.info("finished")
