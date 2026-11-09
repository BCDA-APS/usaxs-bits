"""
Autoscale and dark-current plans for the FX4 electrometers.

The FX4 replacement for :mod:`usaxs.plans.amplifiers_plan`.  Public names and
signatures are unchanged (``autoscale_amplifiers``, ``measure_background``,
``UPDRange``) so the call sites do not have to change.

Why this is still needed
------------------------
The IOC sequence program ranges the electrometer, but only **after a completed
read** -- exactly like the Femto autoranging it replaces.  Nothing guarantees
the range is right when an exposure begins, so a plan that simply starts
counting can take its first points on the wrong range.  This module forces a
few reads so the sequence program converges before the real measurement.

Two things make that more important than it was, not less:

* **One range serves all four channels of an FX4.**  UPD and TRD share
  ``usxFX4``, and a range that suits the transmitted beam is nowhere near right
  for the scattered one.  Every UPD <-> TRD switch therefore needs both a
  ``seq01:channel`` change and a fresh convergence.
* **Range memory is per channel, not per box.**  ``_last_range_`` is keyed by
  ``(electrometer, channel)`` so that returning to UPD after a transmission
  measurement starts from UPD's own last good range rather than TRD's.

Convergence
-----------
The test is *"has the range stopped changing **and** is the reading not
railed?"*.

Stability alone is not sufficient, and assuming it was cost real data at
12-ID-E.  The loop seeds the range from ``_last_range_`` and the sequence
program cannot react until a read completes, so the first two reads return
the seeded range whether or not it is the right one.  A seed seeded from a
different beam condition -- ``saxsExp`` and ``waxsExp`` both insert filters
*between* the measurement that set the seed and this autoscale -- therefore
looked converged immediately and the exposure ran on a railed I0.

Only the *high* side blocks convergence; see :func:`_reading_above_window`
for why the low side must not.

``max_iterations`` is the backstop, defaulting to twice the range count so a
badly seeded range has room for the full walk plus a confirming read.  With
a good seed it still converges on the second read.
"""

import logging
import time
from typing import Optional

import numpy as np
from apsbits.core.instrument_init import oregistry
from bluesky import RunEngine
from bluesky import plan_stubs as bps
from bluesky.utils import RunEngineControlException
from bluesky.utils import plan

from ..devices.fx4_quadem import MOST_SENSITIVE_RANGE
from ..devices.fx4_quadem import NUM_AUTORANGE_RANGES
from ..devices.fx4_quadem import FX4AutorangeDirection
from ..devices.fx4_quadem import FX4AutorangeSettings
from ..devices.fx4_quadem import FX4AutoscaleError
from ..utils.count_time import quantize_count_time
from ..utils.dark_current import dark_is_acceptable
from ..utils.dark_current import robust_dark_statistics
from ..utils.fx4_ranges import full_scale_pA
from ..utils.obsidian_plan_log import _safe_append
from .fx4_setup import fraction_of_full_scale
from .fx4_setup import fx4_monitor_mode
from .fx4_setup import fx4_scaler_mode
from .fx4_setup import group_controls_by_box
from .fx4_setup import select_fx4_channel

logger = logging.getLogger(__name__)

DEFAULT_AUTOSCALE_COUNT_TIME = 0.05
"""Integration time per trial read, seconds.  Three mains cycles."""

DEFAULT_MAX_ITERATIONS = 2 * NUM_AUTORANGE_RANGES
"""Reads before giving up on convergence.

Enough to walk the whole five-range table from any starting point, confirm
the last move, and still have margin -- the convergence test now also
requires the reading not to be railed, so a badly seeded range needs the
walk *plus* a confirming read rather than stopping at the first repeat.

At the default 0.05 s trial count time the worst case costs well under a
second, and only when the range was wrong to begin with; the normal case
still converges on the second read.
"""

_last_range_ = {}
"""``{(electrometer, channel): range index}`` -- the last converged range.

Module-level so it survives between plan calls.  Keyed per *channel* because
one sequence program serves several, and their correct ranges differ by orders
of magnitude.
"""


