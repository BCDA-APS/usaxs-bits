"""No-run plans for the USAXS instrument.

This module provides plans for operations that don't require a full run,
such as simple device movements or status checks.
"""

__all__ = [
    "no_run_trigger_and_wait",
    "no_run_operation",
]

import logging
from typing import Any
from typing import Dict
from typing import Generator
from typing import List
from typing import Optional
from typing import Set
from typing import Tuple
from typing import Union

from ..startup import oregistry
from bluesky import plan_stubs as bps
from bluesky import preprocessors as bpp

logger = logging.getLogger(__name__)
logger.info(__file__)

# Device instances
scaler0 = oregistry["scaler0"]
user_data = oregistry["user_data"]


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


def no_run_operation(
    md: Optional[Dict[str, Any]] = None,
    RE: Optional[Any] = None,
    bec: Optional[Any] = None,
    specwriter: Optional[Any] = None,
) -> Generator[Any, None, Any]:
    """Perform a no-run operation.

    This function performs an operation that doesn't require a full run,
    such as a simple device movement or status check.

    Parameters
    ----------
    md : Optional[Dict[str, Any]], optional
        Metadata dictionary, by default None
    RE : Optional[Any], optional
        Bluesky RunEngine instance, by default None
    bec : Optional[Any], optional
        Bluesky Live Callbacks instance, by default None
    specwriter : Optional[Any], optional
        SPEC file writer instance, by default None

    Returns
    -------
    Generator[Any, None, Any]
        A sequence of plan messages

    USAGE:  ``RE(no_run_operation())``
    """
    if md is None:
        md = {}
    if RE is None:
        raise ValueError("RunEngine instance must be provided")
    if bec is None:
        raise ValueError("Bluesky Live Callbacks instance must be provided")
    if specwriter is None:
        raise ValueError("SPEC file writer instance must be provided")

    _md = {}
    _md.update(md or {})

    @bpp.run_decorator(md=_md)
    def _inner() -> Generator[Any, None, Any]:
        yield from user_data.set_state_plan("performing no-run operation")
        yield from bps.sleep(1)  # Simulate operation time

    return (yield from _inner())
