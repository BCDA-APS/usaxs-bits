"""
Plans for axis tuning in USAXS.

Provides Bluesky plans that tune and calibrate individual optomechanical axes
using ``apstools.plans.lineup2``.  Each public function tunes one axis (or a
related group) and updates the corresponding EPICS parameter PV on success.

Public entry points
-------------------
* ``tune_mr``           — monochromator rotation (MR)
* ``tune_ar``           — analyzer rotation (AR)
* ``find_ar``           — wide-range AR search followed by a fine tune_ar
* ``tune_a2rp``         — analyzer second roll-pitch piezo (A2RP)
* ``find_a2rp``         — wide-range A2RP search followed by a fine tune_a2rp
* ``tune_dx``           — detector X stage
* ``tune_dy``           — detector Y stage
* ``tune_diode``        — both DX and DY (calls tune_dx then tune_dy)
* ``tune_usaxs_optics`` — full USAXS optics sequence (MR → AR → A2RP)
* ``tune_saxs_optics``  — SAXS optics sequence (MR only)

Utility stubs (not yet implemented)
-------------------------------------
* ``instrument_default_tune_ranges`` — no-op; ranges live in EPICS PVs
* ``update_EPICS_tuning_widths``     — no-op; now handled by EPICS
* ``user_defined_settings``          — hook for user overrides before each batch

Note: do not use blocking calls in these plans.
"""

import logging
import time
from typing import Optional

from apsbits.core.instrument_init import oregistry
from apstools.callbacks.scan_signal_statistics import SignalStatsCallback
from apstools.plans import lineup2
from apstools.utils import trim_plot_by_name
from bluesky import plan_stubs as bps

from .amplifiers_plan import autoscale_amplifiers
from .mode_changes import mode_USAXS
from .requested_stop import IfRequestedStopBeforeNextScan

# Device instances
I0_controls = oregistry["I0_controls"]
I00_controls = oregistry["I00_controls"]
upd_controls = oregistry["upd_controls"]

terms = oregistry["terms"]
scaler0 = oregistry["scaler0"]
mono_shutter = oregistry["mono_shutter"]
usaxs_shutter = oregistry["usaxs_shutter"]
a_stage = oregistry["a_stage"]
d_stage = oregistry["d_stage"]
m_stage = oregistry["m_stage"]
s_stage = oregistry["s_stage"]
usaxs_q_calc = oregistry["usaxs_q_calc"]
UPD_SIGNAL = oregistry["UPD_SIGNAL"]
UPD = oregistry["UPD"]
I0_SIGNAL = oregistry["I0_SIGNAL"]
I0 = oregistry["I0"]
upd_photocurrent_calc = oregistry["upd_photocurrent_calc"]
I0_photocurrent_calc = oregistry["I0_photocurrent_calc"]

user_data = oregistry["user_data"]
monochromator = oregistry["monochromator"]

logger = logging.getLogger(__name__)


