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
from ..utils.fx4_ranges import full_scale_pA

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


def fraction_of_full_scale(controls):
    """Return the reading as a fraction of the active range's full scale.

    Replaces the old ``counts > TR_MAX_ALLOWED_COUNTS`` saturation test.  That
    threshold worked because a scaler channel had a fixed maximum count rate;
    the FX4's useful maximum moves with the range, so the test has to move with
    it too.

    Works for fixed-range detectors as well -- it reads the electrometer's
    ``Range``, not the sequence program.

    Parameters
    ----------
    controls : FX4DetectorControls
        The detector to check.

    Returns
    -------
    float or None
        ``reading / full scale``, or ``None`` when the range label could not be
        parsed, in which case the caller has no basis to judge and should not
        guess.
    """
    try:
        label = controls.quadem.em_range.get(as_string=True)
        full_scale = full_scale_pA(label)
        if not full_scale:
            return None
        return controls.signal.get() / full_scale
    except Exception as exc:  # noqa: BLE001 - a missing readback is "unknown"
        logger.debug("%s: cannot judge saturation: %s", controls.nickname, exc)
        return None


def any_near_full_scale(controls_list, limit):
    """Return True if any detector is reading above *limit* of full scale.

    Parameters
    ----------
    controls_list : iterable of FX4DetectorControls
        Detectors to check.
    limit : float
        Fraction of full scale, e.g. ``0.90``.

    Returns
    -------
    bool
        False when no detector can be judged -- an unparseable range is not
        evidence of saturation.
    """
    for controls in controls_list:
        fraction = fraction_of_full_scale(controls)
        if fraction is not None and fraction > limit:
            logger.info(
                "%s at %.0f %% of full scale, above the %.0f %% limit",
                controls.nickname,
                100 * fraction,
                100 * limit,
            )
            return True
    return False


@plan
def enable_fx4_autorange(controls, mode="automatic"):
    """Plan: let the sequence program range *this* detector, live.

    Always prefer this over writing ``controls.auto.mode`` directly.  One
    ``Range`` serves all four channels of an electrometer, so enabling
    automatic ranging without first pointing ``seq01:channel`` at the detector
    in use silently optimises for whichever channel was selected last.  After a
    transmission measurement that is TRD, and a UPD scan would then run on a
    range chosen for the transmitted beam -- orders of magnitude out, and with
    a gain-independent readout the numbers still look like plausible currents.

    A no-op for detectors on a fixed range.

    Parameters
    ----------
    controls : FX4DetectorControls
        The detector to range on.
    mode : str
        ``"automatic"`` or ``"auto+background"``; see
        :class:`~usaxs.devices.fx4_quadem.FX4AutorangeSettings`.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    if not controls.autoranged:
        logger.debug("%s: fixed range, autoranging not enabled", controls.nickname)
        return
    yield from select_fx4_channel(controls)
    yield from bps.mv(controls.auto.mode, mode)


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


def usaxs_electrometers():
    """Return the electrometers a USAXS measurement reads, in a stable order.

    ``fx4`` carries UPD and TRD, ``fx42`` carries I0 and I00.  Both are read at
    every point: the scaler this replaces gated all channels from one clock, so
    a plan that read UPD got I0 in the same document, and keeping that means
    normalisation data is present without every plan having to ask for it.

    Returns
    -------
    list
        ``[fx4, fx42]``.
    """
    from apsbits.core.instrument_init import oregistry

    return [oregistry["fx4"], oregistry["fx42"]]


@plan
def prepare_fx4_counting(count_time, dets=None):
    """Plan: put every USAXS electrometer into fixed-time counting mode.

    The replacement for ``bps.mv(scaler0.preset_time, count_time)`` plus the
    scaler's ``OneShot`` count mode.  Configures the full mode each time rather
    than only the count time: it is a handful of channel-access writes against
    a scan that takes seconds, and it means a plan cannot inherit a fly scan's
    bulb-mode settings and silently take one average per PSO strobe.

    Parameters
    ----------
    count_time : float
        Integration time per point, seconds.  Quantised to whole mains cycles.
    dets : iterable of QuadFX4, optional
        Electrometers to configure.  Defaults to :func:`usaxs_electrometers`.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    for det in dets if dets is not None else usaxs_electrometers():
        yield from fx4_scaler_mode(det, count_time)


