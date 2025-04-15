"""
User can set a PV to request scanning to stop

Scanning will stop between scans at next loop through scan sequence.
"""

__all__ = """
    IfRequestedStopBeforeNextScan
""".split()

import logging
from typing import Any
from typing import Generator

from apsbits.utils.controls_setup import oregistry
from bluesky import plan_stubs as bps

logger = logging.getLogger(__name__)
logger.info(__file__)

# Device instances
mono_shutter = oregistry["mono_shutter"]
terms = oregistry["terms"]
ti_filter_shutter = oregistry["ti_filter_shutter"]
user_data = oregistry["user_data"]
RE = oregistry["RE"]


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