def tune_mr(md: Optional[dict] = None):
    """Bluesky plan: tune the monochromator rotation (MR) stage.

    Opens the USAXS shutter, autoscales the UPD and I0 amplifiers, then runs
    a ``lineup2`` scan over the MR tune range.  On success, writes the new
    center position to ``terms.USAXS.mr_val_center``.

    Parameters
    ----------
    md : dict or None
        Extra metadata merged into the run's start document.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    if md is None:
        md = {}

    yield from IfRequestedStopBeforeNextScan()
    try:
        yield from bps.mv(usaxs_shutter, "open")
        yield from bps.mv(scaler0.preset_time, 0.1)
        yield from bps.mv(upd_controls.auto.mode, "manual")
        md["plan_name"] = "tune_mr"
        logger.info(f"tuning axis: {m_stage.r.name}")

        yield from autoscale_amplifiers([upd_controls, I0_controls])
        scaler0.select_channels(["I0"])
        trim_plot_by_name(5)
        stats = SignalStatsCallback()
        yield from lineup2(
            [I0, scaler0],
            m_stage.r,
            -m_stage.r.tune_range.get(),
            m_stage.r.tune_range.get(),
            31,
            nscans=1,
            signal_stats=stats,
            md=md,
        )
        print(stats.report())
        yield from bps.mv(
            usaxs_shutter,
            "close",
            scaler0.count_mode,
            "AutoCount",
            upd_controls.auto.mode,
            "auto+background",
        )
        scaler0.select_channels()
        if stats.analysis.success:
            yield from bps.mv(terms.USAXS.mr_val_center, m_stage.r.position)
            logger.debug(f"final position: {m_stage.r.position}")
        else:
            print(f"tune_mr failed for {stats.analysis.reasons}")

    except Exception as e:
        logger.error(f"Error in tune_mr: {e}")
        raise
    finally:
        yield from bps.mv(usaxs_shutter, "close")


def tune_ar(md: Optional[dict] = None):
    """Bluesky plan: tune the analyzer rotation (AR) stage.

    Opens the mono and USAXS shutters, autoscales the UPD and I0 amplifiers,
    then runs a ``lineup2`` scan over the AR tune range.  On success, writes
    the new center to ``terms.USAXS.ar_val_center`` and to
    ``usaxs_q_calc.channels.B.input_value``.

    Parameters
    ----------
    md : dict or None
        Extra metadata merged into the run's start document.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    if md is None:
        md = {}
    success = False
    try:
        yield from bps.mv(usaxs_shutter, "open")
        yield from bps.mv(scaler0.preset_time, 0.1)
        yield from bps.mv(upd_controls.auto.mode, "manual")
        md["plan_name"] = "tune_ar"
        yield from IfRequestedStopBeforeNextScan()
        logger.info(f"tuning axis: {a_stage.r.name}")
        yield from bps.mv(
            mono_shutter,
            "open",
            usaxs_shutter,
            "open",
        )
        yield from autoscale_amplifiers([upd_controls, I0_controls])
        trim_plot_by_name(5)
        scaler0.select_channels(["UPD"])
        stats = SignalStatsCallback()
        yield from lineup2(
            [UPD, scaler0],
            a_stage.r,
            -a_stage.r.tune_range.get(),
            a_stage.r.tune_range.get(),
            31,
            nscans=1,
            signal_stats=stats,
            md=md,
        )
        print(stats.report())
        yield from bps.mv(
            usaxs_shutter,
            "close",
            scaler0.count_mode,
            "AutoCount",
            upd_controls.auto.mode,
            "auto+background",
        )
        scaler0.select_channels()
        success = stats.analysis.success
        print(f"Result: {success}")
        if success:
            yield from bps.mv(
                # fmt: off
                terms.USAXS.ar_val_center,
                a_stage.r.position,
                usaxs_q_calc.channels.B.input_value,
                a_stage.r.position,
                # fmt: on
            )
            logger.debug(f"final position: {a_stage.r.position}")
        else:
            logger.info(f"tune_ar failed for {stats.analysis.reasons}")

    except Exception as e:
        logger.error(f"Error in tune_ar: {str(e)}")
        raise


