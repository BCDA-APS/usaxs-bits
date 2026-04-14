"""
Monochromator feedback control plans.

``MONO_FEEDBACK_ON`` and ``MONO_FEEDBACK_OFF`` enable/disable the
hardware feedback loop that keeps the monochromator locked to the
beam energy.
"""

import logging

from apsbits.core.instrument_init import oregistry
from bluesky import plan_stubs as bps

logger = logging.getLogger(__name__)
logger.bsdev(__file__)


monochromator = oregistry["monochromator"]


def MONO_FEEDBACK_OFF():
    """Bluesky plan: disable the monochromator energy-feedback loop."""
    yield from bps.mv(monochromator.feedback.on, 0)


def MONO_FEEDBACK_ON():
    """Bluesky plan: enable the monochromator energy-feedback loop."""
    yield from bps.mv(monochromator.feedback.on, 1)
