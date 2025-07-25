"""Suspender functions for USAXS beamline operations."""

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
    """Configure suspenders for operations mode."""
    fb = FeedbackHandlingDuringSuspension()
    suspender_white_beam_ready = bluesky.suspenders.SuspendBoolLow(  # noqa: F841
        white_beam_ready.available,
        pre_plan=fb.mono_beam_lost_plan,
        sleep=100,  # RE sleeps _before_ calling post_plan
        post_plan=fb.mono_beam_just_came_back_but_after_sleep_plan,
    )  # noqa: F841

    suspend_BeamInHutch = bluesky.suspenders.SuspendBoolLow(BeamInHutch)  # noqa: F841
    logger.info(f"mono shutter connected = {mono_shutter.pss_state.connected}")
    # DO NOT INSTALL THIS for always!!!! It prevents all operations when APS dumps
    # and A shutter closes. 2-24-2025 JIL, hard lesson learned. Really annoying.
    # use following construct now:
    # @bpp.suspend_decorator(suspend_FE_shutter)
    logger.info(
        "Defining suspend_BeamInHutch.  Add as decorator to scan plans as desired."
    )
    suspend_FE_shutter = bluesky.suspenders.SuspendFloor(FE_shutter.pss_state, 1)  # noqa: F841

    return suspend_FE_shutter, suspend_BeamInHutch


def suspender_in_sim():
    """Configure suspenders for simulation mode."""
    # simulators
    _simulated_beam_in_hutch = Signal(name="_simulated_beam_in_hutch")
    suspend_BeamInHutch = bluesky.suspenders.SuspendBoolHigh(_simulated_beam_in_hutch)  # noqa: F841
    suspend_FE_shutter = bluesky.suspenders.SuspendBoolHigh(_simulated_beam_in_hutch)  # noqa: F841

    return suspend_FE_shutter, suspend_BeamInHutch
