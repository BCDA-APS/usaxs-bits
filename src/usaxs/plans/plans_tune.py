"""
USAXS optics tuning plans.

Public entry points
-------------------
* ``preUSAXStune``  — tune ar and a2rp; the standard pre-scan tune.
* ``allUSAXStune``  — tune mr, ar, and a2rp; full optics tune.
* ``preSWAXStune``  — placeholder for SAXS/WAXS pre-scan tune (not yet implemented).
"""

import datetime
import logging
import time
from collections import OrderedDict

from apsbits.core.instrument_init import oregistry
from bluesky import plan_stubs as bps
from bluesky.utils import plan

from .axis_tuning import tune_a2rp
from .axis_tuning import tune_ar
from .axis_tuning import tune_mr
from .mode_changes import mode_USAXS
from .mono_feedback import MONO_FEEDBACK_ON
from .requested_stop import IfRequestedStopBeforeNextScan

logger = logging.getLogger(__name__)

MASTER_TIMEOUT = 60


usaxs_shutter = oregistry["usaxs_shutter"]
user_data = oregistry["user_data"]
monochromator = oregistry["monochromator"]
mono_shutter = oregistry["mono_shutter"]
terms = oregistry["terms"]
s_stage = oregistry["s_stage"]
d_stage = oregistry["d_stage"]
usaxs_slit = oregistry["usaxs_slit"]
guard_slit = oregistry["guard_slit"]
scaler0 = oregistry["scaler0"]
m_stage = oregistry["m_stage"]
a_stage = oregistry["a_stage"]


@plan
def preUSAXStune(md={}):  # noqa: B006
    """Bluesky plan: tune the USAXS optics (ar and a2rp) before a scan.

    Safe to call from any instrument mode.  Switches to USAXS mode, opens
    the mono shutter, tunes the A-stage rocking-curve (ar) and the A-stage
    crystal parallelism (a2rp), then restores the scaler count time.

    Parameters
    ----------
    md : dict, optional
        Metadata passed to each tuning sub-plan.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.

    Notes
    -----
    Usage: ``RE(preUSAXStune())``
    """
    yield from MONO_FEEDBACK_ON()
    yield from bps.mv(
        # fmt:off
        mono_shutter,
        "open",
        usaxs_shutter,
        "close",
        timeout=MASTER_TIMEOUT,
        # fmt:on
    )
    yield from IfRequestedStopBeforeNextScan()  # stop if user chose to do so.

    yield from mode_USAXS()

    if terms.preUSAXStune.use_specific_location.get() in (1, "yes"):
        yield from bps.mv(
            # fmt:off
            s_stage.x,
            terms.preUSAXStune.sx.get(),
            s_stage.y,
            terms.preUSAXStune.sy.get(),
            timeout=MASTER_TIMEOUT,
            # fmt:on
        )

    yield from bps.mv(
        # fmt:off
        d_stage.x,
        terms.USAXS.DX0.get(),
        d_stage.y,
        terms.USAXS.diode.dy.get(),
        user_data.time_stamp,
        str(datetime.datetime.now()),
        usaxs_slit.v_size,
        terms.SAXS.usaxs_v_size.get(),
        usaxs_slit.h_size,
        terms.SAXS.usaxs_h_size.get(),
        guard_slit.v_size,
        terms.SAXS.usaxs_guard_v_size.get(),
        guard_slit.h_size,
        terms.SAXS.usaxs_guard_h_size.get(),
        scaler0.preset_time,
        0.1,
        timeout=MASTER_TIMEOUT,
        # fmt:on
    )
    yield from user_data.set_state_plan("pre-USAXS optics tune")

    # when all that is complete, then ...
    yield from bps.mv(usaxs_shutter, "open", timeout=MASTER_TIMEOUT)

    tuners = OrderedDict()  # list the axes to tune
    # APS-U USAXS does not need tuning M stage too often. Leave to manual staff action
    tuners[a_stage.r] = tune_ar  # tune A stage to M stage
    tuners[a_stage.r2p] = tune_a2rp  # make A stage crystals parallel

    # now, tune the desired axes, bail out if a tune fails
    for _axis, tune in tuners.items():
        yield from bps.mv(usaxs_shutter, "open", timeout=MASTER_TIMEOUT)
        yield from tune(md=md)

        # If we don't wait, the next tune often fails
        # intensity stays flat, statistically
        # We need to wait a short bit to allow EPICS database
        # to complete processing and report back to us.
        yield from bps.sleep(0.5)

    logger.debug("USAXS count time: %s second(s)", terms.USAXS.usaxs_time.get())
    yield from bps.mv(
        # fmt:off
        scaler0.preset_time,
        terms.USAXS.usaxs_time.get(),
        user_data.time_stamp,
        str(datetime.datetime.now()),
        terms.preUSAXStune.num_scans_last_tune,
        0,
        terms.preUSAXStune.run_tune_next,
        0,
        terms.preUSAXStune.epoch_last_tune,
        time.time(),
        timeout=MASTER_TIMEOUT,
        # fmt:on
    )
    yield from user_data.set_state_plan("pre-USAXS optics tune")


