"""
User can set a PV to request scanning to stop.

Scanning will stop between scans at next loop through the scan sequence.
"""

import datetime
import logging
import time

import bluesky
from apsbits.core.instrument_init import oregistry
from bluesky import plan_stubs as bps
from bluesky.run_engine import RequestAbort
from usaxs.utils.obsidian import recordUserAbort

from ..startup import RE

logger = logging.getLogger(__name__)

# Device instances
mono_shutter = oregistry["mono_shutter"]
terms = oregistry["terms"]
usaxs_shutter = oregistry["usaxs_shutter"]
user_data = oregistry["user_data"]


def IfRequestedStopBeforeNextScan():
    """Bluesky plan: honour user pause/stop requests between scans.

    If ``terms.PauseBeforeNextScan`` is set, waits in a 1-second loop until
    it is cleared, then re-opens the mono shutter.  If
    ``terms.StopBeforeNextScan`` is set, closes shutters, clears the flag,
    records the abort in Obsidian, and raises ``RequestAbort`` to halt the
    RunEngine.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.

    Raises
    ------
    RequestAbort
        When ``terms.StopBeforeNextScan`` is set by the user.
    """
    open_the_shutter = False
    t0 = time.time()

    RE.pause_msg = bluesky.run_engine.PAUSE_MSG  # sloppy

    pv_txt = "Pausing for user for %g s"
    while terms.PauseBeforeNextScan.get():
        msg = pv_txt % (time.time() - t0)
        logger.info(msg)
        yield from user_data.set_state_plan(msg)
        yield from bps.sleep(1)
        open_the_shutter = True

    if terms.StopBeforeNextScan.get():
        msg = "EPICS user requested stop data collection before next scan"
        logger.info(msg)
        # the last line of text is overwritten after the run ends
        logger.info("#" * 10)  # sacrificial text line
        mv_args = [
            usaxs_shutter,
            "close",
            terms.StopBeforeNextScan,
            0,
            user_data.collection_in_progress,
            0,
            user_data.time_stamp,
            str(datetime.datetime.now()),
        ]
        yield from bps.mv(*mv_args)
        yield from user_data.set_state_plan("Aborted data collection")

        # record for Obsidian
        recordUserAbort()

        raise RequestAbort(msg)  # long exception trace?

    if open_the_shutter:
        yield from bps.mv(mono_shutter, "open")  # waits until complete
