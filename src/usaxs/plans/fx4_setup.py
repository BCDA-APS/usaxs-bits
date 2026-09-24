"""
Configuration plans for the FX4 electrometers.

The FX4 runs in one of two configurations, and every plan that uses it must put
it in the right one first.  See ``docs/FX4_config_cheatsheet.md``.

``fx4_scaler_mode``
    Fixed-time counting: one integration per trigger, ``MeanValue_RBV`` holds
    the average current.  Used by tuning, step USAXS and transmission.
``fx4_flyscan_mode``
    PSO-gated: one average per strobe interval, appended to a per-channel time
    series.  Used by the USAXS fly scan.

Also here: :func:`select_fx4_channel`, which points a sequence program at the
detector in use, and :func:`group_controls_by_box`, which enforces the rule
that makes that necessary -- one range per electrometer, shared by all four
channels.
"""

import logging

from bluesky import plan_stubs as bps
from bluesky.utils import plan

from ..devices.fx4_quadem import FX4RangeConflictError
from ..utils.count_time import max_count_time
from ..utils.count_time import quantize_count_time
from ..utils.count_time import samples_per_reading

logger = logging.getLogger(__name__)

DEFAULT_SCALER_VPR = 100
"""``ValuesPerRead`` for fixed-time counting.

Higher is better here.  The FX4 pre-averages on the device, so a larger value
does not discard signal -- it only coarsens time resolution *within* the
exposure, which fixed-time counting does not care about.  What it buys is a
10x lower streamed data rate (1 kHz per box instead of 10 kHz) and a longer
unbiased exposure (10 s instead of 1 s).  Both FX4s share one host, so the
link load is the real constraint.
"""

DEFAULT_FLYSCAN_VPR = 10
"""``ValuesPerRead`` for PSO-gated counting.

Cannot follow the same "higher is better" logic: in bulb mode the driver has to
*see* both edges of the HIGH strobe in the streamed samples, or two exposures
fuse into one.  The safe floor is 3-5 sample periods, so the PSO strobe width
sets the ceiling on this value.  10 is the value proven on a 2000-pulse train;
raising it needs the measured strobe width (PLAN.md section 5.2).
"""

VPR_LADDER = (10, 20, 50, 100, 200, 500)
"""Values of ``ValuesPerRead`` to choose from when one must be picked."""


def choose_values_per_read(count_time, minimum=DEFAULT_SCALER_VPR):
    """Return the smallest sensible ``ValuesPerRead`` for a count time.

    The driver's ring buffer holds ``RING_SIZE`` (10000) samples per reading;
    beyond that the oldest are discarded and the mean is biased toward the tail
    of the count.  Since ``samples = count_time x 100000 / VPR``, a long count
    needs a large VPR.

    Parameters
    ----------
    count_time : float
        Longest integration time the configuration must support, seconds.
    minimum : int
        Never return less than this.  Defaults to ``DEFAULT_SCALER_VPR``.

    Returns
    -------
    int
        A value from ``VPR_LADDER``.

    Raises
    ------
    ValueError
        If no laddered value can hold the requested count time.  The fix is to
        raise ``RING_SIZE`` in ``FX4.cmd`` (needs an IOC restart).
    """
    for vpr in VPR_LADDER:
        if vpr >= minimum and count_time <= max_count_time(vpr):
            return vpr
    raise ValueError(
        f"no ValuesPerRead in {VPR_LADDER} supports a {count_time} s count"
        f" within the default 10000-sample ring buffer"
        f" (longest is {max_count_time(VPR_LADDER[-1])} s at VPR={VPR_LADDER[-1]});"
        " raise RING_SIZE in FX4.cmd"
    )


@plan
def fx4_scaler_mode(det, count_time, channels=(1, 2, 3, 4), values_per_read=None):
    """Plan: put an FX4 into fixed-time counting mode.

    Each trigger integrates for ``count_time`` and updates
    ``Current<n>:MeanValue_RBV``.  This is the drop-in replacement for the
    scaler's ``OneShot`` count mode.

    ``CallbacksBlock = Yes`` is the part that is easy to miss: without it
    ``Acquire`` clears as soon as the driver finishes, which can be *before*
    the stats plugin has recomputed the mean -- so a plan that triggers and
    reads immediately gets the previous point's value.

    Parameters
    ----------
    det : QuadFX4
        The electrometer to configure.
    count_time : float
        Integration time, seconds.  Quantised to whole mains cycles.
    channels : iterable of int
        Channels whose stats plugins to enable.  Default all four.
    values_per_read : int, optional
        ``ValuesPerRead``.  Chosen automatically from ``count_time`` if omitted.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    count_time = quantize_count_time(count_time)
    if values_per_read is None:
        values_per_read = choose_values_per_read(count_time)

    yield from bps.mv(
        det.trigger_mode,
        "Free run",  # 0
        det.acquire_mode,
        "Single",  # 2
        det.values_per_read,
        values_per_read,
    )
    for ch in channels:
        stats = det.channel_stats(ch)
        yield from bps.mv(
            stats.enable,
            "Enable",
            stats.blocking_callbacks,
            "Yes",
        )
    yield from bps.mv(det.averaging_time, count_time)

    logger.debug(
        "%s: scaler mode, count_time=%.4f s, VPR=%d, %d samples/reading",
        det.name,
        count_time,
        values_per_read,
        samples_per_reading(count_time, values_per_read),
    )


@plan
def fx4_flyscan_mode(det, num_points, channels=(1, 2, 3, 4), values_per_read=None):
    """Plan: put an FX4 into PSO-gated (bulb) mode and arm its time series.

    Each PSO strobe closes one exposure and appends one average per channel to
    the time series.  ``AveragingTime`` is ignored in this mode -- the gate
    defines the window.

    ``TriggerPolarity = Negative`` because the PSO signal idles LOW and strobes
    HIGH, so the measurement windows are the LOW intervals *between* strobes.
    With Positive it would integrate only the few-microsecond strobe and
    capture essentially nothing.

    Does **not** start acquisition; the caller writes ``acquire = 1`` once
    everything else is armed, before the motion starts.

    Parameters
    ----------
    det : QuadFX4
        The electrometer to configure.
    num_points : int
        Time-series length.  Must be at least the number of PSO pulses; give
        it some margin.
    channels : iterable of int
        Channels to record.  Default all four.
    values_per_read : int, optional
        ``ValuesPerRead``.  Defaults to ``DEFAULT_FLYSCAN_VPR``; see that
        constant before changing it.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    if values_per_read is None:
        values_per_read = DEFAULT_FLYSCAN_VPR

    yield from bps.mv(
        det.trigger_mode,
        "Ext. bulb",  # 3
        det.trigger_polarity,
        "Negative",  # 1
        det.acquire_mode,
        "Continuous",  # 0
        det.values_per_read,
        values_per_read,
    )
    for ch in channels:
        stats = det.channel_stats(ch)
        yield from bps.mv(
            stats.enable,
            "Enable",
            stats.blocking_callbacks,
            "No",
            stats.ts_num_points,
            int(num_points),
            stats.ts_acquire_mode,
            "Fixed length",
        )
    # Arm last, so the series is empty when acquisition starts.
    for ch in channels:
        yield from bps.mv(det.channel_stats(ch).ts_control, "Erase/Start")

    logger.debug(
        "%s: flyscan mode, %d points, VPR=%d, SampleTime=%.1f us",
        det.name,
        num_points,
        values_per_read,
        values_per_read * 10,
    )