@plan
def allUSAXStune(md=None):
    """Bluesky plan: full USAXS optics tune (mr, ar, a2rp).

    Safe to call from any instrument mode.  Tunes the M-stage
    rocking-curve (mr), then the A-stage rocking-curve (ar) and crystal
    parallelism (a2rp).

    Parameters
    ----------
    md : dict, optional
        Metadata passed to each tuning sub-plan.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.

    Notes
    -----
    Usage: ``RE(allUSAXStune())``
    """
    yield from MONO_FEEDBACK_ON()
    yield from bps.mv(
        mono_shutter,
        "open",
        usaxs_shutter,
        "close",
        timeout=MASTER_TIMEOUT,
    )
    yield from IfRequestedStopBeforeNextScan()  # stop if user chose to do so.

    yield from mode_USAXS()

    if terms.preUSAXStune.use_specific_location.get() in (1, "yes"):
        yield from bps.mv(
            s_stage.x,
            terms.preUSAXStune.sx.get(),
            s_stage.y,
            terms.preUSAXStune.sy.get(),
            timeout=MASTER_TIMEOUT,
        )

    yield from bps.mv(
        # fmt:off
        d_stage.x,
        terms.USAXS.DX0.get(),
        d_stage.y,
        terms.USAXS.diode.dy.get(),
        user_data.time_stamp,
        str(datetime.datetime.now()),
        usaxs_slit.v_size,
        terms.SAXS.usaxs_v_size.get(),
        usaxs_slit.h_size,
        terms.SAXS.usaxs_h_size.get(),
        guard_slit.v_size,
        terms.SAXS.usaxs_guard_v_size.get(),
        guard_slit.h_size,
        terms.SAXS.usaxs_guard_h_size.get(),
        scaler0.preset_time,
        0.1,
        timeout=MASTER_TIMEOUT,
        # fmt:on
    )
    yield from user_data.set_state_plan("pre-USAXS optics tune")

    # when all that is complete, then ...
    yield from bps.mv(usaxs_shutter, "open", timeout=MASTER_TIMEOUT)

    tuners = OrderedDict()  # list the axes to tune
    tuners[m_stage.r] = tune_mr  # tune M stage to monochromator
    tuners[a_stage.r] = tune_ar  # tune A stage to M stage
    tuners[a_stage.r2p] = tune_a2rp  # make A stage crystals parallel

    # now, tune the desired axes, bail out if a tune fails
    for _axis, tune in tuners.items():
        yield from bps.mv(usaxs_shutter, "open", timeout=MASTER_TIMEOUT)
        yield from tune(md=md)

        # If we don't wait, the next tune often fails
        # intensity stays flat, statistically
        # We need to wait a short bit to allow EPICS database
        # to complete processing and report back to us.
        yield from bps.sleep(0.5)

    logger.debug("USAXS count time: %s second(s)", terms.USAXS.usaxs_time.get())
    yield from bps.mv(
        # fmt:off
        scaler0.preset_time,
        terms.USAXS.usaxs_time.get(),
        user_data.time_stamp,
        str(datetime.datetime.now()),
        terms.preUSAXStune.num_scans_last_tune,
        0,
        terms.preUSAXStune.run_tune_next,
        0,
        terms.preUSAXStune.epoch_last_tune,
        time.time(),
        timeout=MASTER_TIMEOUT,
        # fmt:on
    )
    yield from user_data.set_state_plan("pre-USAXS optics tune")


@plan
def preSWAXStune(md=None):
    """Bluesky plan: pre-scan tune for SAXS/WAXS optics (stub).

    Not yet implemented.  Currently only updates the instrument state PV.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.

    Notes
    -----
    Usage: ``RE(preSWAXStune())``
    """
    yield from user_data.set_state_plan("pre-SWAXS optics tune")