def _reading_above_window(control):
    """Return True when the latest reading is railed and a coarser range exists.

    Used as the second half of the convergence test.  The asymmetry is
    deliberate: only the *high* side blocks convergence.

    * **Above** the window means the reading is saturated, the value is
      wrong, and moving to a less sensitive range fixes it.  Worth more
      iterations.
    * **Below** the window means there is little signal -- a disconnected
      detector, a closed shutter, a genuinely weak scatterer.  No range
      change can fix that, and blocking on it would turn "TRD sees nothing"
      into a scan-aborting error.

    Because the FX4 reading is gain-independent, a too-*coarse* range costs
    resolution but not correctness; a railed one corrupts the data.  So this
    is the case worth spending time on.

    Parameters
    ----------
    control : FX4DetectorControls
        The detector being autoscaled.

    Returns
    -------
    bool
        False when the range label cannot be parsed, so an unrecognised
        range never causes the loop to spin.
    """
    fraction = fraction_of_full_scale(control)
    if fraction is None:
        return False
    if abs(fraction) <= control.auto.max_fraction.get():
        return False
    # Index 0 is the *least* sensitive range; nothing coarser to move to.
    try:
        return int(control.auto.lurange.get()) > 0
    except Exception:  # noqa: BLE001 - a bad readback must not spin the loop
        return False


def _memory_key(controls):
    """Return the ``_last_range_`` key for a detector.

    Parameters
    ----------
    controls : FX4DetectorControls
        The detector.

    Returns
    -------
    tuple
        ``(electrometer name, channel number)``.
    """
    return (controls.quadem.name, controls.channel_number)


