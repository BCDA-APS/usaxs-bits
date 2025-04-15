"""
control the monochromator feedback
"""

__all__ = [
    "DCMfeedbackOFF",
    "DCMfeedbackON",
]

import logging
from typing import Any
from typing import Generator

from bluesky import plan_stubs as bps

from ..devices.monochromator import MONO_FEEDBACK_OFF
from ..devices.monochromator import MONO_FEEDBACK_ON
from ..devices.monochromator import monochromator

logger = logging.getLogger(__name__)
logger.info(__file__)


def DCMfeedbackOFF() -> Generator[Any, None, None]:
    """plan: could send email"""
    yield from bps.mv(monochromator.feedback.on, MONO_FEEDBACK_OFF)


def DCMfeedbackON() -> Generator[Any, None, None]:
    """plan: could send email"""
    yield from bps.mv(monochromator.feedback.on, MONO_FEEDBACK_ON)
    monochromator.feedback.check_position()
