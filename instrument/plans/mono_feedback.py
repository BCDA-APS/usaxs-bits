
"""
control the monochromator feedback
"""

__all__ = ["DCMfeedbackOFF", "DCMfeedbackON",]

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

from bluesky import plan_stubs as bps

from ..devices.monochromator import MONO_FEEDBACK_OFF
from ..devices.monochromator import MONO_FEEDBACK_ON
from ..devices.monochromator import monochromator


def DCMfeedbackOFF():
    """plan: could send email"""
    yield from bps.mv(monochromator.feedback.on, MONO_FEEDBACK_OFF)


def DCMfeedbackON():
    """plan: could send email"""
    yield from bps.mv(monochromator.feedback.on, MONO_FEEDBACK_ON)
    monochromator.feedback.check_position()
