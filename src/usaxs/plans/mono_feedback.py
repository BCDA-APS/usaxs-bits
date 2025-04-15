"""
control the monochromator feedback
"""

__all__ = [
    "DCMfeedbackOFF",
    "DCMfeedbackON",
]

import logging
from typing import Any
from typing import Dict
from typing import Generator
from typing import Optional

from bluesky import plan_stubs as bps

logger = logging.getLogger(__name__)
logger.info(__file__)


def DCMfeedbackOFF(
    oregistry: Optional[Dict[str, Any]] = None,
) -> Generator[Any, None, None]:
    """
    Plan: turn off monochromator feedback.

    Parameters
    ----------
    oregistry : Dict[str, Any], optional
        The ophyd registry containing device instances, by default None

    Returns
    -------
    Generator[Any, None, None]
        A generator that yields plan steps
    """
    # Get devices from oregistry
    monochromator = oregistry["monochromator"]
    MONO_FEEDBACK_OFF = oregistry["MONO_FEEDBACK_OFF"]

    yield from bps.mv(monochromator.feedback.on, MONO_FEEDBACK_OFF)


def DCMfeedbackON(
    oregistry: Optional[Dict[str, Any]] = None,
) -> Generator[Any, None, None]:
    """
    Plan: turn on monochromator feedback.

    Parameters
    ----------
    oregistry : Dict[str, Any], optional
        The ophyd registry containing device instances, by default None

    Returns
    -------
    Generator[Any, None, None]
        A generator that yields plan steps
    """
    # Get devices from oregistry
    monochromator = oregistry["monochromator"]
    MONO_FEEDBACK_ON = oregistry["MONO_FEEDBACK_ON"]

    yield from bps.mv(monochromator.feedback.on, MONO_FEEDBACK_ON)
    monochromator.feedback.check_position()
