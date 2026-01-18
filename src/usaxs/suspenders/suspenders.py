"""
suspenders : conditions that will interrupt the RunEngine execution
"""

from apsbits.core.instrument_init import oregistry
from bluesky import plan_stubs as bps
from usaxs.utils.obsidian import recordBeamDump, recordBeamRecovery

monochromator = oregistry["monochromator"]


class FeedbackHandlingDuringSuspension:
    """
    Ensure feedback is on while waiting to resume.

    See https://github.com/APS-USAXS/ipython-usaxs/issues/520
    """

    previous = None  # feedback setting just before beam dump
    timeout = 100  # used for setting feedback ON or previous value

    def turn_feedback_on(self):
        """
        Turn feedback on.
        """
        yield from bps.mv(
            monochromator.feedback.on,
            1,  # MONO_FEEDBACK_ON
            timeout=self.timeout,
        )

    def mono_beam_lost_plan(self):
        """
        Turn feedback on after beam loss.
        """
        # self.previous  = monochromator.feedback.on.get()
        #record in Obsidian
        recordBeamDump()
        yield from self.turn_feedback_on()

    def mono_beam_just_came_back_but_after_sleep_plan(self):
        """
        Turn feedback on after beam is back.
        """
        # if self.previous is not None:
        #     yield from bps.mv(
        #         monochromator.feedback.on, self.previous,
        #         timeout=self.timeout,
        #     )
        #     self.previous = None
        #record in Obsidian
        recordBeamRecovery()
        yield from self.turn_feedback_on()