@plan
def autoscale_amplifiers(
    controls,
    shutter=None,
    count_time: float = DEFAULT_AUTOSCALE_COUNT_TIME,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    RE: Optional[RunEngine] = None,
):
    """Plan: bring each detector's FX4 onto the right range.

    Same signature as the Femto-era plan of this name, so call sites are
    unchanged.  Detectors on a fixed range are skipped, and two autoranged
    detectors on one electrometer is a configuration error rather than a group
    (see :func:`usaxs.plans.fx4_setup.group_controls_by_box`).

    A failure to converge is logged, not raised, so one unhappy channel does
    not abort a scan -- except during user operations, where it raises.

    Parameters
    ----------
    controls : list or tuple of FX4DetectorControls
        Detectors to autoscale.
    shutter : optional
        Opened before autoscaling if given, and left open.
    count_time : float
        Integration time per trial read, seconds.
    max_iterations : int
        Reads before giving up.
    RE : RunEngine, optional
        Used only to keep ``summarize_plan`` from raising.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    if not isinstance(controls, (tuple, list)):
        raise ValueError("controls must be a list or tuple")

    by_box = group_controls_by_box(controls)

    if shutter is not None:
        yield from bps.mv(shutter, "open")

    for control in by_box.values():
        try:
            yield from _autoscale_one_(
                control,
                count_time=count_time,
                max_iterations=max_iterations,
                RE=RE,
            )
        except FX4AutoscaleError as exc:
            logger.warning(
                "%s: %s - will continue despite warning", control.nickname, exc
            )
        except RunEngineControlException:
            raise  # RE.abort()/RE.stop(): never swallow
        except Exception as exc:
            logger.error("%s: %s - will continue anyway", control.nickname, exc)


@plan
def _autoscale_one_(
    control,
    count_time: float = DEFAULT_AUTOSCALE_COUNT_TIME,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    RE: Optional[RunEngine] = None,
):
    """Plan (internal): converge one detector's electrometer onto a range.

    Sequence:

    1. point the sequence program at this detector's channel;
    2. clear ``seq01:dir`` to ``Both``, so the loop may walk the range table
       either way whatever the previous plan left behind;
    3. put it in ``automatic`` and seed the range from this channel's last
       converged value, so the usual case needs one or two reads rather than a
       walk across the table;
    4. read repeatedly -- the sequence program can only act on a *completed*
       read -- until the range repeats;
    5. return it to ``manual`` and restore the count time.  ``dir`` is left at
       ``Both``; a caller that wants the gain held for a peak scan applies
       :func:`usaxs.plans.fx4_setup.autorange_hold_for_peak` afterwards.

    Parameters
    ----------
    control : FX4DetectorControls
        A detector with an autorange sequence program.
    count_time : float
        Integration time per trial read, seconds.
    max_iterations : int
        Reads before giving up.
    RE : RunEngine, optional
        When ``RE.state == "idle"`` the convergence failure is not raised, so
        ``summarize_plan`` stays usable.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.

    Raises
    ------
    FX4AutoscaleError
        If the range never settles and the APS is in user operations.
    """
    det = control.quadem
    auto = control.auto
    key = _memory_key(control)

    original_count_time = det.averaging_time.get()
    trial_count_time = quantize_count_time(count_time)

    # One Range per electrometer: tell the sequence program which channel it is
    # optimising for before anything else.  Skipping this is how UPD ends up
    # ranged for the transmitted beam.
    yield from select_fx4_channel(control)

    yield from bps.mv(det.averaging_time, trial_count_time)
    # The convergence loop has to be free to walk the range table in both
    # directions, so a caller that left the program in "Increase only" (a tune,
    # a transmission measurement) must not constrain it here.  Written
    # unconditionally because seq01:dir is autosaved: this, together with
    # fx4_setup.enable_fx4_autorange, is what stops an aborted tune leaving the
    # instrument increase-only indefinitely.
    yield from bps.mv(auto.direction, FX4AutorangeDirection.both)
    yield from bps.mv(auto.mode, FX4AutorangeSettings.automatic)

    seed = _last_range_.get(key)
    if seed is not None:
        yield from auto.setRange(seed)

    settling_time = auto.settling_time.get()
    yield from bps.sleep(settling_time)

    previous_range = None
    converged = False
    for _iteration in range(max_iterations):
        # The sequence program only re-ranges after a completed read, so each
        # trigger buys exactly one opportunity to move.
        yield from bps.trigger(det, wait=True)
        yield from bps.sleep(settling_time)

        current_range = auto.lurange.get()
        stable = current_range == previous_range
        previous_range = current_range

        # Stability alone is not enough.  The range we seeded is forced, and
        # the program cannot react until a read completes, so the first two
        # reads look identical whether or not the range is right -- which is
        # how a stale seed gets locked in.  Require that the reading is also
        # not railed before believing it.
        if stable and not _reading_above_window(control):
            converged = True
            break

    if converged:
        _last_range_[key] = previous_range
    yield from bps.mv(auto.mode, FX4AutorangeSettings.manual)
    yield from bps.mv(det.averaging_time, original_count_time)

    if not converged:
        railed = _reading_above_window(control)
        msg = (
            f"{control.nickname}: "
            + ("still railed" if railed else "range still changing")
            + f" after {max_iterations} reads (last range {previous_range})"
        )
        if _in_user_operations() and RE is not None and RE.state != "idle":
            raise FX4AutoscaleError(msg)
        logger.warning(msg)
        return

    _report_signal_level(control, previous_range)


def _in_user_operations():
    """Return True when the APS is running for users.

    A failure to converge only aborts a scan during user operations; at other
    times it is a warning.  Missing or unreadable APS status is treated as "not
    user operations", so a registry without the ``aps`` device (a simulation, a
    test) degrades to warnings rather than raising something unrelated.

    Returns
    -------
    bool
    """
    try:
        return bool(oregistry["aps"].inUserOperations)
    except Exception as exc:  # noqa: BLE001 - absence is a valid answer here
        logger.debug("APS operating mode unavailable (%s); assuming not user ops", exc)
        return False


def _report_signal_level(control, range_index):
    """Log where the converged reading sits within the range.

    Not a pass/fail test.  A reading below the window at the most sensitive
    range simply means there is little signal, which no amount of ranging
    fixes; one above the window at the least sensitive range means the diode is
    genuinely saturated and the data will be wrong.  Both are worth seeing in
    the log, neither is worth aborting a scan over.

    Parameters
    ----------
    control : FX4DetectorControls
        The detector just autoscaled.
    range_index : int
        The converged range index, for the log message.
    """
    try:
        value = control.signal.get()
        label = control.quadem.em_range.get(as_string=True)
    except Exception as exc:  # noqa: BLE001 - diagnostics must not break a scan
        logger.debug(
            "%s: could not read back the signal level: %s", control.nickname, exc
        )
        return

    full_scale = full_scale_pA(label)
    low, high = control.auto.current_window(full_scale)
    where = "ok"
    if value > high:
        where = "ABOVE the useful window - may be saturated"
    elif value < low:
        where = "below the useful window - little signal"
    logger.info(
        "%s: range %s (%s), %.4g pA - %s",
        control.nickname,
        range_index,
        label,
        value,
        where,
    )


DARK_SETTLE_S = 1.0
"""Pause after the range is confirmed and before the first dark reading, s.

