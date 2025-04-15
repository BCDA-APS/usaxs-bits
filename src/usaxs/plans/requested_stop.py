"""
User can set a PV to request scanning to stop

Scanning will stop between scans at next loop through scan sequence.
"""

__all__ = [
    "IfRequestedStopBeforeNextScan",
]

import datetime
import logging
import time
from typing import Any
from typing import Generator

import bluesky
from bluesky import plan_stubs as bps
from bluesky.run_engine import RequestAbort

from ..devices import mono_shutter
from ..devices import terms
from ..devices import ti_filter_shutter
from ..devices import user_data
from ..framework import RE

logger = logging.getLogger(__name__)
logger.info(__file__)


def IfRequestedStopBeforeNextScan() -> Generator[Any, None, None]:
    """plan: wait if requested"""
    global RE
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
        yield from bps.mv(
            ti_filter_shutter,
            "close",
            terms.StopBeforeNextScan,
            0,
            user_data.collection_in_progress,
            0,
            user_data.time_stamp,
            str(datetime.datetime.now()),
        )
        yield from user_data.set_state_plan("Aborted data collection")

        # RE.pause_msg = "DEBUG: stopped the scans, ignore the (informative) exception trace"
        raise RequestAbort(msg)  # long exception trace?

        # # To make the exception trace brief, `%xmode Minimal`
        # """
        # example:

        # In [8]: def plan():
        #    ...:     raise RequestAbort("Aborted from plan because user requested")
        # In [9]: RE(plan())
        # ---------------------------------------------------------------------------
        # RequestAbort                              Traceback (most recent call last)
        # <ipython-input-9-a6361a080fc0> in <module>
        # ----> 1 RE(plan())

        # <ipython-input-8-7178eb5f1267> in plan()
        #       1 def plan():
        # ----> 2     raise RequestAbort("Aborted from plan because user requested")
        #       3
        #       4

        # RequestAbort: Aborted from plan because user requested
        # In [12]: %xmode Minimal
        # Exception reporting mode: Minimal

        # In [13]: RE(plan())
        # RequestAbort: Aborted from plan because user requested
        # """

    if open_the_shutter:
        yield from bps.mv(mono_shutter, "open")  # waits until complete
        # yield from bps.sleep(2)         # so, sleep not needed
