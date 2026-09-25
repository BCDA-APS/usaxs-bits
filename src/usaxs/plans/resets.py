"""
Instrument reset plan for USAXS.

``reset_USAXS`` moves the instrument to a known-safe USAXS configuration,
restores amplifier modes and motor kinds, and clears the collection flag.
"""

import logging

from apsbits.core.instrument_init import oregistry
from bluesky import plan_stubs as bps
from bluesky.utils import plan

from usaxs.devices.fx4_quadem import FX4AutorangeSettings as AutorangeSettings
from usaxs.plans.fx4_setup import enable_fx4_autorange
from usaxs.plans.fx4_setup import select_fx4_plot

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

    # Hand usxFX4's shared Range back to UPD and let the sequence program range
    # it again.  I0 has its own program on usxFX42; I00 has none.
    yield from enable_fx4_autorange(upd_controls, AutorangeSettings.auto_background)
    yield from enable_fx4_autorange(I0_controls, AutorangeSettings.auto_background)

    # fix omitted stuff from uascan see #584, #583
    # The FX4 detector signals go back to "normal": read and tabulated but not
    # plotted.  They used to be set "hinted" here, which was right for scaler
    # channels but would now put a trace on the plot for every detector --
    # select_fx4_plot is what a scan uses to choose one.
    select_fx4_plot([])
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