The range switch itself, and the diode and cable relaxing after the shutter
closed on a beam that a moment ago put orders of magnitude more current
through them, both need time to die away.  The old 0.08 s did not cover even
the switch.  Dark currents are measured once per command file, so a second
here costs nothing.
"""

DARK_DISCARD_READINGS = 2
"""Readings taken and thrown away before the ones that count."""

DARK_NUM_READINGS = 10
"""Readings per attempt that enter the statistics."""

DARK_MAX_ATTEMPTS = 3
"""Attempts per range before giving up and keeping the stored dark."""

DARK_RANGE_TIMEOUT_S = 5.0
"""How long to wait for the FX4's ``Range_RBV`` to show a requested range, s."""

DARK_RANGE_POLL_S = 0.05
"""Polling interval while waiting for the range, s."""


@plan
def measure_background(
    controls,
    shutter=None,
    count_time: Optional[float] = None,
    num_readings: int = DARK_NUM_READINGS,
    sweep_all_ranges: bool = False,
    note: str = "",
):
    """Plan: measure detector dark currents and store them in the IOC.

    Writes the mean and standard deviation of the dark reading into the
    sequence program's ``bkg<n>`` / ``bkgErr<n>`` records, the same place the
    Femto-era plan wrote them.  Both the fly scan (``saveFlyData.xml``) and the
    step scan (the ``fx4_autorange`` baseline stream) record that table, and
    the data reduction subtracts it -- at high q from a signal *smaller* than
    the dark itself.  So a bad measurement is never stored: see
    :func:`_measure_background_one_` for how readings are taken, cleaned and
    accepted.

    Two differences from the Femto-era plan, both from the shared range:

    * Detectors without a sequence program have nowhere to store a dark
      reading and are skipped.  Today that is I00.
    * There is one ``bkg`` table per sequence program, and on ``usxFX4`` that
      program serves both UPD and TRD, so they cannot both be recorded.
      ``group_controls_by_box`` enforces one per electrometer; pass UPD.

    By default only the **most sensitive** range is measured (index
    :data:`~usaxs.devices.fx4_quadem.MOST_SENSITIVE_RANGE`, i.e. 100 nA --
    *not* index 0, which is 1 mA), because that is where dark current actually
    matters relative to signal.  ``sweep_all_ranges`` restores the full
    five-range sweep.

    Parameters
    ----------
    controls : list or tuple of FX4DetectorControls
        Detectors whose dark current to measure.
    shutter : optional
        Closed before measuring if given.
    count_time : float, optional
        Integration time per reading, seconds, for every detector.  By default
        each box uses its own ``auto.dark_count_time`` (set in
        ``devices.yml``): I0 needs a far longer count than UPD to average out
        its slow pickup.
    num_readings : int
        Readings per attempt that enter the statistics, after
        ``DARK_DISCARD_READINGS`` have been thrown away.
    sweep_all_ranges : bool
        Measure every range instead of only the most sensitive one.
    note : str
        Measurement conditions (e.g. AR position), recorded with every attempt
        in the log and in ``DARK_RECORD_FILE``.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    if not isinstance(controls, (tuple, list)):
        raise ValueError("controls must be a list or tuple")

    by_box = group_controls_by_box(controls)
    if not by_box:
        logger.info("measure_background: no autoranged detectors, nothing to do")
        return

    logger.info("Measuring dark currents")
    if shutter is not None:
        yield from bps.mv(shutter, "close")

    for control in by_box.values():
        yield from _measure_background_one_(
            control,
            count_time=count_time,
            num_readings=num_readings,
            sweep_all_ranges=sweep_all_ranges,
            note=note,
        )


DARK_RETRY_BACKOFF_S = 30 * 60
"""After a dark measurement that kept no result, wait this long before retrying.

