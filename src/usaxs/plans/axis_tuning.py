"""
Plans for axis tuning in USAXS.

Provides Bluesky plans that tune and calibrate individual optomechanical axes
using ``apstools.plans.lineup2``.  Each public function tunes one axis (or a
related group) and updates the corresponding EPICS parameter PV on success.

Public entry points
-------------------
* ``tune_mr``           — monochromator rotation (MR)
* ``find_mr``           — wide-range MR search followed by a fine tune_mr
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

import numpy as np
from apsbits.core.instrument_init import oregistry
from apstools.callbacks.scan_signal_statistics import SignalStatsCallback
from apstools.plans import lineup2
from apstools.utils import trim_plot_by_name
from bluesky import plan_stubs as bps
from bluesky import plans as bp
from bluesky import preprocessors as bpp

from ..devices.fx4_quadem import FX4AutorangeDirection
from ..utils.fx4_channels import select_fx4_plot
from ..utils.peak_search import FLAT
from ..utils.peak_search import HIGH_EDGE
from ..utils.peak_search import INSIDE
from ..utils.peak_search import locate_peak
from .fx4_autorange_plan import autoscale_amplifiers
from .fx4_setup import autorange_hold_for_peak
from .fx4_setup import enable_fx4_autorange
from .fx4_setup import prepare_fx4_counting
from .fx4_setup import resume_fx4_monitoring
from .fx4_setup import usaxs_electrometers
from .mode_changes import mode_USAXS
from .requested_stop import IfRequestedStopBeforeNextScan

# Device instances
I0_controls = oregistry["I0_controls"]
I00_controls = oregistry["I00_controls"]
upd_controls = oregistry["upd_controls"]

terms = oregistry["terms"]
mono_shutter = oregistry["mono_shutter"]
usaxs_shutter = oregistry["usaxs_shutter"]
a_stage = oregistry["a_stage"]
d_stage = oregistry["d_stage"]
m_stage = oregistry["m_stage"]
s_stage = oregistry["s_stage"]
usaxs_q_calc = oregistry["usaxs_q_calc"]
# UPD and I0 are the FX4 MeanValue signals, named by
# usaxs.utils.fx4_channels.setup_fx4_channels().  They read picoamps directly,
# which is why the old upd_photocurrent_calc / I0_photocurrent_calc swait
# records are gone: those existed only to turn scaler counts plus a Femto gain
# back into a photocurrent, and the FX4 reports one already.
UPD = oregistry["UPD"]
I0 = oregistry["I0"]
# Both electrometers are read at every tune point, so I0 lands in the same
# document as UPD -- the scaler used to give that for free.
FX4_DETECTORS = usaxs_electrometers()

user_data = oregistry["user_data"]
monochromator = oregistry["monochromator"]

logger = logging.getLogger(__name__)


def _travel_window(axis, margin):
    """Absolute (lo, hi) the walk may scan within: soft limits less ``margin``.

    ``margin`` is the axis' tune range, so the fine tune run about the peak
    afterwards cannot reach the end of travel either.  ``None`` when the motor
    has no soft limits set (EPICS uses LLM == HLM for "unlimited").
    """
    lo, hi = axis.limits
    if lo >= hi:
        return None
    return lo + margin, hi - margin


def _walk_to_peak(
    plan_name,
    axis,
    signal,
    detectors,
    half_width,
    npoints,
    max_steps,
    md,
    limits=None,
):
    """Plan: wide-scan ``axis``, stepping uphill until the peak is inside.

    The replacement for a wide ``lineup2``, which accepts a slope as a peak
    and can never look past its first scan (see ``usaxs.utils.peak_search``).
    Each scan spans ±``half_width`` about the current centre.  If the maximum
    of ``signal`` is at an edge, the centre steps 0.9 scan widths that way and
    the scan repeats, at most ``max_steps`` times.

    ``limits`` is an absolute (lo, hi) window (see :func:`_travel_window`).
    Scans are cut off at it, and a peak still climbing at a cut-off edge ends
    the walk: the peak lies beyond the axis' travel.

    Returns (via ``yield from``) the position of the peak, with ``axis``
    already moved there, or ``None`` with ``axis`` back where it started.
    """
    lo, hi = limits if limits is not None else (-np.inf, np.inf)
    start = axis.position
    center = start
    direction = 0
    for step in range(max_steps + 1):
        center = min(max(center, lo), hi)
        rel_lo = max(-half_width, lo - center)
        rel_hi = min(half_width, hi - center)
        yield from IfRequestedStopBeforeNextScan()
        xs, ys, primary = [], [], set()

        def collect(name, doc, xs=xs, ys=ys, primary=primary):
            # Only the scan's own points: the session's supplemental streams
            # (baseline, monitors) emit events too, without these keys.  An
            # exception here would abort the run, so stay defensive.
            if name == "descriptor" and doc.get("name") == "primary":
                primary.add(doc["uid"])
            elif name == "event" and doc["descriptor"] in primary:
                data = doc["data"]
                if axis.name in data and signal.name in data:
                    xs.append(data[axis.name])
                    ys.append(data[signal.name])

        _md = dict(md, plan_name=plan_name, purpose="alignment", find_step=step)
        yield from bps.mv(axis, center)
        yield from bpp.subs_wrapper(
            bp.rel_scan(detectors, axis, rel_lo, rel_hi, npoints, md=_md),
            collect,
        )
        where, x_at_max = locate_peak(xs, ys)
        print(
            f"{plan_name} step {step}: centre {center:.6f},"
            f" max {signal.name} at {x_at_max:.6f} -> {where}"
        )
        if where == FLAT:
            print(f"{plan_name}: no signal to follow; giving up.")
            break
        if where == INSIDE:
            yield from bps.mv(axis, x_at_max)
            return x_at_max
        new_direction = 1 if where == HIGH_EDGE else -1
        if direction and new_direction != direction:
            # The previous scan pointed here and this one points back: the
            # peak sits in the overlap, at this scan's edge.
            yield from bps.mv(axis, x_at_max)
            return x_at_max
        at_limit = rel_hi < half_width if new_direction > 0 else rel_lo > -half_width
        if at_limit:
            end = hi if new_direction > 0 else lo
            print(
                f"{plan_name}: signal still rising at the"
                f" {'upper' if new_direction > 0 else 'lower'} end of"
                f" {axis.name} travel ({end:.6f}, soft limit less one tune"
                f" range).  The peak is beyond what {axis.name} can reach;"
                " realign coarsely before running this again."
            )
            break
        direction = new_direction
        center += direction * 1.8 * half_width
    else:
        print(
            f"{plan_name}: still climbing after {max_steps} steps"
            f" ({'up' if direction > 0 else 'down'}, last centre"
            f" {center - direction * 1.8 * half_width:.6f})."
        )
    print(f"{plan_name}: peak not found; {axis.name} returned to {start:.6f}.")
    yield from bps.mv(axis, start)
    return None


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
        yield from prepare_fx4_counting(0.1)
        md["plan_name"] = "tune_mr"
        logger.info(f"tuning axis: {m_stage.r.name}")

        yield from autoscale_amplifiers([upd_controls, I0_controls])
        # The MR rocking curve is fitted on *I0*, not UPD, so I0's program is
        # the one whose gain must be held: full autoranging cannot follow the
        # climb into the peak and flattens its top.  UPD's program stays on
        # "Both" so a stale seed there still self-corrects.
        yield from autorange_hold_for_peak(I0_controls)
        select_fx4_plot(["I0"])
        trim_plot_by_name(5)
        stats = SignalStatsCallback()
        yield from lineup2(
            [I0, *FX4_DETECTORS],
            m_stage.r,
            -m_stage.r.tune_range.get(),
            m_stage.r.tune_range.get(),
            31,
            nscans=1,
            signal_stats=stats,
            md=md,
        )
        print(stats.report())
        # resume_fx4_monitoring() below restores auto+background *and* clears
        # seq01:dir back to "Both" through enable_fx4_autorange, so there is no
        # separate auto.mode write here -- one that bypassed the chokepoint
        # would leave the direction set.
        yield from bps.mv(usaxs_shutter, "close")
        select_fx4_plot([])
        yield from resume_fx4_monitoring()
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


def find_mr(
    md: Optional[dict] = None,
    range_multiplier: float = 10,
    npoints: int = 81,
):
    """Bluesky plan: wide-range MR search followed by a fine tune_mr.

    Searches for the Bragg peak of the monochromator over a range
    ``range_multiplier`` times wider than the normal MR tune range
    (``usxLAX:USAXS:tune_mr_range``, 0.0035 deg).  If the maximum is at an
    edge of that scan, MR steps that way and scans again, up to 4 times
    (``_walk_to_peak``), never past its soft limits less one tune range.  Once
    the peak is inside a scan, MR moves to its maximum and the standard
    ``tune_mr`` sequence runs at normal range and gain settings, so on success
    ``terms.USAXS.mr_val_center`` holds the fine-tuned centre.

    Like ``tune_mr`` -- and unlike ``find_ar`` -- the signal fitted is **I0**,
    the first electrometer downstream of the monochromator, so the I0 sequence
    program is the one configured here.

    Use this when ``tune_mr`` fails because the Bragg peak is outside the
    normal search window: after an energy change, or after MR has been left
    stranded.

    If the walk finds no peak, MR is returned to its starting position and
    the fine tune is skipped.

    Parameters
    ----------
    md : dict or None
        Extra metadata merged into the run's start document.
    range_multiplier : float
        How much wider than the normal MR tune range the first scan sweeps.
        Widen it when the peak is still not found.
    npoints : int
        Points in the wide scan.  Keep the step well under the rocking-curve
        width when widening the range.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    maxWalkSteps = 4
    if md is None:
        md = {}
    try:
        yield from bps.mv(usaxs_shutter, "open")
        yield from prepare_fx4_counting(0.2)
        md["plan_name"] = "find_mr"
        yield from IfRequestedStopBeforeNextScan()
        logger.info(f"tuning axis: {m_stage.r.name}")
        yield from bps.mv(
            mono_shutter,
            "open",
            usaxs_shutter,
            "open",
        )
        # Let the sequence program keep ranging as the wide scan sweeps off the
        # Bragg peak and back.  Via enable_fx4_autorange, so seq01:channel on
        # fx42 is pointed at I0 -- the signal this scan is fitting.
        #
        # "Both" is deliberate, as in find_ar: this half is looking for a peak
        # somewhere in a large space, not measuring a profile, so a range that
        # follows the signal over several decades is what finds it.
        yield from enable_fx4_autorange(
            I0_controls, "automatic", FX4AutorangeDirection.both
        )
        # NOTE: do NOT call autoscale_amplifiers here -- it ends in manual
        # mode, and the wide scan needs the sequence program to keep
        # re-ranging as the signal sweeps over several decades.
        trim_plot_by_name(5)
        select_fx4_plot(["I0"])
        peak = yield from _walk_to_peak(
            "find_mr",
            m_stage.r,
            I0,
            [I0, *FX4_DETECTORS],
            range_multiplier * m_stage.r.tune_range.get(),
            npoints,
            maxWalkSteps,
            md,
            limits=_travel_window(m_stage.r, m_stage.r.tune_range.get()),
        )
        if peak is None:
            yield from bps.mv(usaxs_shutter, "close")
            select_fx4_plot([])
            yield from resume_fx4_monitoring()
            return
        # Now run a standard tune_mr at normal range and gain settings.
        yield from prepare_fx4_counting(0.1)
        yield from bps.mv(
            mono_shutter,
            "open",
            usaxs_shutter,
            "open",
        )
        yield from autoscale_amplifiers([upd_controls, I0_controls])
        # This half is a tune_mr, so its peak profile matters: hold I0's gain,
        # since I0 is the signal being fitted.
        yield from autorange_hold_for_peak(I0_controls)
        trim_plot_by_name(5)
        select_fx4_plot(["I0"])
        stats = SignalStatsCallback()
        yield from lineup2(
            [I0, *FX4_DETECTORS],
            m_stage.r,
            -m_stage.r.tune_range.get(),
            m_stage.r.tune_range.get(),
            31,
            nscans=1,
            signal_stats=stats,
            md=md,
        )
        print(stats.report())
        # resume_fx4_monitoring() restores auto+background and clears
        # seq01:dir; see the note in tune_mr.
        yield from bps.mv(usaxs_shutter, "close")
        select_fx4_plot([])
        yield from resume_fx4_monitoring()
        success = stats.analysis.success
        print(f"Result: {success}")
        if success:
            yield from bps.mv(terms.USAXS.mr_val_center, m_stage.r.position)
            logger.debug(f"final position: {m_stage.r.position}")
        else:
            logger.info(f"find_mr failed for {stats.analysis.reasons}")

    except Exception as e:
        logger.error(f"Error in find_mr: {str(e)}")
        raise
    finally:
        # See tune_ar: the shutter ends closed on every exit path.
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
        yield from prepare_fx4_counting(0.1)
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
        # Hold UPD's gain through the scan: full autoranging cannot follow the
        # climb into the rocking-curve peak and flattens its top.
        yield from autorange_hold_for_peak(upd_controls)
        trim_plot_by_name(5)
        select_fx4_plot(["UPD"])
        stats = SignalStatsCallback()
        yield from lineup2(
            [UPD, *FX4_DETECTORS],
            a_stage.r,
            -a_stage.r.tune_range.get(),
            a_stage.r.tune_range.get(),
            31,
            nscans=1,
            signal_stats=stats,
            md=md,
        )
        print(stats.report())
        # resume_fx4_monitoring() restores auto+background and clears
        # seq01:dir; see the note in tune_mr.
        yield from bps.mv(usaxs_shutter, "close")
        select_fx4_plot([])
        yield from resume_fx4_monitoring()
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
    finally:
        # The Uniblitz protects the diode and the sample, so it ends closed
        # whatever happened -- a failed lineup2, a RequestAbort, Ctrl-C.
        yield from bps.mv(usaxs_shutter, "close")


