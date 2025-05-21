"""
User can set a PV to request scanning to stop

Scanning will stop between scans at next loop through scan sequence.
"""

import datetime
import logging
import time

import bluesky
from apsbits.core.instrument_init import oregistry
from bluesky import plan_stubs as bps
from bluesky.run_engine import RequestAbort

from ..startup import RE

logger = logging.getLogger(__name__)

# Device instances
mono_shutter = oregistry["mono_shutter"]
terms = oregistry["terms"]
usaxs_shutter = oregistry["usaxs_shutter"]
user_data = oregistry["user_device"]


def IfRequestedStopBeforeNextScan():
    """plan: wait if requested"""

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

        # RE.pause_msg = "DEBUG: stopped the scans, ignore the (informative) exception trace"
        raise RequestAbort(msg)  # long exception trace?

    if open_the_shutter:
        yield from bps.mv(mono_shutter, "open")  # waits until complete
        # yield from bps.sleep(2)         # so, sleep not needed


# def IfRequestedStopBeforeNextScan() -> Generator[Any, None, None]:
#     """
#     Plan: check if stop was requested before next scan.

#     Parameters
#     ----------

#     Returns
#     -------
#     Generator[Any, None, None]
#         A generator that yields plan steps
#     """
#     if terms.USAXS.stop_requested.get():
#         yield from bps.mv(
#             mono_shutter,
#             "close",
#             usaxs_shutter,
#             "close",
#         )
#         yield from user_data.set_state_plan("Stop requested")
#         RE.stop()
#         return True
#     return False


# def handle_stop_request(
#     md: Optional[Dict[str, Any]] = None,
#     RE: Optional[Any] = None,
#     bec: Optional[Any] = None,
#     specwriter: Optional[Any] = None,
# ) -> Generator[Any, None, Any]:
#     """Handle a requested stop during instrument operation.

#     This function handles a requested stop by performing necessary cleanup
#     and state management tasks.

#     Parameters
#     ----------
#     md : Optional[Dict[str, Any]], optional
#         Metadata dictionary, by default None
#     RE : Optional[Any], optional
#         Bluesky RunEngine instance, by default None
#     bec : Optional[Any], optional
#         Bluesky Live Callbacks instance, by default None
#     specwriter : Optional[Any], optional
#         SPEC file writer instance, by default None

#     Returns
#     -------
#     Generator[Any, None, Any]
#         A sequence of plan messages

#     USAGE:  ``RE(handle_stop_request())``
#     """
#     if md is None:
#         md = {}
#     if RE is None:
#         raise ValueError("RunEngine instance must be provided")
#     if bec is None:
#         raise ValueError("Bluesky Live Callbacks instance must be provided")
#     if specwriter is None:
#         raise ValueError("SPEC file writer instance must be provided")

#     _md = {}
#     _md.update(md or {})

#     @bpp.run_decorator(md=_md)
#     def _inner() -> Generator[Any, None, Any]:
#         yield from user_data.set_state_plan("handling stop request")
#         yield from bps.mv(scaler0.count_mode, "AutoCount")
#         yield from bps.sleep(1)  # Allow time for cleanup

#     return (yield from _inner())