@plan
def set_usaxs_count_time(count_time, dets=None):
    """Plan: change the integration time on every USAXS electrometer.

    For the inner loop of a scan, where the mode is already set and only the
    dwell changes -- ``uascan``'s dynamic timing, for instance.

    Parameters
    ----------
    count_time : float
        Integration time, seconds.  Quantised to whole mains cycles.
    dets : iterable of QuadFX4, optional
        Electrometers to set.  Defaults to :func:`usaxs_electrometers`.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    for det in dets if dets is not None else usaxs_electrometers():
        yield from set_fx4_count_time(det, count_time)


@plan
def restore_upd_channel():
    """Plan: hand usxFX4's shared Range back to UPD.

    Anything that autoranges TRD points ``seq01:channel`` at it, and one Range
    serves all four channels.  Consumers are defended -- both
    :func:`enable_fx4_autorange` and the autoscale plan select the channel
    before using it -- but leaving the instrument pointed at the transmitted
    beam invites a hand-run scan to pick up the wrong range, and with a
    gain-independent readout that produces plausible numbers rather than an
    error.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    from apsbits.core.instrument_init import oregistry

    yield from select_fx4_channel(oregistry["upd_controls"])


I0_GATED_GROUP = "fx4_gated_I0"
"""Bluesky group for the I0 integration that runs under an image exposure."""


@plan
def start_gated_I0(exposure_time):
    """Plan: begin the I0 integration that normalises an area-detector frame.

    The stopgap for the one thing the FX4 cannot do (PLAN.md section 5.0).
    ``scaler1`` was **hardware**-gated by the detector exposure: the I0 V-F
    frequency was split, one copy free-running and one gated, and the gated
    count normalised the frame.  There is no frequency to split now and no gate
    wired to the detector, so the integration is started in software with
    ``AveragingTime`` set to the exposure time.

    Returns immediately, so the integration overlaps the exposure rather than
    adding to it.  Pair with :func:`finish_gated_I0` after the acquisition.

    The window therefore only *approximates* the exposure window: it drifts
    with detector dead time, with multi-image series, and with acquire-period
    overhead.  Good enough while exposures are uniform, and the reason the
    shutdown TODO in PLAN.md section 5.0 exists.

    Parameters
    ----------
    exposure_time : float
        Image exposure time, seconds.  Quantised to whole mains cycles.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    from apsbits.core.instrument_init import oregistry

    det = oregistry["fx42"]
    yield from fx4_scaler_mode(det, exposure_time, channels=(1, 2))
    yield from bps.trigger(det, group=I0_GATED_GROUP)


@plan
def finish_gated_I0():
    """Plan: wait for the gated I0 integration and return the charge.

    Returns ``Total`` rather than ``MeanValue``: it is the sum of the samples
    in the reading, which is the scaler-like integral and therefore the right
    quantity behind an NXmonitor ``integral``.  Unlike a mean it also stays
    correct when the exposure time varies, which the software-timed window
    makes likely.  ``ADconfigs`` records it under the unchanged attribute name
    ``I0_cts_gated``, so the NeXus hardlink and the reduction path are
    untouched; absolute charge is that value times ``FX4_SampleTime``.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.

    Returns
    -------
    float
        The I0 integral over the exposure.
    """
    from apsbits.core.instrument_init import oregistry

    det = oregistry["fx42"]
    yield from bps.wait(group=I0_GATED_GROUP)
    return det.channel_stats(1).total.get()


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
