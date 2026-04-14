"""
Instrument reset plan for USAXS.

``reset_USAXS`` moves the instrument to a known-safe USAXS configuration,
restores amplifier modes and motor kinds, and clears the collection flag.
"""

import logging

from apsbits.core.instrument_init import oregistry
from apstools.devices import SCALER_AUTOCOUNT_MODE
from bluesky import plan_stubs as bps
from bluesky.utils import plan

from usaxs.devices.amplifiers import AutorangeSettings

from .mode_changes import mode_USAXS
from .mono_feedback import MONO_FEEDBACK_ON

logger = logging.getLogger(__name__)

# Device instances

I0 = oregistry["I0"]
I0_controls = oregistry["I0_controls"]
I00 = oregistry["I00"]
I00_controls = oregistry["I00_controls"]
TRD = oregistry["TRD"]
UPD = oregistry["UPD"]
a_stage = oregistry["a_stage"]
d_stage = oregistry["d_stage"]
m_stage = oregistry["m_stage"]
s_stage = oregistry["s_stage"]
scaler0 = oregistry["scaler0"]
terms = oregistry["terms"]
upd_controls = oregistry["upd_controls"]
usaxs_shutter = oregistry["usaxs_shutter"]
user_data = oregistry["user_data"]


@plan
def reset_USAXS():
    """Bluesky plan: return the USAXS instrument to a known-safe configuration.

    Switches to USAXS mode, enables mono feedback, closes the shutter, sets
    amplifier modes, restores motor positions from EPICS PVs, and resets
    ophyd ``kind`` attributes for key signals and axes.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    logger.info("Resetting USAXS")
    yield from mode_USAXS()
    yield from user_data.set_state_plan("resetting motors")
    yield from MONO_FEEDBACK_ON()
    yield from bps.mv(
        # fmt: off
        scaler0.count_mode,
        SCALER_AUTOCOUNT_MODE,
        upd_controls.auto.mode,
        AutorangeSettings.auto_background,
        I0_controls.auto.mode,
        AutorangeSettings.manual,
        I00_controls.auto.mode,
        AutorangeSettings.manual,
        usaxs_shutter,
        "close",
        user_data.scanning,
        "no",
        d_stage.x,
        terms.USAXS.DX0.get(),
        a_stage.x,
        terms.USAXS.AX0.get(),
        a_stage.r,
        terms.USAXS.ar_val_center.get(),
        # fmt: on
    )

    # fix omitted stuff from uascan see #584, #583
    upd_controls.kind = "hinted"  # correct value
    TRD.kind = "hinted"  # correct value
    I0.kind = "hinted"  # correct value
    I00.kind = "hinted"  # correct value
    for obj in (m_stage.r, a_stage.r, a_stage.x, s_stage.y, s_stage.x, d_stage.x):
        obj.kind = "normal"  #  correct value
        obj.user_setpoint.kind = "normal"  #  correct value
        obj.user_readback.kind = "hinted"  #  correct value

    yield from user_data.set_state_plan("USAXS reset complete")

    yield from bps.mv(
        # fmt: off
        user_data.collection_in_progress,
        0,  # despite the label, 0 means not collecting
        # fmt: on
    )
