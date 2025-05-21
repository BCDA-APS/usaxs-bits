
"""
plans that do not generate a run
"""

__all__ = ["no_run_trigger_and_wait",]

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

from bluesky import plan_stubs as bps


def no_run_trigger_and_wait(objects):
    """
    count objects (presume detectors) but do not create a bluesky run

    Does most of bps.trigger_and_read() but does not create&save a run.
    Caller must call `.read()` on each object once this returns.

    The primary use case is to count detectors (on a scaler card)
    when measuring sample transmission.
    """
    if not isinstance(objects, (tuple, set, list)):
        objects = [objects]
    group = bps._short_uid("trigger_and_wait_no_run")
    for obj in objects:
        yield from bps.trigger(obj, group=group)
    yield from bps.wait(group=group)