A rejected measurement leaves ``bkg`` -- and so its timestamp -- untouched,
which is right (a failed dark must not look fresh) but means every following
scan would see it as stale and spend up to ~50 s retrying.
"""

_last_dark_attempt_ = {}
"""``{electrometer name: time.time()}`` of the last dark measurement started.

Only consulted while the stored dark is stale, i.e. after a failure.
"""


def dark_age_s(control, range_index=MOST_SENSITIVE_RANGE, now=None):
    """Return the age of a detector's stored dark current, seconds.

    The age is taken from the Channel Access timestamp of ``bkg<range_index>``
    -- the IOC stamps every write -- so a dark measured by any path counts, the
    age survives a Bluesky or queueserver restart, and a rejected measurement
    (which writes nothing) does not make a stale dark look fresh.  One known
    flaw: an IOC reboot restores ``bkg`` from autosave with a new timestamp,
    so the restored (last measured) value looks fresh for one interval.

    Parameters
    ----------
    control : FX4DetectorControls
        A detector with an autorange sequence program.
    range_index : int
        The range whose dark to check.
    now : float, optional
        Current time, for tests.  Defaults to ``time.time()``.

    Returns
    -------
    float
        Age in seconds; ``inf`` when the timestamp cannot be read.
    """
    now = time.time() if now is None else now
    record = getattr(control.auto.ranges, f"range{range_index}")
    try:
        stamp = float(record.background.timestamp)
    except Exception as exc:  # noqa: BLE001 - unreadable means "measure it"
        logger.debug("%s: no dark timestamp (%s)", control.nickname, exc)
        return float("inf")
    if not stamp > 0:
        return float("inf")
    return now - stamp


@plan
def measure_background_if_stale(
    controls, max_age_s, shutter=None, now=None, force=False, note=""
):
    """Plan: re-measure dark currents that are older than *max_age_s*.

    The command file used to measure darks once, at its start; a scan queued
    by hand or from Igor never did, so an overnight queue ran on one dark for
    13 h.  This is called at the end of each USAXS scan (``Flyscan``,
    ``USAXSscanStep``) to keep it fresh.  Only the stale boxes are measured,
    each with its own settings (see :func:`measure_background`).  If nothing is
    stale it yields no messages at all.

    After a failed measurement a box is not retried for
    ``DARK_RETRY_BACKOFF_S``.

    Parameters
    ----------
    controls : list or tuple of FX4DetectorControls
        Detectors to check.
    max_age_s : float
        Darks older than this are re-measured.  ``<= 0`` disables the check.
    shutter : optional
        Closed before measuring, if anything is measured.
    now : float, optional
        Current time, for tests.  Defaults to ``time.time()``.
    force : bool
        Measure every box whatever its age (still subject to the back-off).
        Used when the caller wants a dark now regardless of age.
    note : str
        Measurement conditions, recorded with every attempt.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    if max_age_s <= 0 and not force:
        return
    now = time.time() if now is None else now
    stale = []
    for control in group_controls_by_box(controls).values():
        age = dark_age_s(control, now=now)
        if not force and age <= max_age_s:
            continue
        box = control.quadem.name
        since_attempt = now - _last_dark_attempt_.get(box, float("-inf"))
        if since_attempt < DARK_RETRY_BACKOFF_S:
            logger.debug(
                "%s dark is %.1f h old, but the last attempt failed %.0f min ago",
                control.nickname,
                age / 3600,
                since_attempt / 60,
            )
            continue
        logger.info(
            "%s dark current is %.1f h old (limit %.1f h%s): re-measuring",
            control.nickname,
            age / 3600,
            max_age_s / 3600,
            ", requested" if force else "",
        )
        _last_dark_attempt_[box] = now
        stale.append(control)

    if not stale:
        return
    yield from measure_background(stale, shutter=shutter, note=note)
    # Rewind boundary: a suspension later in the scan must not replay the
    # dark measurement (CLAUDE.md, "Every plan must bound its rewind cache").
    yield from bps.checkpoint()


