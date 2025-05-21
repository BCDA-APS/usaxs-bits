# this is a warmup instrument plan

import logging

logger = logging.getLogger(__name__)


from bluesky import plan_stubs as bps
from instrument.devices import usaxs_flyscan


def warmupInstrument():
    """
    simply runs just epics flyscan in a loop, with delays between scans.
    run as:
    RE(warmupInstrument())
    to stop, simply do ctrl-C ctrol-C
    and then RE.abort()
    this should return BS to idle...

    reload by :
    %run -m warmup
    """

    while True:
        try:
            logger.info(f"Starting '{usaxs_flyscan.busy.pvname}'")
            yield from bps.mv(usaxs_flyscan.busy, "Busy")
            logger.info(f"completed '{usaxs_flyscan.busy.pvname}'")
        except Exception as exc:
            logger.error(f"caught {exc}")
        yield from bps.sleep(900)
