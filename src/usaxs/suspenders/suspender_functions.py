"""
Suspender factory functions for the 12-ID-E USAXS beamline.

Provides two factory functions that create and return a pair of Bluesky
suspenders appropriate for the current operating mode.  Callers receive the
suspenders and decide how to install them.

``suspender_in_operations()``
    Real suspenders tied to live beam / shutter EPICS signals.  Returns:
    - ``suspend_FE_shutter`` : suspends when the Front End shutter closes
      (PSS state drops below 1).  **Do not install this globally** — it will
      block all RunEngine activity during any APS beam dump.  Apply it only
      to specific plans using ``@bpp.suspend_decorator(suspend_FE_shutter)``.
    - ``suspend_BeamInHutch`` : suspends when the beam-in-hutch check signal
      goes low.  Safe to install globally.

``suspender_in_sim()``
    Dummy suspenders backed by a software ``Signal`` that is never triggered.
    Used in simulation mode so the RunEngine has suspender objects without
    any real hardware dependency.
"""

import logging

import bluesky.suspenders
from apsbits.core.instrument_init import oregistry
from ophyd import Signal

from .suspenders import FeedbackHandlingDuringSuspension

logger = logging.getLogger(__name__)

FE_shutter = oregistry["FE_shutter"]
mono_shutter = oregistry["mono_shutter"]
white_beam_ready = oregistry["white_beam_ready"]
BeamInHutch = oregistry["usaxs_CheckBeamStandard"]


def suspender_in_operations():
    """Create and return real beam/shutter suspenders for operations mode.

    Creates three suspenders:

    ``suspender_white_beam_ready``
        Suspends when ``white_beam_ready.available`` goes low (beam lost).
        Runs ``FeedbackHandlingDuringSuspension.mono_beam_lost_plan`` before
        pausing and ``mono_beam_just_came_back_but_after_sleep_plan`` after a
        100-second sleep when the beam returns.  Not returned — installed
        internally via the feedback handler.

    ``suspend_FE_shutter``
        Suspends when ``FE_shutter.pss_state`` drops below 1 (A-shutter
        closes).  **Do not install globally** — doing so blocks all operations
        during any APS ring dump (lesson learned 2025-02-24).  Use only as a
        per-plan decorator: ``@bpp.suspend_decorator(suspend_FE_shutter)``.

    ``suspend_BeamInHutch``
        Suspends when the beam-in-hutch check signal goes low.  Safe to
        install on the RunEngine globally.

    Returns
    -------
    tuple[SuspendFloor, SuspendBoolLow]
        ``(suspend_FE_shutter, suspend_BeamInHutch)``
    """
    fb = FeedbackHandlingDuringSuspension()
    suspender_white_beam_ready = bluesky.suspenders.SuspendBoolLow(  # noqa: F841
        white_beam_ready.available,
        pre_plan=fb.mono_beam_lost_plan,
        sleep=100,  # RE sleeps _before_ calling post_plan
        post_plan=fb.mono_beam_just_came_back_but_after_sleep_plan,
    )

    suspend_BeamInHutch = bluesky.suspenders.SuspendBoolLow(BeamInHutch)  # noqa: F841
    logger.info(f"mono shutter connected = {mono_shutter.pss_state.connected}")
    logger.info(
        "Defining suspend_BeamInHutch.  Add as decorator to scan plans as desired."
    )
    suspend_FE_shutter = bluesky.suspenders.SuspendFloor(FE_shutter.pss_state, 1)  # noqa: F841

    return suspend_FE_shutter, suspend_BeamInHutch


def suspender_in_sim():
    """Create and return dummy suspenders for simulation mode.

    Both suspenders are backed by a single software ``Signal`` that is never
    set, so they never trigger.  This allows simulation-mode startup to
    produce suspender objects with the same interface as operations mode.

    Returns
    -------
    tuple[SuspendBoolHigh, SuspendBoolHigh]
        ``(suspend_FE_shutter, suspend_BeamInHutch)`` — both inert.
    """
    _simulated_beam_in_hutch = Signal(name="_simulated_beam_in_hutch")
    suspend_BeamInHutch = bluesky.suspenders.SuspendBoolHigh(_simulated_beam_in_hutch)  # noqa: F841
    suspend_FE_shutter = bluesky.suspenders.SuspendBoolHigh(_simulated_beam_in_hutch)  # noqa: F841

    return suspend_FE_shutter, suspend_BeamInHutch