def seq_range_full_scale_pA(range_index):
    """Return the full scale of a sequence-program range index, in pA.

    The program's enum runs ``[0] 1 mA .. [4] 100 nA``, a decade apart.

    Parameters
    ----------
    range_index : int
        Sequence-program range index, 0 to ``NUM_AUTORANGE_RANGES - 1``.

    Returns
    -------
    float
        Full-scale current, pA.
    """
    return 1.0e9 / 10 ** int(range_index)


@plan
def _wait_for_range(control, target):
    """Plan (internal): wait until the electrometer itself is on *target*.

    Checks the FX4's ``Range_RBV`` (``quadem.em_range``), **not** the sequence
    program's ``lurange``.  In ``manual`` mode the program writes ``Range`` in
    ``changeRange`` and then clears the ``Range`` monitor event, so ``update``
    -- the only state that sets ``lurange`` -- never runs.  Tested on
    2026-10-31: ``Range_RBV`` followed a ``reqrange`` write within 0.2 s while
    ``lurange`` stayed on the old range indefinitely.  Waiting on ``lurange``
    therefore timed out after every tune.

    Parameters
    ----------
    control : FX4DetectorControls
        The detector whose electrometer to watch.
    target : int
        Sequence-program range index requested.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.

    Returns
    -------
    bool
        True once the range is confirmed, False on timeout.
    """
    wanted = seq_range_full_scale_pA(target)
    polls = int(np.ceil(DARK_RANGE_TIMEOUT_S / DARK_RANGE_POLL_S))
    for _ in range(polls):
        try:
            label = control.quadem.em_range.get(as_string=True)
            if full_scale_pA(label) == wanted:
                return True
        except Exception as exc:  # noqa: BLE001 - keep polling until timeout
            logger.debug("Range_RBV unreadable while waiting: %s", exc)
        yield from bps.sleep(DARK_RANGE_POLL_S)
    return False


