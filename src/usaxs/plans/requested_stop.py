"""
User can set a PV to request scanning to stop

Scanning will stop between scans at next loop through scan sequence.
"""

__all__ = """
    IfRequestedStopBeforeNextScan
""".split()

import logging
from typing import Any
from typing import Dict
from typing import Generator
from typing import Optional

from apsbits.utils.controls_setup import oregistry
from bluesky import plan_stubs as bps
from bluesky import preprocessors as bpp

logger = logging.getLogger(__name__)
logger.info(__file__)

# Device instances
mono_shutter = oregistry["mono_shutter"]
terms = oregistry["terms"]
ti_filter_shutter = oregistry["ti_filter_shutter"]
user_data = oregistry["user_data"]
RE = oregistry["RE"]
scaler0 = oregistry["scaler0"]


def IfRequestedStopBeforeNextScan() -> Generator[Any, None, None]:
    """
    Plan: check if stop was requested before next scan.

    Parameters
    ----------

    Returns
    -------
    Generator[Any, None, None]
        A generator that yields plan steps
    """
    if terms.USAXS.stop_requested.get():
        yield from bps.mv(
            mono_shutter,
            "close",
            ti_filter_shutter,
            "close",
        )
        yield from user_data.set_state_plan("Stop requested")
        RE.stop()
        return True
    return False


def handle_stop_request(
    md: Optional[Dict[str, Any]] = None,
    RE: Optional[Any] = None,
    bec: Optional[Any] = None,
    specwriter: Optional[Any] = None,
) -> Generator[Any, None, Any]:
    """Handle a requested stop during instrument operation.

    This function handles a requested stop by performing necessary cleanup
    and state management tasks.

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

    USAGE:  ``RE(handle_stop_request())``
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
        yield from user_data.set_state_plan("handling stop request")
        yield from bps.mv(scaler0.count_mode, "AutoCount")
        yield from bps.sleep(1)  # Allow time for cleanup

    return (yield from _inner())
