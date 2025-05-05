
"""
control the monochromator feedback
"""

import logging

from apsbits.core.instrument_init import oregistry
from bluesky import plan_stubs as bps

logger = logging.getLogger(__name__)
logger.bsdev(__file__)


monochromator = oregistry["monochromator"]

def DCMfeedbackOFF():
    """plan: could send email"""
    yield from bps.mv(monochromator.feedback.on, 0)


def DCMfeedbackON():
    """plan: could send email"""
    yield from bps.mv(monochromator.feedback.on, 1)
    monochromator.feedback.check_position()
