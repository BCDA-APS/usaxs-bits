"""
plans that do not generate a run
"""

__all__ = [
    "no_run_trigger_and_wait",
]

import logging
from typing import Any
from typing import Generator
from typing import List
from typing import Set
from typing import Tuple
from typing import Union

from bluesky import plan_stubs as bps

logger = logging.getLogger(__name__)
logger.info(__file__)


def no_run_trigger_and_wait(
    objects: Union[Any, List[Any], Set[Any], Tuple[Any, ...]],
) -> Generator[Any, None, None]:
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