def find_ar(md: Optional[dict] = None):
    """Bluesky plan: wide-range AR search followed by a fine tune_ar.

    Uses ``upd_photocurrent_calc`` (UPD amplifier in automatic gain mode) to
    search over a range 5× wider than the normal AR tune range, running up to
    3 ``lineup2`` scans to narrow in.  Then replicates the standard ``tune_ar``
    sequence at normal range and gain settings.

    Use this when ``tune_ar`` fails because the peak is outside the normal
    search window.

    Parameters
    ----------
    md : dict or None
        Extra metadata merged into the run's start document.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    howWiderRangeToScan = 5
    howManyPoints = 61
    if md is None:
        md = {}
    success = False
    try:
        yield from bps.mv(usaxs_shutter, "open")
        yield from bps.mv(scaler0.preset_time, 0.2)
        md["plan_name"] = "find_ar"
        yield from IfRequestedStopBeforeNextScan()
        logger.info(f"tuning axis: {a_stage.r.name}")
        yield from bps.mv(
            mono_shutter,
            "open",
            usaxs_shutter,
            "open",
            upd_controls.auto.mode,
            "automatic",  # set UPD amplifier to automatic so it does not saturate
        )
        # NOTE: do NOT call autoscale_amplifiers here — it forces manual mode,
        # which prevents the automatic gain-ranging needed for the wide scan.
        trim_plot_by_name(5)
        # control BEC plotting since we use upd_photocurrent_calc
        scaler0.kind = "normal"
        scaler0.select_channels([])         # no scaler channels plotted
        stats = SignalStatsCallback()
        yield from lineup2(
            [upd_photocurrent_calc, scaler0],
            a_stage.r,
            -1 * howWiderRangeToScan * a_stage.r.tune_range.get(),
            howWiderRangeToScan * a_stage.r.tune_range.get(),
            howManyPoints,
            nscans=3,
            signal_stats=stats,
            md=md,
        )
        print(stats.report())
        # Now run a standard tune_ar at normal range and gain settings.
        yield from bps.mv(scaler0.preset_time, 0.1)
        yield from bps.mv(
            mono_shutter,
            "open",
            usaxs_shutter,
            "open",
        )
        yield from autoscale_amplifiers([upd_controls, I0_controls])
        trim_plot_by_name(5)
        scaler0.select_channels(["UPD"])
        stats = SignalStatsCallback()
        yield from lineup2(
            [UPD, scaler0],
            a_stage.r,
            -a_stage.r.tune_range.get(),
            a_stage.r.tune_range.get(),
            31,
            nscans=1,
            signal_stats=stats,
            md=md,
        )
        print(stats.report())
        yield from bps.mv(
            usaxs_shutter,
            "close",
            scaler0.count_mode,
            "AutoCount",
            upd_controls.auto.mode,
            "auto+background",
        )
        scaler0.select_channels()
        success = stats.analysis.success
        print(f"Result: {success}")
        if success:
            yield from bps.mv(
                # fmt: off
                terms.USAXS.ar_val_center,
                a_stage.r.position,
                usaxs_q_calc.channels.B.input_value,
                a_stage.r.position,
                # fmt: on
            )
            logger.debug(f"final position: {a_stage.r.position}")
        else:
            logger.info(f"find_ar failed for {stats.analysis.reasons}")

    except Exception as e:
        logger.error(f"Error in find_ar: {str(e)}")
        raise


def tune_a2rp(md: Optional[dict] = None):
    """Bluesky plan: tune the analyzer second roll-pitch piezo (A2RP).

    Opens the mono and USAXS shutters, autoscales the UPD and I0 amplifiers,
    then runs a ``lineup2`` scan over the A2RP tune range.

    Parameters
    ----------
    md : dict or None
        Extra metadata merged into the run's start document.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    if md is None:
        md = {}
    try:
        yield from bps.mv(usaxs_shutter, "open")
        yield from bps.sleep(0.1)  # piezo is fast, give the system time to react
        yield from bps.mv(scaler0.preset_time, 0.1)
        yield from bps.mv(upd_controls.auto.mode, "manual")
        md["plan_name"] = "tune_a2rp"
        yield from IfRequestedStopBeforeNextScan()
        logger.info(f"tuning axis: {a_stage.r2p.name}")
        yield from bps.mv(
            mono_shutter,
            "open",
            usaxs_shutter,
            "open",
        )
        yield from autoscale_amplifiers([upd_controls, I0_controls])
        scaler0.select_channels(["UPD"])
        trim_plot_by_name(5)
        stats = SignalStatsCallback()
        yield from lineup2(
            [UPD, scaler0],
            a_stage.r2p,
            -a_stage.r2p.tune_range.get(),
            a_stage.r2p.tune_range.get(),
            31,
            nscans=1,
            signal_stats=stats,
            md=md,
        )
        print(stats.report())
        yield from bps.mv(
            usaxs_shutter,
            "close",
            scaler0.count_mode,
            "AutoCount",
            upd_controls.auto.mode,
            "auto+background",
        )
        scaler0.select_channels()
        if stats.analysis.success:
            logger.debug(f"final position: {a_stage.r2p.position}")
        else:
            print(f"tune_a2rp failed for {stats.analysis.reasons}")

    except Exception as e:
        logger.error(f"Error in tune_a2rp: {str(e)}")
        raise


