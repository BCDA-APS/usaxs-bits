"""
control the monochromator feedback
"""

import logging

from usaxs.startup import oregistry
from bluesky import plan_stubs as bps

logger = logging.getLogger(__name__)
logger.bsdev(__file__)


monochromator = oregistry["monochromator"]

def MONO_FEEDBACK_OFF():
    """plan: could send email"""
    yield from bps.mv(monochromator.feedback.on, 0)


def MONO_FEEDBACK_ON():
    """plan: could send email"""
    yield from bps.mv(monochromator.feedback.on, 1)
    monochromator.feedback.check_position()
