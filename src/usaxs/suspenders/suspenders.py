"""
Suspender support classes for the 12-ID-E USAXS beamline.

A Bluesky suspender pauses the RunEngine when a condition is met and resumes
when the condition clears.  Suspenders can be given ``pre_plan`` and
``post_plan`` generator functions that run immediately before the pause and
immediately after the resume delay respectively.

This module provides two classes whose plan methods are passed as
``pre_plan`` / ``post_plan`` to the suspenders defined in
``suspender_functions.suspender_in_operations()``:

``FeedbackHandlingDuringSuspension``
    Used by the white-beam-ready suspender.  Keeps monochromator feedback ON
    and logs beam dump / recovery events to Obsidian.

``BeamInHutchSuspension``
    Used by the beam-in-hutch suspender.  Logs hutch-check failures and
    recoveries to Obsidian so users have a complete record of all suspensions.
"""

import logging

from apsbits.core.instrument_init import oregistry
from bluesky import plan_stubs as bps

from usaxs.utils.obsidian import recordBeamDump
from usaxs.utils.obsidian import recordBeamInHutchLost
from usaxs.utils.obsidian import recordBeamInHutchRestored
from usaxs.utils.obsidian import recordBeamRecovery

logger = logging.getLogger(__name__)

monochromator = oregistry["monochromator"]
usaxs_flyscan = oregistry["usaxs_flyscan"]

# Generous cap on the abort write itself; the busy record uses put_complete.
ABORT_TIMEOUT_S = 10


def abort_flyscan_if_flying():
    """Bluesky plan: stop an in-flight USAXS fly scan when the beam is lost.

    Used as part of the suspenders' ``pre_plan``, so it runs at the moment of
    suspension, before the RunEngine waits for beam to return.

    Why this is necessary
    ---------------------
    ``Flyscan_internal_plan`` arms the busy record with
    ``timeout=scan_time + timeout_s``.  That ophyd Status is a wall-clock timer
    and keeps counting while the RunEngine is suspended, so an outage longer
    than ``timeout_s`` makes the Status fail *during* the suspension.  The plan
    then dies with ``FailedStatus`` while still waiting for beam and never gets
    to resume.  Writing "Done" here stops the trajectory and closes the Status
    cleanly, so the outage can last arbitrarily long.

    On resume the RunEngine replays the cached messages, which re-arms the busy
    record and runs a fresh, complete sweep (see the checkpoint in
    ``fly_scan_plan.py``).  The data from the interrupted sweep is discarded,
    which is the point -- it was taken without beam.

    Also clears ``flying`` so the progress-reporting thread exits instead of
    logging frozen positions for the whole outage.  The replayed
    ``progress_kick`` write restarts it for the new attempt.

    No-op unless a fly scan is actually in progress, so SAXS, WAXS and step
    scans are unaffected.

    Yields
    ------
    Bluesky messages
    """
    if not usaxs_flyscan.flying.get():
        yield from bps.null()
        return

    logger.warning(
        "Beam lost during fly scan: aborting the trajectory so it "
        "can be restarted cleanly when beam returns."
    )
    try:
        yield from bps.abs_set(
            usaxs_flyscan.busy,
            usaxs_flyscan.busy.enum_strs[0],  # "Done"
            wait=True,
            timeout=ABORT_TIMEOUT_S,
        )
    except Exception as exc:
        # Never let the abort itself break the suspension handling.
        logger.error("Could not abort the fly scan trajectory: %s", exc)
    # Stop the progress thread; the replayed progress_kick starts a fresh one.
    yield from bps.abs_set(usaxs_flyscan.flying, False)


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

        Records the beam dump event in the Obsidian logbook, aborts an
        in-flight fly scan (see :func:`abort_flyscan_if_flying`), then turns
        monochromator feedback on so the mono is stable during the outage.

        Yields
        ------
        Bluesky messages
        """
        recordBeamDump()
        # Idempotent: a ring dump also closes the FE shutter, so that
        # suspender's pre_plan may already have aborted the sweep.
        yield from abort_flyscan_if_flying()
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


class BeamInHutchSuspension:
    """Bluesky plan hooks that log beam-in-hutch suspender events to Obsidian.

    Intended to be used as ``pre_plan`` / ``post_plan`` arguments to a
    ``bluesky.suspenders.SuspendBoolLow`` suspender watching the
    beam-in-hutch check signal (``usaxs_CheckBeamStandard``).

    When the hutch check fails the RunEngine pauses; when it recovers the
    RunEngine resumes.  Both events are written to the Obsidian logbook so
    users have a timestamped record of every suspension and restart.
    """

    def beam_not_in_hutch_plan(self):
        """Bluesky plan: called by the suspender when the hutch check fails.

        Records the suspension event in the Obsidian logbook and aborts an
        in-flight fly scan so its busy-record Status cannot age out while the
        RunEngine waits for beam.

        Yields
        ------
        Bluesky messages
        """
        recordBeamInHutchLost()
        yield from abort_flyscan_if_flying()

    def beam_in_hutch_restored_plan(self):
        """Bluesky plan: called by the suspender after the post-resume delay.

        Records the recovery event in the Obsidian logbook.

        Yields
        ------
        Bluesky messages
        """
        recordBeamInHutchRestored()
        yield from bps.null()
