"""
BS plan template to control Linkam temperature during data collection same as spec used to do.

load this way:
    %run -im usaxs.user.linkam_template

* PRJ, 2022-01-22 : updated for new linkam support
* JIL, 2021-11-12 : modified to use updated before_command_list(), verify operations
* JIL, 2022-11-05 : 20ID test
* JIL, 2024-12-03 : 12ID check and fix. Needs testing
* JIL, 2025-05-28 : fixs for BITS
* JIL, 2025-7-14  : operations
* JIL, 2025-12-11 : Used AI to clean up the code and made into template file. 

limitations: uses new Linkam support only for tc1 with linux ioc

"""

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

import time

from bluesky import plan_stubs as bps
from apsbits.core.instrument_init import oregistry


from usaxs.plans.plans_user_facing import saxsExp
from usaxs.plans.plans_user_facing import waxsExp
from usaxs.plans.plans_usaxs import USAXSscan
from usaxs.plans.command_list import after_command_list
from usaxs.plans.command_list import before_command_list
from ophyd import Signal
from usaxs.plans.command_list import sync_order_numbers
from usaxs.utils.obsidian import appendToMdFile, recordFunctionRun

linkam_tc1 = oregistry["linkam_tc1"]

SECOND = 1
MINUTE = 60 * SECOND
HOUR = 60 * MINUTE
DAY = 24 * HOUR
WEEK = 7 * DAY

linkam_debug = Signal(name="linkam_debug", value=False)
#   In order to run as debug (without collecting data, only control Linkam) in command line run:
# linkam_debug.put(True)

# DO NOT MODIFY THE TEMPLATE, COPY AND EDIT OR MAKE A NEW FILE...
def myLinkamPlan_template(
    pos_X, pos_Y, thickness, scan_title, temp1, rate1, delay1min, temp2, rate2, md={}
):
    """
    Sample measurement workflow using a Linkam TC-1 controller.

    1. Acquire room temperature data (≈40 °C).
    2. Ramp to *temp1* at *rate1* (no data collection during heating).
    3. Hold at *temp1* for *delay1min* minutes while collecting USAXS/SAXS/WAXS.
    4. Ramp to *temp2* at *rate2* (collect data during heating/cooling).
    5. Final data set at *temp2*.

    Temp is in C, delay is in minutes
    reload by
        %run -im usaxs.user.linkam
    Run as 
        RE(myLinkamPlan_template(0,0,1,"sample",200,100,20,40,100))
    """
    # ------------------------------------------------------------------
    # Helper utilities
    # ------------------------------------------------------------------
    def setSampleName():
        """Create a sample name that records the scan title, temperature, and elapsed time."""
        return (
            f"{scan_title}"
            f"_{linkam.temperature.position:.0f}C"
            f"_{(time.time() - t0)/60:.0f}min"
        )

    def collectAllThree(debug=False):
        """Run a USAXS → SAXS → WAXS sequence with appropriate sample naming."""
        sampleMod = setSampleName()
        if debug:
            print(sampleMod)
            yield from bps.sleep(20)
        else:
            yield from sync_order_numbers()
            md["title"] = sampleMod
            yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
            md["title"] = setSampleName()
            yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
            md["title"] = setSampleName()
            yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    def change_rate_and_temperature(rate, t, wait=False):
        """Set ramp rate and target temperature on the Linkam controller."""
        yield from bps.mv(linkam.ramprate.setpoint, rate)
        yield from linkam.set_target(t, wait=wait)

    # ------------------------------------------------------------------
    # Execution sequence
    # ------------------------------------------------------------------
    linkam = linkam_tc1
    isDebugMode = linkam_debug.get()

    # Normal startup scripts (skip in debug mode)
    if not isDebugMode:
        yield from before_command_list()            #records also Obsidian start

    # 1. Acquire room‑temperature data
    yield from change_rate_and_temperature(150, 40, wait=True)
    t0 = time.time()  # reset elapsed‑time counter 
    yield from collectAllThree(isDebugMode)

    # 2. Ramp to *temp1*, hold, and collect during the hold
    logger.info(f"Ramping temperature to {temp1} C")
    appendToMdFile(f"Ramping temperature to {temp1} C")
    yield from change_rate_and_temperature(rate1, temp1, wait=True)
    t0 = time.time()  # reset elapsed‑time counter

    logger.info(f"Reached temperature, collecting data for {delay1min} minutes")
    appendToMdFile(f"Reached temperature, collecting data for {delay1min} minutes")
    hold_until = time.time() + delay1min * 60
    while time.time() < hold_until:
        yield from collectAllThree(isDebugMode)

    logger.info(f"Waited {delay1min} minutes, now changing temperature to {temp2} C")
    appendToMdFile(f"Waited {delay1min} minutes, now changing temperature to {temp2} C")    

    # 3. Ramp to *temp2* while collecting data
    yield from change_rate_and_temperature(rate2, temp2, wait=False)
    while not linkam.temperature.inposition:
        yield from collectAllThree(isDebugMode)

    logger.info(f"Reached {temp2} C")
    appendToMdFile(f"Reached {temp2} C")
    yield from collectAllThree(isDebugMode)  # final set

    logger.info("finished")
    appendToMdFile("finished")

    # Normal cleanup scripts (skip in debug mode)
    if not isDebugMode:
        yield from after_command_list()


