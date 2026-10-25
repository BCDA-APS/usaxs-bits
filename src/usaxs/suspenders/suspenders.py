"""
Suspender support classes for the 12-ID-E USAXS beamline.

A Bluesky suspender pauses the RunEngine when a condition is met and resumes
when the condition clears.  Suspenders can be given ``pre_plan`` and
``post_plan`` generator functions that run immediately before the pause and
immediately before the resume respectively.  Any settle delay belongs at the
top of the ``post_plan``, not in the suspender's ``sleep=`` argument -- see
``FeedbackHandlingDuringSuspension.mono_beam_just_came_back_but_after_sleep_plan``.

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

import datetime
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


#: Width of the rule around an :func:`_announce` banner.
_BANNER_WIDTH = 72


def _announce(*lines) -> None:
    """Log a banner the operator cannot miss among the suspender chatter.

    A beam dump prints three ``SuspendBoolLow(EpicsSignalRO(read_pv=...))``
    repr dumps from bluesky, none of which says what happens next or how
    long it takes -- and since the settle moved out of ``sleep=`` they all
    read "Will sleep for 0 seconds", so the 100 s wait appears nowhere at
    all.  An operator watching that has no way to tell a recovering
    instrument from a hung one, and reaches for Ctrl-C.

    Parameters
    ----------
    *lines : str
        One sentence per line, inside the rules.
    """
    logger.info("=" * _BANNER_WIDTH)
    for line in lines:
        logger.info("%s", line)
    logger.info("=" * _BANNER_WIDTH)


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
    to resume.  Aborting here stops the trajectory and closes the Status
    cleanly, so the outage can last arbitrarily long.

    On resume the RunEngine replays the cached messages, which re-arms the busy
    record (see the checkpoint in ``fly_scan_plan.py``).  The IOC's
    ``scanSseq`` taxis AR, AX and DX to the first trajectory element itself
    before executing, so the replayed sweep is complete and correctly placed
    wherever this plan left the stages.  The data from the interrupted sweep
    is discarded, which is the point -- it was taken without beam.

    Three things happen, in this order:

    1. **Clear ``flying``** -- both to stop the progress thread and as the
       idempotence guard, since all three suspenders trip within ~100 ms of
       a dump and every one of them runs this pre_plan.
    2. **Write "Done" to the busy record.**  That is the whole abort.
    3. **Stop both electrometers and disarm their time series**, the same
       cleanup the end of a completed sweep does.  Otherwise they are left
       acquiring in "Ext. bulb" mode with armed series: on 2026-10-25
       ``usxFX42:FX4:Acquire`` was still 1 and five ``TSAcquire`` records
       still armed 70 minutes after the abort.

    The abort is wrapped so a failure is logged and the suspension still
    happens -- losing beam must never be made worse by the cleanup.

    Do **not** reach for ``usxLAX:USAXSfly:Abort`` here, however much it
    looks like the right record.  It drives ``fanAbort``, which does stop
    the sequence and the Aerotech properly -- but ``usxAERO:pm1:Abort`` is
    a plain ``bo`` with no self-reset, so it **latches**, and every later
    profile run fails with ``(54000) "This move command was stopped due to
    an abort command."``  Tried on 2026-10-25: the replayed sweep sat 65 s
    before the controller recovered, then ran its full 90 s, and the busy
    Status expired mid-sweep.  Writing Done to the busy record instead
    leaves the controller untouched; the sweep finishes unmonitored, and
    the replayed scan re-taxis and runs cleanly.

    **Keep this plan short, and never put a motor move in it.**  A pre_plan
    can be abandoned part-way through: when a second suspender trips,
    ``request_suspend`` cancels the RunEngine task and ``_run`` resumes at
    the new helper, so whatever message this plan was waiting on is never
    re-issued.  A three-motor ``bps.mv`` here was tried on 2026-10-25 and
    left this plan frozen on its ``wait`` for three minutes with the moves
    already issued and nobody waiting on them.  Returning the stages to
    their home positions belongs in ``Flyscan``'s own exit path, where it
    runs in the plan's context and cannot be abandoned.

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
    # 1. Clear ``flying`` first.  All three suspenders trip within ~100 ms of
    #    a dump and each runs this pre_plan, so this is also the idempotence
    #    guard: once it is False the second and third invocations return at
    #    the check above instead of repeating the whole cleanup.  It is the
    #    cheapest message here (a soft Signal), so it is safe to put first.
    #    It also stops the progress thread promptly; the replayed
    #    progress_kick starts a fresh one.
    yield from bps.abs_set(usaxs_flyscan.flying, False)

    # 2. Write "Done" to the busy record.  This is the whole abort.  The
    #    record is "Busy" at this point, so the put transitions it and the
    #    put-callback fires, which both releases this plan's write and
    #    releases the Status that ``Flyscan_internal_plan`` is waiting on.
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

    # 3. Stop the electrometers and disarm their time series.
    #    Imported here, not at module scope: fx4_setup is part of the plan
    #    layer and this module is imported from suspender_functions at startup.
    from usaxs.plans.fx4_setup import fx4_stop_timeseries
    from usaxs.plans.fx4_setup import usaxs_electrometers

    try:
        for det in usaxs_electrometers():
            yield from bps.mv(det.acquire, 0)
            yield from fx4_stop_timeseries(det)
    except Exception as exc:
        # Same rule as above: the suspension must still happen.
        logger.error("Could not stop the electrometers after the abort: %s", exc)


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
    settle_s : int
        Seconds to wait after beam returns, before the plan resumes, so mono
        feedback has time to pull the crystal back onto the peak. (100 s)
    """

    timeout = 100  # seconds; passed to bps.mv when setting feedback ON
    settle_s = 100  # seconds; mono feedback settle time after beam returns

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

        Announces what is about to happen, records the beam dump event in the
        Obsidian logbook, aborts an in-flight fly scan (see
        :func:`abort_flyscan_if_flying`), then turns monochromator feedback on
        so the mono is stable during the outage.

        Yields
        ------
        Bluesky messages
        """
        _announce(
            "BEAM LOST -- the scan is suspended.",
            "It restarts by itself. Do NOT press Ctrl-C.",
            f"Next: wait for beam, then {self.settle_s:.0f} s for the"
            " monochromator feedback to settle.",
        )
        recordBeamDump()
        # Idempotent: a ring dump also closes the FE shutter, so that
        # suspender's pre_plan may already have aborted the sweep.
        yield from abort_flyscan_if_flying()
        yield from self.turn_feedback_on()

    def mono_beam_just_came_back_but_after_sleep_plan(self):
        """Bluesky plan: called by the suspender once beam is back.

        Waits ``settle_s`` for mono feedback to recover, records the beam
        recovery event in the Obsidian logbook, then turns monochromator
        feedback on ready for scanning to resume.

        The settle time lives here rather than in the suspender's ``sleep=``
        argument because the RunEngine drops a pending ``sleep`` whenever a
        second suspender trips.  ``request_suspend`` cancels the RunEngine
        task to push the new suspender's helper plan onto the stack, and
        ``_run`` handles that cancellation with a bare ``continue`` while the
        state is ``suspending`` -- the earlier helper's ``Msg('wait_for')`` is
        never re-issued, so its future (the one the ``sleep=`` delay gates) is
        no longer awaited.  Only the last suspender to trip ends up timing the
        resume.  On 2026-10-24 a ring dump tripped this suspender, then the
        FE-shutter suspender (``sleep=0``) 23 s later, and the plan restarted
        the instant the shutter reopened -- 100 s early, with the mono still
        settling.  ``post_plan`` does run in that situation, so the delay is
        honoured from here.

        Yields
        ------
        Bluesky messages
        """
        resume_at = datetime.datetime.now() + datetime.timedelta(seconds=self.settle_s)
        _announce(
            "BEAM IS BACK -- recovering. Do NOT press Ctrl-C.",
            f"Next: {self.settle_s:.0f} s for the monochromator feedback to"
            " settle, then the scan continues on its own.",
            f"Expect it to resume at about {resume_at.strftime('%H:%M:%S')}.",
        )
        yield from bps.sleep(self.settle_s)
        logger.info("Monochromator feedback has settled -- the scan continues now.")
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
