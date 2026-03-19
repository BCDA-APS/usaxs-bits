"""
Suspender support classes for the 12-ID-E USAXS beamline.

A Bluesky suspender pauses the RunEngine when a condition is met and resumes
when the condition clears.  Suspenders can be given ``pre_plan`` and
``post_plan`` generator functions that run immediately before the pause and
immediately after the resume delay respectively.

This module provides ``FeedbackHandlingDuringSuspension``, whose plan methods
are passed as ``pre_plan`` / ``post_plan`` to the beam-loss suspender defined
in ``suspender_functions.suspender_in_operations()``.
"""

from apsbits.core.instrument_init import oregistry
from bluesky import plan_stubs as bps
from usaxs.utils.obsidian import recordBeamDump, recordBeamRecovery

monochromator = oregistry["monochromator"]


class FeedbackHandlingDuringSuspension:
    """Bluesky plan hooks that keep monochromator feedback on during beam loss.

    Intended to be used as ``pre_plan`` / ``post_plan`` arguments to a
    ``bluesky.suspenders.SuspendBoolLow`` suspender watching the beam-ready
    signal.  The design always forces feedback ON rather than restoring a
    previous state, to ensure the monochromator is stable when the beam
    returns.

    See https://github.com/APS-USAXS/ipython-usaxs/issues/520

    Attributes
    ----------
    timeout : int
        Timeout in seconds passed to ``bps.mv`` when setting feedback. (100 s)
    """

    timeout = 100  # seconds; passed to bps.mv when setting feedback ON

    def turn_feedback_on(self):
        """Bluesky plan: set monochromator feedback to ON (value=1).

        Yields
        ------
        Bluesky messages
        """
        yield from bps.mv(
            monochromator.feedback.on,
            1,  # MONO_FEEDBACK_ON
            timeout=self.timeout,
        )

    def mono_beam_lost_plan(self):
        """Bluesky plan: called by the suspender immediately on beam loss.

        Records the beam dump event in the Obsidian logbook, then turns
        monochromator feedback on so the mono is stable during the outage.

        Yields
        ------
        Bluesky messages
        """
        recordBeamDump()
        yield from self.turn_feedback_on()

    def mono_beam_just_came_back_but_after_sleep_plan(self):
        """Bluesky plan: called by the suspender after the post-resume sleep.

        Records the beam recovery event in the Obsidian logbook, then turns
        monochromator feedback on ready for scanning to resume.

        Yields
        ------
        Bluesky messages
        """
        recordBeamRecovery()
        yield from self.turn_feedback_on()
