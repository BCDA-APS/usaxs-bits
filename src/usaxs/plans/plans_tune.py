"""
user-facing scans
"""

import datetime
import logging
import time
from collections import OrderedDict
from typing import Any
from typing import Dict
from typing import Optional

from .mono_feedback import MONO_FEEDBACK_ON
from apsbits.core.instrument_init import oregistry
from bluesky import plan_stubs as bps
from bluesky import preprocessors as bpp

from usaxs.startup import suspend_BeamInHutch
from usaxs.startup import suspend_FE_shutter
from usaxs.utils.emails import email_notices

from .axis_tuning import tune_a2rp
from .axis_tuning import tune_ar
from .axis_tuning import tune_mr
from .mode_changes import mode_USAXS
from .mono_feedback import MONO_FEEDBACK_ON
from .requested_stop import IfRequestedStopBeforeNextScan


logger = logging.getLogger(__name__)

MASTER_TIMEOUT = 60


# # Device and plan instances from oregistry (allowed list)
mono_shutter = oregistry["mono_shutter"]
usaxs_shutter = oregistry["usaxs_shutter"]
guard_slit = oregistry["guard_slit"]
monochromator = oregistry["monochromator"]
terms = oregistry["terms"]
s_stage = oregistry["s_stage"]
usaxs_slit = oregistry["usaxs_slit"]
user_data = oregistry["user_device"]
scaler0 = oregistry["scaler0"]
m_stage = oregistry["m_stage"]
a_stage = oregistry["a_stage"]
d_stage = oregistry["d_stage"]
mono_shutter = oregistry["mono_shutter"]
usaxs_shutter = oregistry["usaxs_shutter"]
usaxs_slit = oregistry["usaxs_slit"]
user_data = oregistry["user_device"]
scaler0 = oregistry["scaler0"]
m_stage = oregistry["m_stage"]
a_stage = oregistry["a_stage"]
d_stage = oregistry["d_stage"]
monochromator = oregistry["monochromator"]
terms = oregistry["terms"]
s_stage = oregistry["s_stage"]
guard_slit = oregistry["guard_slit"]
monochromator = oregistry["monochromator"]
mono_shutter = oregistry["mono_shutter"]
ccd_shutter = oregistry["ccd_shutter"]
terms = oregistry["terms"]
s_stage = oregistry["s_stage"]
user_data = oregistry["user_data"]
scaler0 = oregistry["scaler0"]
usaxs_shutter = oregistry["usaxs_shutter"]
m_stage = oregistry["m_stage"]
ms_stage = oregistry["ms_stage"]
tune_msrp = oregistry["tune_msrp"]
tune_m2rp = oregistry["tune_m2rp"]
monochromator = oregistry["monochromator"]
mono_shutter = oregistry["mono_shutter"]
ccd_shutter = oregistry["ccd_shutter"]
terms = oregistry["terms"]
s_stage = oregistry["s_stage"]
d_stage = oregistry["d_stage"]
user_data = oregistry["user_device"]
usaxs_slit = oregistry["usaxs_slit"]
guard_slit = oregistry["guard_slit"]
scaler0 = oregistry["scaler0"]
usaxs_shutter = oregistry["usaxs_shutter"]
m_stage = oregistry["m_stage"]
a_stage = oregistry["a_stage"]
NOTIFY_ON_BADTUNE = oregistry["NOTIFY_ON_BADTUNE"]