def find_a2rp(md: Optional[dict] = None):
    """Bluesky plan: wide-range A2RP search followed by a fine tune_a2rp.

    Uses ``upd_photocurrent_calc`` (UPD amplifier in automatic gain mode) to
    search over a range 2.5× wider than the normal A2RP tune range, running
    up to 3 ``lineup2`` scans to narrow in.  Then replicates the standard
    ``tune_a2rp`` sequence at normal range and gain settings.

    The wide-scan start is clamped so it cannot drive the axis into a negative
    absolute position; the wide-scan end is clamped at 88 (hardware limit).

    Parameters
    ----------
    md : dict or None
        Extra metadata merged into the run's start document.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    howWiderRangeToScan = 2.5
    howManyPoints = 61
    if md is None:
        md = {}
    success = False
    try:
        yield from bps.mv(usaxs_shutter, "open")
        yield from bps.mv(scaler0.preset_time, 0.2)
        md["plan_name"] = "find_a2rp"
        yield from IfRequestedStopBeforeNextScan()
        logger.info(f"tuning axis: {a_stage.r2p.name}")
        axis_start = a_stage.r2p.position
        yield from bps.mv(
            mono_shutter,
            "open",
            usaxs_shutter,
            "open",
            upd_controls.auto.mode,
            "automatic",  # set UPD amplifier to automatic so it does not saturate
        )
        # NOTE: do NOT call autoscale_amplifiers here — it forces manual mode,
        # which prevents the automatic gain-ranging needed for the wide scan.
        trim_plot_by_name(5)
        # control BEC plotting since we use upd_photocurrent_calc
        scaler0.kind = "normal"
        scaler0.select_channels([])         # no scaler channels plotted
        stats = SignalStatsCallback()
        tune_start = -1 * howWiderRangeToScan * a_stage.r2p.tune_range.get()
        tune_end = howWiderRangeToScan * a_stage.r2p.tune_range.get()
        # tune_start must be larger than -1*axis_start (avoid driving axis negative)
        tune_start = max(tune_start, -1 * axis_start)
        tune_end = min(tune_end, 88)
        yield from lineup2(
            [upd_photocurrent_calc, scaler0],
            a_stage.r2p, tune_start, tune_end, howManyPoints,
            nscans=3, signal_stats=stats,
            md=md,
        )
        print(stats.report())
        # Now run a standard tune_a2rp at normal range and gain settings.
        yield from bps.mv(scaler0.preset_time, 0.1)
        yield from bps.mv(
            mono_shutter,
            "open",
            usaxs_shutter,
            "open",
        )

        yield from autoscale_amplifiers([upd_controls, I0_controls])
        scaler0.select_channels(["UPD"])
        trim_plot_by_name(5)
        stats = SignalStatsCallback()
        yield from lineup2(
            [UPD, scaler0],
            a_stage.r2p,
            -a_stage.r2p.tune_range.get(),
            a_stage.r2p.tune_range.get(),
            31,
            nscans=1,
            signal_stats=stats,
            md=md,
        )
        print(stats.report())
        yield from bps.mv(
            usaxs_shutter,
            "close",
            scaler0.count_mode,
            "AutoCount",
            upd_controls.auto.mode,
            "auto+background",
        )
        scaler0.select_channels()
        if stats.analysis.success:
            logger.debug(f"final position: {a_stage.r2p.position}")
        else:
            print(f"tune_a2rp failed for {stats.analysis.reasons}")

    except Exception as e:
        logger.error(f"Error in find_ar: {str(e)}")
        raise


def tune_dx(md: Optional[dict] = None):
    """Bluesky plan: tune the detector X (DX) stage.

    Opens the mono and USAXS shutters, autoscales the UPD and I0 amplifiers,
    then runs a ``lineup2`` scan over the DX tune range.  On success, writes
    the new center position to ``terms.USAXS.DX0``.

    Parameters
    ----------
    md : dict or None
        Extra metadata merged into the run's start document.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    if md is None:
        md = {}

    try:
        yield from bps.mv(usaxs_shutter, "open")
        yield from bps.sleep(0.1)  # piezo is fast, give the system time to react
        yield from bps.mv(scaler0.preset_time, 0.1)
        yield from bps.mv(upd_controls.auto.mode, "manual")
        md["plan_name"] = "tune_dx"
        yield from IfRequestedStopBeforeNextScan()
        logger.info(f"tuning axis: {d_stage.x.name}")
        yield from bps.mv(
            mono_shutter,
            "open",
            usaxs_shutter,
            "open",
        )
        yield from autoscale_amplifiers([upd_controls, I0_controls])
        trim_plot_by_name(5)
        scaler0.select_channels(["UPD"])
        stats = SignalStatsCallback()
        yield from lineup2(
            [UPD, scaler0],
            d_stage.x,
            -d_stage.x.tune_range.get(),
            d_stage.x.tune_range.get(),
            31,
            nscans=1,
            signal_stats=stats,
            md=md,
        )
        print(stats.report())
        yield from bps.mv(
            usaxs_shutter,
            "close",
            scaler0.count_mode,
            "AutoCount",
            upd_controls.auto.mode,
            "auto+background",
        )
        scaler0.select_channels()
        if stats.analysis.success:
            yield from bps.mv(
                terms.USAXS.DX0,
                d_stage.x.position,
            )
            logger.info(f"final position: {d_stage.x.position}")
        else:
            logger.info(f"tune_dx failed for {stats.analysis.reasons}")

    except Exception as e:
        logger.error(f"Error in tune_dx: {str(e)}")
        raise


