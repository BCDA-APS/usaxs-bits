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
Simpler than the scaler version, because the FX4 has no counter to overflow:
every range returns one current, which may just be over or under the useful
window.  So the test is only *"has the range stopped changing?"*.  A stable
range across two consecutive reads means the sequence program is content.

``max_iterations`` is the backstop.  Five reads is enough to walk the whole
five-range table from any starting point, plus one more to confirm the last
move, so the default is seven.  With seeding it normally converges in two.
"""

import logging
from typing import Optional

import numpy as np
from apsbits.core.instrument_init import oregistry
from bluesky import RunEngine
from bluesky import plan_stubs as bps
from bluesky.utils import plan

from ..devices.fx4_quadem import NUM_AUTORANGE_RANGES
from ..devices.fx4_quadem import FX4AutorangeSettings
from ..devices.fx4_quadem import FX4AutoscaleError
from ..utils.count_time import quantize_count_time
from ..utils.fx4_ranges import full_scale_pA
from .fx4_setup import group_controls_by_box
from .fx4_setup import select_fx4_channel

logger = logging.getLogger(__name__)

DEFAULT_AUTOSCALE_COUNT_TIME = 0.05
"""Integration time per trial read, seconds.  Three mains cycles."""

DEFAULT_MAX_ITERATIONS = NUM_AUTORANGE_RANGES + 2
"""Enough reads to cross the whole range table, plus one to confirm."""

_last_range_ = {}
"""``{(electrometer, channel): range index}`` -- the last converged range.

Module-level so it survives between plan calls.  Keyed per *channel* because
one sequence program serves several, and their correct ranges differ by orders
of magnitude.
"""


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
    2. put it in ``automatic`` and seed the range from this channel's last
       converged value, so the usual case needs one or two reads rather than a
       walk across the table;
    3. read repeatedly -- the sequence program can only act on a *completed*
       read -- until the range repeats;
    4. return it to ``manual`` and restore the count time.

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
        if current_range == previous_range:
            converged = True
            break
        previous_range = current_range

    if converged:
        _last_range_[key] = previous_range
    yield from bps.mv(auto.mode, FX4AutorangeSettings.manual)
    yield from bps.mv(det.averaging_time, original_count_time)

    if not converged:
        msg = (
            f"{control.nickname}: range still changing after {max_iterations}"
            f" reads (last range {previous_range})"
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


@plan
def measure_background(
    controls,
    shutter=None,
    count_time: float = 0.2,
    num_readings: int = 5,
    sweep_all_ranges: bool = False,
):
    """Plan: measure detector dark currents and store them in the IOC.

    Writes the mean and standard deviation of the dark reading into the
    sequence program's ``bkg<n>`` / ``bkgErr<n>`` records, the same place the
    Femto-era plan wrote them.

    Two differences from that plan, both from the shared range:

    * Detectors without a sequence program have nowhere to store a dark
      reading and are skipped.  Today that is I0 and I00.
    * There is one ``bkg`` table per sequence program, and on ``usxFX4`` that
      program serves both UPD and TRD, so they cannot both be recorded.
      ``group_controls_by_box`` enforces one per electrometer; pass UPD.

    By default only the **most sensitive** range is measured, which is where
    dark current actually matters relative to signal.  ``sweep_all_ranges``
    restores the full five-range sweep.

    Parameters
    ----------
    controls : list or tuple of FX4DetectorControls
        Detectors whose dark current to measure.
    shutter : optional
        Closed before measuring if given.
    count_time : float
        Integration time per reading, seconds.
    num_readings : int
        Readings per range, for the mean and its spread.
    sweep_all_ranges : bool
        Measure every range instead of only the most sensitive one.

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
        )


@plan
def _measure_background_one_(
    control,
    count_time: float = 0.2,
    num_readings: int = 5,
    sweep_all_ranges: bool = False,
):
    """Plan (internal): measure and store dark current for one detector.

    Parameters
    ----------
    control : FX4DetectorControls
        A detector with an autorange sequence program.
    count_time : float
        Integration time per reading, seconds.
    num_readings : int
        Readings per range.
    sweep_all_ranges : bool
        Measure every range instead of only the most sensitive one.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    det = control.quadem
    auto = control.auto

    original_count_time = det.averaging_time.get()
    trial_count_time = quantize_count_time(count_time)

    yield from select_fx4_channel(control)
    yield from bps.mv(det.averaging_time, trial_count_time)
    # Manual, so the sequence program does not re-range mid-sweep.
    yield from bps.mv(auto.mode, FX4AutorangeSettings.manual)

    # Range 0 is the most sensitive, so it is where dark current matters most
    # relative to signal and where one measurement buys the most.
    ranges = range(NUM_AUTORANGE_RANGES) if sweep_all_ranges else (0,)

    for range_index in ranges:
        yield from auto.setRange(range_index)
        yield from bps.sleep(auto.settling_time.get())

        readings = []
        for _ in range(num_readings):
            yield from bps.trigger(det, wait=True)
            readings.append(control.signal.get())

        record = getattr(auto.ranges, f"range{range_index}")
        yield from bps.mv(
            record.background,
            float(np.mean(readings)),
            record.background_error,
            float(np.std(readings)),
        )
        logger.info(
            "%s dark: range %d, %.4g +/- %.2g pA (%d readings)",
            control.nickname,
            range_index,
            np.mean(readings),
            np.std(readings),
            num_readings,
        )

    yield from bps.mv(det.averaging_time, original_count_time)


def UPDRange() -> int:
    """Return the UPD channel's last used range index.

    Returns
    -------
    int
        The ``lurange`` readback of the UPD sequence program.
    """
    return oregistry["upd_controls"].auto.lurange.get()
