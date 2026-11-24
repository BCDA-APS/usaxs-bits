"""
How the FX4 electrometers are gated by the PSO train during a fly scan.

Two modes, chosen per scan by :func:`resolve_flyscan_trigger_mode`:

``Ext. trig.`` (the default since 2026-11-17)
    Each PSO rising edge closes the current point and opens the next, so point
    *i* is the interval from pulse *i* to pulse *i+1* and there is **no dead
    time**.  After the last pulse the final point runs until
    ``AveragingTime`` expires, so N pulses give **N points, of which the last
    is a timeout tail** (``channel_time[-1] == AveragingTime``), not a PSO
    interval.  Needs FX4 firmware >= :data:`FAST_GATE_FIRMWARE` on **every**
    box: the old firmware polled D1 at ~1 kHz and could not see a short edge.

``Ext. bulb`` (rollback)
    The LOW level *between* strobes is integrated (``TriggerPolarity =
    Negative``); each rising edge emits one point.  Point 0 is the wait from
    ``Acquire = 1`` to the first strobe (0.72 s in GC_SRM3600_0003.h5,
    2026-11-06), and point *i* runs from strobe *i-1* to strobe *i*.  The
    strobe width is dead time, and on old firmware it must be several sample
    periods wide (:func:`usaxs.utils.count_time.min_strobe_width_us`).

**The two modes index the same physics differently: trig point i is bulb point
i+1.**  Data reduction must branch on the trigger mode recorded in the fly-scan
HDF5 (``flyScan/fx4_trigger_mode``); a file without it is bulb.

Measured on 2026-11-17 with usxFX4 and usxFX42 both on firmware 26.10.151957,
``Ext. trig.``, Positive, ``AveragingTime`` 1.0 s, VPR 20, PSO strobes 20 us
wide: 4000 and 8000 pulses gave exactly 4000 and 8000 points on both boxes,
``channel_time[0]`` 31 ms (the first PSO interval), ``channel_time[-1]``
1.000 s.  Positive and Negative gave the same counts.

Kept free of ophyd and apsbits so it can be unit-tested without EPICS.
"""

import logging

logger = logging.getLogger(__name__)

TRIGGER_MODE_TRIG = "Ext. trig."
"""``TriggerMode`` enum string for edge-triggered points.  Note the lower-case
"t": the R9-8 driver's enum is ``Free run / Ext. trig. / Ext. bulb / Ext.
gate`` (indices 0-3), and EPICS matches the string exactly."""

TRIGGER_MODE_BULB = "Ext. bulb"
"""``TriggerMode`` enum string for level-gated points (rollback)."""

FLYSCAN_TRIGGER_MODES = (TRIGGER_MODE_TRIG, TRIGGER_MODE_BULB)

DEFAULT_FLYSCAN_TRIGGER_MODE = TRIGGER_MODE_TRIG

FLYSCAN_TRIGGER_POLARITY = {
    TRIGGER_MODE_TRIG: "Positive",
    TRIGGER_MODE_BULB: "Negative",
}
"""``TriggerPolarity`` per mode.

``Ext. trig.``: Positive, i.e. the rising edge.  The PSO line idles LOW and
the rising edge is the instant the Aerotech fires at the programmed position;
the falling edge comes ``PulseLength`` later.  At 20 us that is a fifth of a
sample period and the two give the same data (as tested), but at the 1200 us
rollback strobe Negative would shift every window by 1.2 ms.

``Ext. bulb``: Negative, so the LOW interval between strobes is integrated.
"""

FLYSCAN_AVERAGING_TIME = 1.0
"""``AveragingTime`` for ``Ext. trig.`` fly scans, seconds.

In this mode it is a **timeout**, not the dwell: a trigger arriving before it
expires closes the point early, which is what happens on every PSO interval.
It must therefore exceed the longest interval in any trajectory, or that point
is truncated and dead time creeps back in (see :func:`truncated_points`).  The
longest interval in a 90 s, 4000-point scan is ~0.17 s, so 1.0 s has a 6x
margin.  It also sets the length of the final point (the tail after the last
pulse), and so how long the plan waits for that point before stopping.
"""

TRUNCATION_FRACTION = 0.9
"""A point whose dwell reaches this fraction of ``AveragingTime`` was probably
closed by the timeout rather than by the next pulse."""

FAST_GATE_FIRMWARE = "26.10.151957"
"""First FX4 firmware whose D1 input is an edge counter streamed at the ADC
rate (quadEM R9-8).  Older firmware needs ``Ext. bulb`` and wide strobes."""


class FX4FirmwareError(RuntimeError):
    """The FX4 boxes cannot run the requested fly-scan trigger mode."""


def parse_firmware_version(text):
    """Return an FX4 firmware string as a comparable tuple of ints.

    Parameters
    ----------
    text : str or None
        As read from ``$(P)FX4:Firmware``, e.g. ``"26.10.151957"``.

    Returns
    -------
    tuple of int, or None
        ``None`` if the string is empty or does not parse.

    Examples
    --------
    >>> parse_firmware_version("26.10.151957")
    (26, 10, 151957)
    >>> parse_firmware_version("") is None
    True
    """
    if text is None:
        return None
    text = str(text).strip().strip("\x00")
    try:
        return tuple(int(part) for part in text.split("."))
    except ValueError:
        return None