def tune_dy(md: Optional[dict] = None):
    """Bluesky plan: tune the detector Y (DY) stage.

    Opens the mono and USAXS shutters, autoscales the UPD and I0 amplifiers,
    then runs a ``lineup2`` scan over the DY tune range.  On success, writes
    the new center position to ``terms.SAXS.dy_in``.

    Parameters
    ----------
    md : dict or None
        Extra metadata merged into the run's start document.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    if md is None:
        md = {}

    try:
        yield from bps.mv(usaxs_shutter, "open")
        yield from bps.sleep(0.1)  # piezo is fast, give the system time to react
        yield from bps.mv(scaler0.preset_time, 0.1)
        yield from bps.mv(upd_controls.auto.mode, "manual")
        md["plan_name"] = "tune_dy"
        yield from IfRequestedStopBeforeNextScan()
        logger.info(f"tuning axis: {d_stage.y.name}")
        yield from bps.mv(
            mono_shutter,
            "open",
            usaxs_shutter,
            "open",
        )
        yield from autoscale_amplifiers([upd_controls, I0_controls])
        scaler0.select_channels(["UPD"])
        trim_plot_by_name(5)
        stats = SignalStatsCallback()
        yield from lineup2(
            [UPD, scaler0],
            d_stage.y,
            -d_stage.y.tune_range.get(),
            d_stage.y.tune_range.get(),
            31,
            nscans=1,
            signal_stats=stats,
            md=md,
        )
        print(stats.report())
        yield from bps.mv(
            usaxs_shutter,
            "close",
            scaler0.count_mode,
            "AutoCount",
            upd_controls.auto.mode,
            "auto+background",
        )
        scaler0.select_channels()
        if stats.analysis.success:
            yield from bps.mv(terms.SAXS.dy_in, d_stage.y.position)
            logger.info(f"final position: {d_stage.y.position}")
        else:
            logger.info(f"tune_dy failed for {stats.analysis.reasons}")

    except Exception as e:
        logger.error(f"Error in tune_dy: {str(e)}")
        raise


def tune_diode(md: Optional[dict] = None):
    """Bluesky plan: tune both the DX and DY detector stages.

    Calls ``tune_dx`` then ``tune_dy`` in sequence.

    Parameters
    ----------
    md : dict or None
        Extra metadata merged into the run's start document.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    if md is None:
        md = {}

    try:
        yield from tune_dx(md=md)
        yield from tune_dy(md=md)

    except Exception as e:
        logger.error(f"Error in tune_diode: {str(e)}")
        raise