@plan
def set_fx4_count_time(det, count_time):
    """Plan: change the integration time of an FX4 already in scaler mode.

    Quantises to whole mains cycles and warns -- loudly -- if the result
    overflows the driver's ring buffer, because that failure is silent in the
    data: the mean is biased toward the tail of the count and nothing else
    looks wrong.

    Parameters
    ----------
    det : QuadFX4
        The electrometer.
    count_time : float
        Requested integration time, seconds.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    count_time = quantize_count_time(count_time)
    vpr = det.values_per_read.get()
    if vpr and count_time > max_count_time(vpr):
        logger.warning(
            "%s: count_time %.3f s exceeds the unbiased maximum %.3f s at"
            " ValuesPerRead=%d -- the ring buffer will overflow and the mean"
            " will be biased. Raise ValuesPerRead or RING_SIZE.",
            det.name,
            count_time,
            max_count_time(vpr),
            vpr,
        )
    yield from bps.mv(det.averaging_time, count_time)


@plan
def select_fx4_channel(controls):
    """Plan: point a detector's sequence program at its FX4 channel.

    An FX4 has one ``Range`` shared by all four channels, and the sequence
    program's ``channel`` record decides which one it optimises for.  UPD
    (ch 1) and TRD (ch 4) share ``fx4`` and are never in use at the same time,
    so this must be set before autoranging either of them.

    A no-op for detectors on a fixed range (``auto is None``).

    Parameters
    ----------
    controls : FX4DetectorControls
        The detector whose channel should be selected.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    if not controls.autoranged:
        return
    yield from controls.auto.setChannel(controls.channel_number)
    logger.debug(
        "%s: autoranging on %s channel %d",
        controls.nickname,
        controls.quadem.name,
        controls.channel_number,
    )


def group_controls_by_box(controls):
    """Return autoranged controls grouped by electrometer, one per box.

    The FX4-era replacement for ``amplifiers_plan.group_controls_by_scaler``.
    Two differences, both from the shared range:

    * detectors on a fixed range (``auto is None``) are dropped -- there is
      nothing to converge;
    * **two autoranged channels on one box is an error**, not a group.
      Converging one would de-converge the other, and because the reading is
      gain-independent the wrong answer still looks like a current.

    Parameters
    ----------
    controls : list or tuple of FX4DetectorControls
        Detectors to autoscale.

    Returns
    -------
    dict
        ``{quadem_name: control}`` -- at most one control per electrometer.

    Raises
    ------
    FX4RangeConflictError
        If two autoranged detectors share an electrometer.
    """
    if not isinstance(controls, (tuple, list)):
        raise ValueError("controls must be a list or tuple")

    by_box = {}
    for control in controls:
        if not control.autoranged:
            logger.debug("%s: fixed range, not autoscaled", control.nickname)
            continue
        box = control.quadem.name
        if box in by_box:
            raise FX4RangeConflictError(
                f"{box}: cannot autorange {by_box[box].nickname} and"
                f" {control.nickname} together -- one Range serves all four"
                " channels. Autoscale them in separate calls."
            )
        by_box[box] = control
    return by_box


@plan
def check_ring_overflows(dets, context=""):
    """Plan: warn if an FX4 dropped samples during the last acquisition.

    A non-zero ``RingOverflows`` means the driver's ring buffer filled and the
    oldest samples were discarded, so the reported means are biased toward the
    end of each count.  Nothing else in the data shows this, which is why it is
    worth an explicit check after every scan.

    Parameters
    ----------
    dets : iterable of QuadFX4
        Electrometers to check.
    context : str
        Text included in the warning, e.g. the plan name.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    yield from bps.null()
    for det in dets:
        overflows = det.ring_overflows.get()
        if overflows:
            logger.warning(
                "%s: RingOverflows=%s after %s -- samples were dropped and the"
                " means are biased. Raise ValuesPerRead or shorten the count.",
                det.name,
                overflows,
                context or "the last acquisition",
            )