def resolve_flyscan_trigger_mode(requested):
    """Return the trigger mode a fly scan should use.

    Parameters
    ----------
    requested : str or None
        ``usaxs_flyscan.trigger_mode``; empty or ``None`` means
        :data:`DEFAULT_FLYSCAN_TRIGGER_MODE`.

    Returns
    -------
    str
        One of :data:`FLYSCAN_TRIGGER_MODES`.

    Raises
    ------
    ValueError
        For any other string -- a typo must not silently pick a mode.
    """
    if not requested:
        return DEFAULT_FLYSCAN_TRIGGER_MODE
    if requested not in FLYSCAN_TRIGGER_MODES:
        raise ValueError(
            f"fly-scan trigger mode {requested!r} is not one of {FLYSCAN_TRIGGER_MODES}"
        )
    return requested


def check_fast_gate_firmware(firmware_by_box, minimum=FAST_GATE_FIRMWARE):
    """Raise unless every FX4 box runs fast-gate firmware, and the same one.

    Both boxes see the same PSO train and UPD/I0 is taken point by point, so
    they must define points identically.  A box on old firmware cannot run
    ``Ext. trig.`` reliably, and mixing modes offsets the two series by one
    point (see the module docstring).  An unreadable version is treated as
    old: *unknown* must not mean *ready*.

    Parameters
    ----------
    firmware_by_box : dict
        ``{box name: firmware string or None}``.
    minimum : str
        Oldest acceptable firmware.

    Raises
    ------
    FX4FirmwareError
        If any box is unreadable or older than *minimum*, or the boxes differ.
    """
    floor = parse_firmware_version(minimum)
    problems = []
    for name, text in firmware_by_box.items():
        version = parse_firmware_version(text)
        if version is None:
            problems.append(f"{name}: firmware unreadable ({text!r})")
        elif version < floor:
            problems.append(f"{name}: firmware {text} is older than {minimum}")
    if not problems:
        versions = {parse_firmware_version(t) for t in firmware_by_box.values()}
        if len(versions) > 1:
            problems.append(f"boxes run different firmware: {firmware_by_box}")
    if problems:
        raise FX4FirmwareError(
            f"Cannot fly in {TRIGGER_MODE_TRIG!r} mode: "
            + "; ".join(problems)
            + f".  Upgrade the box, or set usaxs_flyscan.trigger_mode to"
            f" {TRIGGER_MODE_BULB!r} for the old-firmware bulb mode."
        )


def expected_flyscan_points(num_pulses, trigger_mode):
    """Return how many time-series points *num_pulses* PSO pulses produce.

    N in both modes, but for different reasons: in ``Ext. trig.`` the last
    point is the ``AveragingTime`` tail after the final pulse; in ``Ext.
    bulb`` the first point is the wait before the first strobe and the LOW
    stretch after the last strobe never closes.

    Parameters
    ----------
    num_pulses : int
        ``usxAERO:pm1:NumPulses``.
    trigger_mode : str
        One of :data:`FLYSCAN_TRIGGER_MODES`.

    Returns
    -------
    int
    """
    resolve_flyscan_trigger_mode(trigger_mode)
    return int(num_pulses)


def point_count_problems(captured_by_box, expected):
    """Describe what is wrong with the per-box point counts, if anything.

    Parameters
    ----------
    captured_by_box : dict
        ``{box name: TSCurrentPoint or None}``.
    expected : int
        From :func:`expected_flyscan_points`; 0 means unknown.

    Returns
    -------
    list of str
        Empty when every box captured *expected* (or *expected* + 1, seen once
        in testing and harmless: it is a trailing point) and all agree.
    """
    problems = []
    counts = {k: v for k, v in captured_by_box.items() if v is not None}
    for name in captured_by_box:
        if captured_by_box[name] is None:
            problems.append(f"{name}: point count unreadable")
    if len(set(counts.values())) > 1:
        problems.append(
            f"boxes disagree on the point count {counts}: UPD/I0 is not"
            " point-by-point valid"
        )
    if expected:
        for name, n in counts.items():
            if n < expected:
                problems.append(
                    f"{name}: captured {n} of {expected} points"
                    f" ({expected - n} missing)"
                )
            elif n > expected + 1:
                problems.append(f"{name}: captured {n} points, expected {expected}")
    return problems


def truncated_points(channel_time, averaging_time, fraction=TRUNCATION_FRACTION):
    """Return indices of ``Ext. trig.`` points that the timeout closed.

    The last point is always the timeout tail, so it is not examined.  Any
    other point whose dwell reaches ``fraction x averaging_time`` was cut short
    by ``AveragingTime`` instead of by the next pulse: the gap until that pulse
    went unrecorded, and the point's AR span is shorter than its neighbours'.

    Parameters
    ----------
    channel_time : sequence of float
        Per-point dwell, seconds (``total / mean x SampleTime``).
    averaging_time : float
        ``AveragingTime`` in force during the scan.
    fraction : float
        Threshold, see :data:`TRUNCATION_FRACTION`.

    Returns
    -------
    list of int
    """
    limit = fraction * averaging_time
    return [i for i, dt in enumerate(list(channel_time)[:-1]) if dt >= limit]