def tune_usaxs_optics(side: bool = False, md: Optional[dict] = None):
    """Bluesky plan: tune the full USAXS optics sequence.

    Switches the instrument to USAXS mode, then tunes in optical-path order:
    MR → AR → A2RP.  Updates ``terms.preUSAXStune`` timestamps on completion.

    Parameters
    ----------
    side : bool
        Reserved for future side-bounce tuning (MSRP/ASRP); currently unused.
    md : dict or None
        Extra metadata merged into the run's start document.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    if md is None:
        md = {}

    try:
        yield from mode_USAXS()

        yield from tune_mr(md=md)
        yield from tune_ar(md=md)
        yield from tune_a2rp(md=md)

        yield from bps.mv(
            terms.preUSAXStune.num_scans_last_tune,
            0,
            terms.preUSAXStune.epoch_last_tune,
            time.time(),
        )

    except Exception as e:
        logger.error(f"Error in tune_usaxs_optics: {str(e)}")
        raise


def tune_saxs_optics(md: Optional[dict] = None):
    """Bluesky plan: tune the SAXS optics sequence.

    Tunes the monochromator rotation (MR) and updates the tune timestamp.
    SAXS does not require AR or A2RP tuning.

    Parameters
    ----------
    md : dict or None
        Extra metadata merged into the run's start document.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    if md is None:
        md = {}

    try:
        yield from tune_mr(md=md)
        yield from bps.mv(
            terms.preUSAXStune.epoch_last_tune,
            time.time(),
        )

    except Exception as e:
        logger.error(f"Error in tune_saxs_optics: {str(e)}")
        raise


def instrument_default_tune_ranges():
    """Bluesky plan: no-op stub — tune ranges are now stored in EPICS PVs.

    Previously this function computed energy-dependent tune ranges from the
    monochromator position and wrote them to local device objects.  That logic
    has been superseded: tune ranges are now configured directly via
    ``axis_tune_range.*`` EPICS PVs and read by ``TunableEpicsMotor2.tune_range``
    at plan time.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    try:
        yield from bps.null()

    except Exception as e:
        logger.error(f"Error in instrument_default_tune_ranges: {str(e)}")
        raise


def update_EPICS_tuning_widths():
    """Bluesky plan: no-op stub — tuning widths are now managed in EPICS.

    Previously this function pushed local tuner width values back to the
    ``axis_tune_range.*`` EPICS PVs.  Width management is now handled
    directly in EPICS; this stub is retained for call-site compatibility.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    try:
        yield from bps.null()

    except Exception as e:
        logger.error(f"Error in update_EPICS_tuning_widths: {str(e)}")
        raise


def user_defined_settings():
    """Bluesky plan: hook for user overrides before each measurement batch.

    Called from ``beforePlan()`` at the start of every batch set of
    measurements.  Users may override instrument defaults here (e.g. tune
    ranges for optical axes).

    **Important:** do not use any blocking calls (``time.sleep()``, direct
    EPICS ``get``/``put``, file I/O) inside this plan — they will stall the
    RunEngine.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    try:
        yield from bps.null()

    except Exception as e:
        logger.error(f"Error in user_defined_settings: {str(e)}")
        raise