@bpp.suspend_decorator(suspend_FE_shutter)
@bpp.suspend_decorator(suspend_BeamInHutch)
def preUSAXStune(md={}):
    """
    Tune the USAXS optics in any mode, is safe.

    Parameters
    ----------
    md : Optional[Dict[str, Any]], optional
        Metadata dictionary, by default None
    RE : Optional[Any], optional
        Bluesky RunEngine instance, by default None
    bec : Optional[Any], optional
        Bluesky Live Callbacks instance, by default None
    specwriter : Optional[Any], optional
        SPEC file writer instance, by default None

    Returns
    -------
    Generator[Any, None, None]
        A generator that yields plan steps

    USAGE:  ``RE(preUSAXStune())``
    """


    yield from bps.mv(
        monochromator.feedback.on,
        MONO_FEEDBACK_ON,
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
    )
    yield from user_data.set_state_plan("pre-USAXS optics tune")

    # when all that is complete, then ...
    yield from bps.mv(usaxs_shutter, "open", timeout=MASTER_TIMEOUT)

    # TODO: install suspender using usaxs_CheckBeamStandard.get()

    tuners = OrderedDict()  # list the axes to tune
    # 20IDB does not need tuning M stage too often. Leave to manual staff action
    # tuners[m_stage.r] = tune_mr            # tune M stage to monochromator
    if not m_stage.isChannelCut:
        # tuners[m_stage.r2p] = tune_m2rp  # make M stage crystals parallel
        pass
    if terms.USAXS.useMSstage.get():
        # tuners[ms_stage.rp] = tune_msrp    # align MSR stage with M stage
        pass
    if terms.USAXS.useSBUSAXS.get():
        # tuners[as_stage.rp] = tune_asrp
        #     align ASR stage with MSR stage
        #     and set ASRP0 value
        pass
    # tuners[a_stage.r] = tune_ar  # tune A stage to M stage
    #tuners[a_stage.r2p] = tune_a2rp  # make A stage crystals parallel
    tuners[a_stage.r] = tune_ar  # tune A stage to M stage
    # tuners[a_stage.r2p] = tune_a2rp  # make A stage crystals parallel
    tuners[a_stage.r] = tune_ar  # tune A stage to M stage
    tuners[a_stage.r2p] = tune_a2rp  # make A stage crystals parallel

    # now, tune the desired axes, bail out if a tune fails
    # yield from bps.install_suspender(suspend_BeamInHutch)
    for axis, tune in tuners.items():
        yield from bps.mv(usaxs_shutter, "open", timeout=MASTER_TIMEOUT)
        yield from tune(md=md)
        if not axis.tuner.tune_ok:
            logger.warning("!!! tune failed for axis %s !!!", axis.name)
            # if NOTIFY_ON_BADTUNE:
            #     email_notices.send(
            #         f"USAXS tune failed for axis {axis.name}",
            #         f"USAXS tune failed for axis {axis.name}",
            #     )

        # If we don't wait, the next tune often fails
        # intensity stays flat, statistically
        # We need to wait a short bit to allow EPICS database
        # to complete processing and report back to us.
        yield from bps.sleep(1)
    # tune a2rp one more time as final step, we will see if it is needed...
    # yield from bps.mv(usaxs_shutter, "open", timeout=MASTER_TIMEOUT)
    # yield from tune_a2rp(md=md)
    # if not axis.tuner.tune_ok:
    #    logger.warning("!!! tune failed for axis %s !!!", "a2rp")
    # yield from bps.sleep(1)
    # yield from bps.remove_suspender(suspend_BeamInHutch)

    logger.info("USAXS count time: %s second(s)", terms.USAXS.usaxs_time.get())
    yield from bps.mv(
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
    )
    yield from user_data.set_state_plan("pre-USAXS optics tune")


@bpp.suspend_decorator(suspend_FE_shutter)
@bpp.suspend_decorator(suspend_BeamInHutch)
def allUSAXStune(
    md: Optional[Dict[str, Any]] = None,
    RE: Optional[Any] = None,
    bec: Optional[Any] = None,
    specwriter: Optional[Any] = None,
):
    """
    Tune mr, ar, a2rp, ar, a2rp USAXS optics.

    Parameters
    ----------
    md : Optional[Dict[str, Any]], optional
        Metadata dictionary, by default None
    RE : Optional[Any], optional
        Bluesky RunEngine instance, by default None
    bec : Optional[Any], optional
        Bluesky Live Callbacks instance, by default None
    specwriter : Optional[Any], optional
        SPEC file writer instance, by default None

    Returns
    -------
    Generator[Any, None, None]
        A generator that yields plan steps

    USAGE:  ``RE(allUSAXStune())``
    """



    yield from bps.mv(
        monochromator.feedback.on,
        MONO_FEEDBACK_ON,
        mono_shutter,
        "open",
        ccd_shutter,
        "close",
        timeout=MASTER_TIMEOUT,
    )
    yield from IfRequestedStopBeforeNextScan(
        oregistry=oregistry
    )  # stop if user chose to do so.

    yield from mode_USAXS(oregistry=oregistry)

    if terms.preUSAXStune.use_specific_location.get() in (1, "yes"):
        yield from bps.mv(
            s_stage.x,
            terms.preUSAXStune.sx.get(),
            s_stage.y,
            terms.preUSAXStune.sy.get(),
            timeout=MASTER_TIMEOUT,
        )

    yield from bps.mv(
        d_stage.x,
        terms.USAXS.DX0.get(),  # TODO: resolve this database issue
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
    )
    yield from user_data.set_state_plan("pre-USAXS optics tune")

    # when all that is complete, then ...
    yield from bps.mv(usaxs_shutter, "open", timeout=MASTER_TIMEOUT)

    # TODO: install suspender using usaxs_CheckBeamStandard.get()

    tuners = OrderedDict()  # list the axes to tune
    tuners[m_stage.r] = tune_mr  # tune M stage to monochromator
    if not m_stage.isChannelCut:
        tuners[m_stage.r2p] = tune_m2rp  # make M stage crystals parallel
    if terms.USAXS.useMSstage.get():
        # tuners[ms_stage.rp] = tune_msrp    # align MSR stage with M stage
        pass
    if terms.USAXS.useSBUSAXS.get():
        # tuners[as_stage.rp] = tune_asrp    # align ASR stage with MSR stage
        pass
    tuners[a_stage.r] = tune_ar  # tune A stage to M stage
    tuners[a_stage.r2p] = tune_a2rp  # make A stage crystals parallel
    tuners[a_stage.r] = tune_ar  # tune A stage to M stage
    tuners[a_stage.r2p] = tune_a2rp  # make A stage crystals parallel

    # now, tune the desired axes, bail out if a tune fails
    # yield from bps.install_suspender(suspend_BeamInHutch)
    for axis, tune in tuners.items():
        yield from bps.mv(usaxs_shutter, "open", timeout=MASTER_TIMEOUT)
        yield from tune(md=md, oregistry=oregistry)
        if not axis.tuner.tune_ok:
            logger.warning("!!! tune failed for axis %s !!!", axis.name)
            if NOTIFY_ON_BADTUNE:
                email_notices.send(
                    f"USAXS tune failed for axis {axis.name}",
                    f"USAXS tune failed for axis {axis.name}",
                )

        # If we don't wait, the next tune often fails
        # intensity stays flat, statistically
        # We need to wait a short bit to allow EPICS database
        # to complete processing and report back to us.
        yield from bps.sleep(1)
    # yield from bps.remove_suspender(suspend_BeamInHutch)

    logger.info("USAXS count time: %s second(s)", terms.USAXS.usaxs_time.get())
    yield from bps.mv(
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
    )
    yield from user_data.set_state_plan("pre-USAXS optics tune")


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -


