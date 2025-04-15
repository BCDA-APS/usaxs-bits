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

from apsbits.utils.controls_setup import oregistry
from bluesky import plan_stubs as bps

logger = logging.getLogger(__name__)
logger.info(__file__)

# Constants
MONO_FEEDBACK_OFF = oregistry["MONO_FEEDBACK_OFF"]
MONO_FEEDBACK_ON = oregistry["MONO_FEEDBACK_ON"]

# Device instances
monochromator = oregistry["monochromator"]


def DCMfeedbackOFF() -> Generator[Any, None, None]:
    """
    Plan: turn off monochromator feedback.

    Returns
    -------
    Generator[Any, None, None]
        A generator that yields plan steps
    """
    yield from bps.mv(monochromator.feedback.on, MONO_FEEDBACK_OFF)


def DCMfeedbackON() -> Generator[Any, None, None]:
    """
    Plan: turn on monochromator feedback.

    Returns
    -------
    Generator[Any, None, None]
        A generator that yields plan steps
    """
    yield from bps.mv(monochromator.feedback.on, MONO_FEEDBACK_ON)
    monochromator.feedback.check_position()