def find_ar(md: Optional[dict] = None):
    """Bluesky plan: wide-range AR search followed by a fine tune_ar.

    Searches on UPD, with its FX4 sequence program autoranging in both
    directions, over a range 5× wider than the normal AR tune range.  If the
    maximum is at an edge of that scan -- the scan saw only the flank of the
    rocking curve -- AR steps that way and scans again, up to 4 times
    (``_walk_to_peak``), never past its soft limits less one tune range.  Once the peak is inside a scan, AR moves to its
    maximum and the standard ``tune_ar`` sequence runs at normal range and
    gain settings.

    If the walk finds no peak, AR is returned to its starting position, the
    fine tune is skipped and ``ARcenter`` is not written.

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
    maxWalkSteps = 4
    if md is None:
        md = {}
    success = False
    try:
        yield from bps.mv(usaxs_shutter, "open")
        yield from prepare_fx4_counting(0.2)
        md["plan_name"] = "find_ar"
        yield from IfRequestedStopBeforeNextScan()
        logger.info(f"tuning axis: {a_stage.r.name}")
        yield from bps.mv(
            mono_shutter,
            "open",
            usaxs_shutter,
            "open",
        )
        # Let the sequence program keep ranging as the wide scan sweeps over
        # several decades.  Via enable_fx4_autorange, so seq01:channel is
        # pointed at UPD first -- after a transmission measurement it is on
        # TRD, and ranging for the transmitted beam would wreck this scan.
        #
        # "Both" is deliberate and is the one tune that does *not* hold its
        # gain: this scan is looking for a peak somewhere in a large space, not
        # measuring a profile, so a range that follows the signal over several
        # decades is exactly what finds it.
        yield from enable_fx4_autorange(
            upd_controls, "automatic", FX4AutorangeDirection.both
        )
        # NOTE: do NOT call autoscale_amplifiers here -- it ends in manual
        # mode, and the wide scan needs the sequence program to keep
        # re-ranging as the signal sweeps over several decades.
        trim_plot_by_name(5)
        select_fx4_plot(["UPD"])
        peak = yield from _walk_to_peak(
            "find_ar",
            a_stage.r,
            UPD,
            [UPD, *FX4_DETECTORS],
            howWiderRangeToScan * a_stage.r.tune_range.get(),
            howManyPoints,
            maxWalkSteps,
            md,
            limits=_travel_window(a_stage.r, a_stage.r.tune_range.get()),
        )
        if peak is None:
            yield from bps.mv(usaxs_shutter, "close")
            select_fx4_plot([])
            yield from resume_fx4_monitoring()
            return
        # Now run a standard tune_ar at normal range and gain settings.
        yield from prepare_fx4_counting(0.1)
        yield from bps.mv(
            mono_shutter,
            "open",
            usaxs_shutter,
            "open",
        )
        yield from autoscale_amplifiers([upd_controls, I0_controls])
        # This half is a tune_ar, so its peak profile matters: hold UPD's gain.
        yield from autorange_hold_for_peak(upd_controls)
        trim_plot_by_name(5)
        select_fx4_plot(["UPD"])
        stats = SignalStatsCallback()
        yield from lineup2(
            [UPD, *FX4_DETECTORS],
            a_stage.r,
            -a_stage.r.tune_range.get(),
            a_stage.r.tune_range.get(),
            31,
            nscans=1,
            signal_stats=stats,
            md=md,
        )
        print(stats.report())
        # resume_fx4_monitoring() restores auto+background and clears
        # seq01:dir; see the note in tune_mr.
        yield from bps.mv(usaxs_shutter, "close")
        select_fx4_plot([])
        yield from resume_fx4_monitoring()
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
    finally:
        # See tune_ar: the shutter ends closed on every exit path.
        yield from bps.mv(usaxs_shutter, "close")


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
        yield from prepare_fx4_counting(0.1)
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
        # Hold UPD's gain through the scan; see the note in tune_ar.
        yield from autorange_hold_for_peak(upd_controls)
        select_fx4_plot(["UPD"])
        trim_plot_by_name(5)
        stats = SignalStatsCallback()
        yield from lineup2(
            [UPD, *FX4_DETECTORS],
            a_stage.r2p,
            -a_stage.r2p.tune_range.get(),
            a_stage.r2p.tune_range.get(),
            31,
            nscans=1,
            signal_stats=stats,
            md=md,
        )
        print(stats.report())
        # resume_fx4_monitoring() restores auto+background and clears
        # seq01:dir; see the note in tune_mr.
        yield from bps.mv(usaxs_shutter, "close")
        select_fx4_plot([])
        yield from resume_fx4_monitoring()
        if stats.analysis.success:
            logger.debug(f"final position: {a_stage.r2p.position}")
        else:
            print(f"tune_a2rp failed for {stats.analysis.reasons}")

    except Exception as e:
        logger.error(f"Error in tune_a2rp: {str(e)}")
        raise
    finally:
        # See tune_ar: the shutter ends closed on every exit path.
        yield from bps.mv(usaxs_shutter, "close")


def find_a2rp(md: Optional[dict] = None):
    """Bluesky plan: wide-range A2RP search followed by a fine tune_a2rp.

    Searches on UPD, with its FX4 sequence program autoranging in both
    directions, over a range 2.5× wider than the normal A2RP tune range.  If
    the maximum is at an edge of that scan, A2RP steps that way and scans
    again, up to 4 times (``_walk_to_peak``).  Once the peak is inside a scan,
    A2RP moves to its maximum and the standard ``tune_a2rp`` sequence runs at
    normal range and gain settings.

    The walk stays inside the piezo's soft limits (-20..90 um, i.e. -2..9 V)
    less one tune range at each end.  If the signal is still rising at that
    boundary, the peak is out of the piezo's reach: the plan says so, returns
    A2RP to its starting position and skips the fine tune.  Likewise if the
    walk finds no peak at all.

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
    maxWalkSteps = 4
    if md is None:
        md = {}
    try:
        yield from bps.mv(usaxs_shutter, "open")
        yield from prepare_fx4_counting(0.2)
        md["plan_name"] = "find_a2rp"
        yield from IfRequestedStopBeforeNextScan()
        logger.info(f"tuning axis: {a_stage.r2p.name}")
        yield from bps.mv(
            mono_shutter,
            "open",
            usaxs_shutter,
            "open",
        )
        # Let the sequence program keep ranging as the wide scan sweeps over
        # several decades.  Via enable_fx4_autorange, so seq01:channel is
        # pointed at UPD first -- after a transmission measurement it is on
        # TRD, and ranging for the transmitted beam would wreck this scan.
        #
        # "Both" is deliberate: like find_ar, this half searches a large space
        # for a peak rather than measuring a profile, so following the signal
        # across decades is what finds it.
        yield from enable_fx4_autorange(
            upd_controls, "automatic", FX4AutorangeDirection.both
        )
        # NOTE: do NOT call autoscale_amplifiers here -- it ends in manual
        # mode, and the wide scan needs the sequence program to keep
        # re-ranging as the signal sweeps over several decades.
        trim_plot_by_name(5)
        select_fx4_plot(["UPD"])
        # The piezo's travel, -2..9 V = -20..90 um, is its motor's soft
        # limits; a peak beyond it ends the walk with a report rather than
        # running the piezo into an end.
        peak = yield from _walk_to_peak(
            "find_a2rp",
            a_stage.r2p,
            UPD,
            [UPD, *FX4_DETECTORS],
            howWiderRangeToScan * a_stage.r2p.tune_range.get(),
            howManyPoints,
            maxWalkSteps,
            md,
            limits=_travel_window(a_stage.r2p, a_stage.r2p.tune_range.get()),
        )
        if peak is None:
            yield from bps.mv(usaxs_shutter, "close")
            select_fx4_plot([])
            yield from resume_fx4_monitoring()
            return
        # Now run a standard tune_a2rp at normal range and gain settings.
        yield from prepare_fx4_counting(0.1)
        yield from bps.mv(
            mono_shutter,
            "open",
            usaxs_shutter,
            "open",
        )

        yield from autoscale_amplifiers([upd_controls, I0_controls])
        # This half is a tune_a2rp, so its peak profile matters: hold UPD's
        # gain.
        yield from autorange_hold_for_peak(upd_controls)
        select_fx4_plot(["UPD"])
        trim_plot_by_name(5)
        stats = SignalStatsCallback()
        yield from lineup2(
            [UPD, *FX4_DETECTORS],
            a_stage.r2p,
            -a_stage.r2p.tune_range.get(),
            a_stage.r2p.tune_range.get(),
            31,
            nscans=1,
            signal_stats=stats,
            md=md,
        )
        print(stats.report())
        # resume_fx4_monitoring() restores auto+background and clears
        # seq01:dir; see the note in tune_mr.
        yield from bps.mv(usaxs_shutter, "close")
        select_fx4_plot([])
        yield from resume_fx4_monitoring()
        if stats.analysis.success:
            logger.debug(f"final position: {a_stage.r2p.position}")
        else:
            print(f"tune_a2rp failed for {stats.analysis.reasons}")

    except Exception as e:
        logger.error(f"Error in find_a2rp: {str(e)}")
        raise
    finally:
        # See tune_ar: the shutter ends closed on every exit path.
        yield from bps.mv(usaxs_shutter, "close")


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
        yield from prepare_fx4_counting(0.1)
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
        # Hold UPD's gain through the scan; see the note in tune_ar.
        yield from autorange_hold_for_peak(upd_controls)
        trim_plot_by_name(5)
        select_fx4_plot(["UPD"])
        stats = SignalStatsCallback()
        yield from lineup2(
            [UPD, *FX4_DETECTORS],
            d_stage.x,
            -d_stage.x.tune_range.get(),
            d_stage.x.tune_range.get(),
            31,
            nscans=1,
            signal_stats=stats,
            md=md,
        )
        print(stats.report())
        # resume_fx4_monitoring() restores auto+background and clears
        # seq01:dir; see the note in tune_mr.
        yield from bps.mv(usaxs_shutter, "close")
        select_fx4_plot([])
        yield from resume_fx4_monitoring()
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
    finally:
        # See tune_ar: the shutter ends closed on every exit path.
        yield from bps.mv(usaxs_shutter, "close")


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
        yield from prepare_fx4_counting(0.1)
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
        # Hold UPD's gain through the scan; see the note in tune_ar.
        yield from autorange_hold_for_peak(upd_controls)
        select_fx4_plot(["UPD"])
        trim_plot_by_name(5)
        stats = SignalStatsCallback()
        yield from lineup2(
            [UPD, *FX4_DETECTORS],
            d_stage.y,
            -d_stage.y.tune_range.get(),
            d_stage.y.tune_range.get(),
            31,
            nscans=1,
            signal_stats=stats,
            md=md,
        )
        print(stats.report())
        # resume_fx4_monitoring() restores auto+background and clears
        # seq01:dir; see the note in tune_mr.
        yield from bps.mv(usaxs_shutter, "close")
        select_fx4_plot([])
        yield from resume_fx4_monitoring()
        if stats.analysis.success:
            yield from bps.mv(terms.SAXS.dy_in, d_stage.y.position)
            logger.info(f"final position: {d_stage.y.position}")
        else:
            logger.info(f"tune_dy failed for {stats.analysis.reasons}")

    except Exception as e:
        logger.error(f"Error in tune_dy: {str(e)}")
        raise
    finally:
        # See tune_ar: the shutter ends closed on every exit path.
        yield from bps.mv(usaxs_shutter, "close")


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
