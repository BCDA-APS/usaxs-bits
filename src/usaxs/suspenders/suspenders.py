"""
suspenders : conditions that will interrupt the RunEngine execution
"""

__all__ = []

import logging

from bluesky import plan_stubs as bps

from .monochromator import MONO_FEEDBACK_ON
from .monochromator import monochromator

logger = logging.getLogger(__name__)
logger.info(__file__)


class FeedbackHandlingDuringSuspension:
    """
    Ensure feedback is on while waiting to resume.

    See https://github.com/APS-USAXS/ipython-usaxs/issues/520
    """

    previous = None  # feedback setting just before beam dump
    timeout = 100  # used for setting feedback ON or previous value

    def turn_feedback_on(self):
        yield from bps.mv(
            monochromator.feedback.on,
            MONO_FEEDBACK_ON,
            timeout=self.timeout,
        )

    def mono_beam_lost_plan(self):
        # self.previous  = monochromator.feedback.on.get()
        yield from self.turn_feedback_on()

    def mono_beam_just_came_back_but_after_sleep_plan(self):
        # if self.previous is not None:
        #     yield from bps.mv(
        #         monochromator.feedback.on, self.previous,
        #         timeout=self.timeout,
        #     )
        #     self.previous = None
        yield from self.turn_feedback_on()