@plan
def _measure_background_one_(
    control,
    count_time: Optional[float] = None,
    num_readings: int = DARK_NUM_READINGS,
    sweep_all_ranges: bool = False,
    note: str = "",
):
    """Plan (internal): measure and store dark current for one detector.

    Hardened after a measurement at 12-ID-E stored -1.6 +/- 6 pA for UPD,
    against a normal 2 pA +/- 0.05.  In order:

    1. **Configure the box with** ``fx4_scaler_mode``.  The resting state that
       follows a fly scan leaves the stats plugins at ``CallbacksBlock = No``,
       and then a trigger can return before the mean is recomputed -- the
       reading is the *previous* one.
    2. **Wait for the range** to be confirmed by the FX4's ``Range_RBV``
       (:func:`_wait_for_range`), then settle ``DARK_SETTLE_S``.  If it never
       arrives nothing is measured and the stored dark is kept.
    3. **Discard** ``DARK_DISCARD_READINGS`` readings, then take
       ``num_readings`` of ``auto.dark_count_time`` each.  The spread check
       below cannot see pickup slower than one attempt -- the readings agree
       with each other while all sitting on the same part of the wave -- so
       the count time has to span it.  That is why I0 counts 1 s, not 0.2.
    4. **Reject outliers** against the median and MAD
       (:func:`~usaxs.utils.dark_current.robust_dark_statistics`).
    5. **Accept** only if the spread is within ``auto.max_dark_error`` and most
       readings survived; otherwise settle and try again, up to
       ``DARK_MAX_ATTEMPTS``.
    6. **Never overwrite a stored dark with a bad one.**  If no attempt is
       accepted, the previous ``bkg``/``bkgErr`` are left alone and a warning
       goes to the log and to the Obsidian notebook.  The command file is not
       aborted.

    Afterwards the sequence program's mode and the count time are restored
    and the box is left free-running, as every plan leaves it.

    Parameters
    ----------
    control : FX4DetectorControls
        A detector with an autorange sequence program.
    count_time : float, optional
        Integration time per reading, seconds.  Defaults to the box's
        ``auto.dark_count_time``.
    num_readings : int
        Readings per attempt that enter the statistics.
    sweep_all_ranges : bool
        Measure every range instead of only the most sensitive one.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    det = control.quadem
    auto = control.auto

    original_count_time = det.averaging_time.get()
    original_mode = auto.mode.get()
    if count_time is None:
        count_time = auto.dark_count_time.get()

    yield from select_fx4_channel(control)
    # Also sets CallbacksBlock = Yes, Single acquire and the count time.
    yield from fx4_scaler_mode(det, count_time)
    # Manual, so the sequence program does not re-range mid-sweep.
    yield from bps.mv(auto.mode, FX4AutorangeSettings.manual)

    # The most sensitive range is where dark current matters most relative to
    # signal, so that is the one worth measuring when only one is measured.
    # It is index NUM_AUTORANGE_RANGES-1, *not* 0 -- the sequence program's
    # enum runs least-to-most sensitive ([0] 1 mA .. [4] 100 nA).
    ranges = (
        range(NUM_AUTORANGE_RANGES) if sweep_all_ranges else (MOST_SENSITIVE_RANGE,)
    )

    for range_index in ranges:
        yield from _measure_one_range_(control, range_index, num_readings, note)

    yield from bps.mv(auto.mode, original_mode)
    yield from bps.mv(det.averaging_time, original_count_time)
    yield from fx4_monitor_mode(det)


@plan
def _measure_one_range_(control, range_index, num_readings, note=""):
    """Plan (internal): measure, check and store the dark for one range.

    See :func:`_measure_background_one_` for the procedure.  Every attempt,
    accepted or not, is appended to ``DARK_RECORD_FILE``.

    Parameters
    ----------
    control : FX4DetectorControls
        A detector with an autorange sequence program, already configured.
    range_index : int
        Range index to measure.
    num_readings : int
        Readings per attempt that enter the statistics.
    note : str
        Measurement conditions, recorded with every attempt.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    det = control.quadem
    auto = control.auto
    max_error = auto.max_dark_error.get()

    yield from auto.setRange(range_index)
    confirmed = yield from _wait_for_range(control, range_index)
    if not confirmed:
        # A dark taken on the wrong range is a plausible-looking wrong number.
        record = getattr(auto.ranges, f"range{range_index}")
        logger.warning(
            "%s dark: FX4 never reached range %d (Range_RBV %r after %.1f s)."
            "  Nothing measured; KEEPING the previous value %.4g +/- %.2g pA.",
            control.nickname,
            range_index,
            control.quadem.em_range.get(as_string=True),
            DARK_RANGE_TIMEOUT_S,
            record.background.get(),
            record.background_error.get(),
        )
        return

    attempts = []
    for attempt in range(1, DARK_MAX_ATTEMPTS + 1):
        yield from bps.sleep(DARK_SETTLE_S)

        readings = []
        for i in range(DARK_DISCARD_READINGS + num_readings):
            yield from bps.trigger(det, wait=True)
            if i >= DARK_DISCARD_READINGS:
                readings.append(control.signal.get())

        mean, std, n_kept = robust_dark_statistics(readings)
        attempts.append((mean, std, n_kept))
        accepted = dark_is_acceptable(std, n_kept, len(readings), max_error)
        _record_dark(
            control.nickname,
            range_index,
            attempt,
            mean,
            std,
            n_kept,
            readings,
            accepted,
            note,
        )
        if accepted:
            record = getattr(auto.ranges, f"range{range_index}")
            yield from bps.mv(
                record.background,
                mean,
                record.background_error,
                std,
            )
            logger.info(
                "%s dark: range %d, %.4g +/- %.2g pA (%d of %d readings kept,"
                " attempt %d)%s",
                control.nickname,
                range_index,
                mean,
                std,
                n_kept,
                len(readings),
                attempt,
                f" [{note}]" if note else "",
            )
            return

        logger.warning(
            "%s dark: range %d attempt %d rejected: %.4g +/- %.2g pA"
            " (%d of %d readings kept, limit %.2g pA); raw readings %s",
            control.nickname,
            range_index,
            attempt,
            mean,
            std,
            n_kept,
            len(readings),
            max_error,
            np.array2string(np.asarray(readings), precision=3),
        )

    record = getattr(auto.ranges, f"range{range_index}")
    previous = (record.background.get(), record.background_error.get())
    tried = ", ".join(f"{m:.4g} +/- {s:.2g}" for m, s, _n in attempts)
    logger.warning(
        "%s dark current, range %d: no good measurement in %d attempts"
        " (%s pA; limit %.2g pA).  KEEPING the previous value %.4g +/- %.2g pA.",
        control.nickname,
        range_index,
        DARK_MAX_ATTEMPTS,
        tried,
        max_error,
        *previous,
    )
    _safe_append(
        f"## Dark Current Rejected — {control.nickname}, range {range_index}\n"
        f"- **Attempts (pA):** {tried}\n"
        f"- **Limit (pA):** {max_error:.2g}\n"
        f"- **Kept previous value (pA):** {previous[0]:.4g} +/- {previous[1]:.2g}\n"
    )


