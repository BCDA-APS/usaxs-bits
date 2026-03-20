"""No-run plans for the USAXS instrument.

Plans in this module trigger and read detectors without opening a Bluesky
run, so no data is saved to the databroker.  The primary use case is
measuring sample transmission via scaler counts outside of a scan.
"""

import logging

from apsbits.core.instrument_init import oregistry
from bluesky import plan_stubs as bps

from ..startup import bec

logger = logging.getLogger(__name__)


user_data = oregistry["user_data"]


def no_run_trigger_and_wait(objects):
    """Bluesky plan: trigger detectors and wait without creating a run.

    Triggers each object in *objects* and waits for all to complete.
    The caller is responsible for calling ``.read()`` on each object
    afterwards to retrieve the counts.

    Parameters
    ----------
    objects : object or list or set or tuple
        One or more triggerable ophyd objects (typically a scaler).

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    bec.disable_table()
    if not isinstance(objects, (tuple, set, list)):
        objects = [objects]
    group = bps._short_uid("trigger_and_wait_no_run")
    for obj in objects:
        yield from bps.trigger(obj, group=group)
    yield from bps.wait(group=group)