def preSWAXStune(
    md: Optional[Dict[str, Any]] = None,
    RE: Optional[Any] = None,
    bec: Optional[Any] = None,
    specwriter: Optional[Any] = None,
):
    """
    Tune the SAXS/WAXS optics in any mode, is safe.

    Parameters
    ----------
    md : Optional[Dict[str, Any]], optional
        Metadata dictionary, by default None
    RE : Optional[Any], optional
        Bluesky RunEngine instance, by default None
    bec : Optional[Any], optional
        Bluesky Live Callbacks instance, by default None
    specwriter : Optional[Any], optional
        SPEC file writer instance, by default None

    Returns
    -------
    Generator[Any, None, None]
        A generator that yields plan steps

    USAGE:  ``RE(preSWAXStune())``
    """
    if md is None:
        md = {}
    if RE is None:
        raise ValueError("RunEngine instance must be provided")
    if bec is None:
        raise ValueError("Bluesky Live Callbacks instance must be provided")
    if specwriter is None:
        raise ValueError("SPEC file writer instance must be provided")



    yield from bps.mv(
        monochromator.feedback.on,
        MONO_FEEDBACK_ON,
        mono_shutter,
        "open",
        ccd_shutter,
        "close",
        timeout=MASTER_TIMEOUT,
    )
    yield from IfRequestedStopBeforeNextScan(
        oregistry=oregistry
    )  # stop if user chose to do so.

    if terms.preUSAXStune.use_specific_location.get() in (1, "yes"):
        yield from bps.mv(
            s_stage.x,
            terms.preUSAXStune.sx.get(),
            s_stage.y,
            terms.preUSAXStune.sy.get(),
            timeout=MASTER_TIMEOUT,
        )

    yield from bps.mv(
        user_data.time_stamp,
        str(datetime.datetime.now()),
        scaler0.preset_time,
        0.1,
        timeout=MASTER_TIMEOUT,
    )
    yield from user_data.set_state_plan("pre-SWAXS optics tune")

    # when all that is complete, then ...
    yield from bps.mv(usaxs_shutter, "open", timeout=MASTER_TIMEOUT)

    # TODO: install suspender using usaxs_CheckBeamStandard.get()

    tuners = OrderedDict()  # list the axes to tune
    tuners[m_stage.r] = tune_mr  # tune M stage to monochromator
    if not m_stage.isChannelCut:
        tuners[m_stage.r2p] = tune_m2rp  # make M stage crystals parallel
    if terms.USAXS.useMSstage.get():
        tuners[ms_stage.rp] = tune_msrp  # align MSR stage with M stage

    # now, tune the desired axes, bail out if a tune fails
    yield from bps.install_suspender(suspend_BeamInHutch)
    for axis, tune in tuners.items():
        yield from bps.mv(usaxs_shutter, "open", timeout=MASTER_TIMEOUT)
        yield from tune(md=md, oregistry=oregistry)
        if axis.tuner.tune_ok:
            # If we don't wait, the next tune often fails
            # intensity stays flat, statistically
            # We need to wait a short bit to allow EPICS database
            # to complete processing and report back to us.
            yield from bps.sleep(1)
        else:
            logger.warning("!!! tune failed for axis %s !!!", axis.name)
            # break
    yield from bps.remove_suspender(suspend_BeamInHutch)

    logger.info("USAXS count time: %s second(s)", terms.USAXS.usaxs_time.get())
    yield from bps.mv(
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
    )
    yield from user_data.set_state_plan("pre-SWAXS optics tune")
