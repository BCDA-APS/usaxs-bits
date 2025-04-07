"""
Linkam plan for Fan Zhang experiments 2020-12.

Load this into a bluesky console session with::

    %run -m fz_linkam

Note:
Use option is "-m" and no trailing ".py".  Loads as
a *module*.  The directory is already on the search path.
"""

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)


import time

from bluesky import plan_stubs as bps
from instrument.devices import linkam_tc1
from instrument.plans import SAXS
from instrument.plans import WAXS
from instrument.plans import USAXSscan
from instrument.plans import after_command_list
from instrument.plans import before_command_list
from instrument.plans import reset_USAXS
from instrument.plans.command_list import *
from usaxs_support.surveillance import instrument_archive

# NOTE NOTE NOTE NOTE NOTE NOTE
# this plan's name is custom!
# NOTE NOTE NOTE NOTE NOTE NOTE


def fzLinkamPlan(
    pos_X, pos_Y, thickness, scan_title, temp1, rate1, delay1_min, temp2, rate2, md={}
):
    """
    collect RT USAXS/SAXS/WAXS
    change temperature T to temp1 with rate1
    collect USAXS/SAXS/WAXS while heating
    when temp1 reached, hold for delay1 min, collecting data repeatedly
    change T to temp2 with rate2
    collect USAXS/SAXS/WAXS while heating
    when temp2 reached, hold for delay2 seconds, collecting data repeatedly
    collect final data
    and it will end here...

    reload by
    # %run -m linkam
    """

    def setSampleName():
        return (
            f"{scan_title}" f"_{linkam.value+0.5:.0f}C" f"_{(time.time()-t0)/60:.0f}min"
        )

    def collectAllThree(debug=False):
        sampleMod = setSampleName()
        if debug:
            # for testing purposes, set debug=True
            print(sampleMod)
            yield from bps.sleep(20)
        else:
            try:
                md["title"] = sampleMod
                yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
            except Exception as exc:
                logger.error(exc)
                yield from reset_USAXS()

            try:
                sampleMod = setSampleName()
                md["title"] = sampleMod
                yield from SAXS(pos_X, pos_Y, thickness, sampleMod, md={})
            except Exception as exc:
                logger.error(exc)

            try:
                sampleMod = setSampleName()
                md["title"] = sampleMod
                yield from WAXS(pos_X, pos_Y, thickness, sampleMod, md={})
            except Exception as exc:
                logger.error(exc)

    summary = (
        "Linkam USAXS/SAXS/WAXS heating sequence\n"
        f"fzLinkamPlan(pos_X={pos_X}, pos_Y={pos_Y},thickness={thickness},"
        f"sample_name={scan_title}, temp1={temp1},rate1={rate1})"
        f"delay1_min={delay1_min}, temp2={temp2},rate2={rate2})"
    )
    instrument_archive(summary)

    # Linkam device choice
    linkam = linkam_tc1  # Linkam T96, 600, 1500V, 350V
    # linkam = linkam_ci94   # Linkam 1500 using old controller.
    logger.info(f"Linkam controller PV prefix={linkam.prefix}")
    # this runs start of scan code...
    yield from before_command_list(md={})

    # go to 40C and measure all data there as baseline...
    yield from bps.mv(linkam.ramprate.setpoint, 50)  # sets the rate of next ramp
    yield from linkam.set_target(40, wait=True)  # sets the temp of next ramp
    t0 = time.time()
    yield from collectAllThree()
    # yield from mode_USAXS()

    # here is start of heating rmap up.
    yield from bps.mv(linkam.ramprate.setpoint, rate1)  # sets the rate of next ramp
    yield from linkam.set_target(temp1, wait=True)  # sets the temp of next ramp
    logger.info(f"Ramping temperature to {temp1} C")

    # enable is want to collect data as heating up...
    # while not linkam.settled:                           #runs data collection until next temp
    #    yield from collectAllThree()

    # at temperature stuff goes here...
    logger.info(f"Reached temperature, now collecting data for {delay1_min} minutes")
    t1 = time.time()
    t0 = time.time()
    # this is main loop where we collect data at temeprature.
    while time.time() - t1 < delay1_min * 60:  # collects data for delay1 seconds
        yield from collectAllThree()

    logger.info(f"waited for {delay1_min} min, now changing temperature to {temp2} C")

    # done with main loop, we will cool next.
    t0 = time.time()
    yield from bps.mv(linkam.ramprate.setpoint, rate2)  # sets the rate of next ramp
    yield from linkam.set_target(temp2, wait=False)  # sets the temp of next ramp

    # collecting data on cooling
    while not linkam.settled:  # runs data collection until next temp
        yield from collectAllThree()

    logger.info(f"reached {temp2} C")

    # cooling finished, get one more data set at final temperature.
    yield from collectAllThree()

    # run endof scan code.
    yield from after_command_list()

    # done...
    logger.info("finished")