DARK_RECORD_FILE = "/share1/log/usaxs_dark_currents.csv"
"""Every dark-current attempt is appended here, for trending and diagnosis."""

_DARK_RECORD_FIELDS = (
    "time",
    "detector",
    "range",
    "attempt",
    "mean_pA",
    "std_pA",
    "n_kept",
    "n_readings",
    "accepted",
    "note",
    "readings_pA",
)


def _record_dark(
    nickname, range_index, attempt, mean, std, n_kept, readings, accepted, note
):
    """Append one dark-current attempt to ``DARK_RECORD_FILE``, never raising.

    A ``/share1`` problem must not stop a measurement, so failures are logged
    and swallowed.
    """
    import csv
    import datetime
    import os

    row = {
        "time": datetime.datetime.now().isoformat(timespec="seconds"),
        "detector": nickname,
        "range": range_index,
        "attempt": attempt,
        "mean_pA": f"{mean:.4f}",
        "std_pA": f"{std:.4f}",
        "n_kept": n_kept,
        "n_readings": len(readings),
        "accepted": int(bool(accepted)),
        "note": note,
        "readings_pA": " ".join(f"{r:.3f}" for r in readings),
    }
    try:
        new_file = not os.path.exists(DARK_RECORD_FILE)
        with open(DARK_RECORD_FILE, "a", newline="") as fp:
            writer = csv.DictWriter(fp, fieldnames=_DARK_RECORD_FIELDS)
            if new_file:
                writer.writeheader()
            writer.writerow(row)
    except Exception as exc:  # noqa: BLE001 - recording must never break a scan
        logger.warning("Could not record dark current to %s: %s", DARK_RECORD_FILE, exc)


def UPDRange() -> int:
    """Return the UPD channel's last used range index.

    Returns
    -------
    int
        The ``lurange`` readback of the UPD sequence program.
    """
    return oregistry["upd_controls"].auto.lurange.get()
