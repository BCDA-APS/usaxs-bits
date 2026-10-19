"""
Count-time helpers for the FX4 electrometers.

The FX4 integrates for ``AveragingTime`` seconds on each trigger.  Unlike the
scaler it replaced, the integration window is a free-running software window
rather than an integer number of clock ticks, so nothing stops it from landing
on a fraction of a mains cycle.  When that happens the 50/60 Hz pickup riding on
the photocurrent does not average out and repeatability suffers no matter how
long the count is -- see ``docs/FX4_PSO_flyscan_setup.md`` section 12.

Every plan that sets an FX4 count time should route the value through
:func:`quantize_count_time`.
"""

import logging

logger = logging.getLogger(__name__)

MAINS_FREQUENCY_HZ = 60.0
"""Mains frequency at APS.  One cycle is 16.667 ms."""

RING_SIZE_SAMPLES = 200_000
"""Driver ring-buffer size, samples per reading.

Set by ``epicsEnvSet("RING_SIZE", ...)`` in the FX4 IOC's ``iocsh/FX4.cmd``
and passed to ``drvFX4Configure``.  Raised from 100000 to 200000 in the IOC
and re-read from ``iocBoot/iocusxFX4{,2}/iocsh/FX4.cmd`` on 2026-10-13;
changing it there needs an IOC restart, and this constant must follow.

Past this cap the driver silently discards the oldest samples and the
reported mean is biased toward the tail of the count.
"""

MIN_STROBE_SAMPLE_PERIODS = 5
"""How many sample periods wide a PSO strobe must be to register reliably.

The FX4 reports the state of its D1 gate input once per output sample, at
``100 kHz / ValuesPerRead``.  A strobe narrower than one sample period falls
between two samples and is **never transmitted** -- the loss happens on the
device, so no ring-buffer size or IOC read rate can recover it, and the
captured fraction goes as ``width / SampleTime``.  See
``docs/FX4_PSO_trigger_issue.md`` section 0, which identified this after the
2026-09-27 width scan was found to have run at an effective ``ValuesPerRead``
of 100 (1 ms sample period) rather than the 10 recorded at the time.

The documented safe window is 3-5 sample periods; this is the conservative
end of it.
"""


def quantize_count_time(
    count_time: float,
    mains_hz: float = MAINS_FREQUENCY_HZ,
) -> float:
    """Round a count time to a whole number of mains cycles.

    Integrating over an integer number of mains cycles cancels the 50/60 Hz
    pickup in the photocurrent.  A window that ends part-way through a cycle
    leaves a residual that does not shrink with longer averaging, so this
    rounding is the difference between noise that averages away and noise that
    does not.

    The result is never zero: a request below half a cycle is raised to one
    full cycle (16.667 ms at 60 Hz).

    Parameters
    ----------
    count_time : float
        Requested integration time, seconds.
    mains_hz : float
        Mains frequency, Hz.  Default 60 (APS).

    Returns
    -------
    float
        The nearest integer number of mains cycles, in seconds.

    Examples
    --------
    >>> round(quantize_count_time(0.1), 6)        # 6 cycles
    0.1
    >>> round(quantize_count_time(0.1 / 3), 6)    # 2 cycles
    0.033333
    >>> round(quantize_count_time(0.001), 6)      # floor of 1 cycle
    0.016667
    """
    if count_time <= 0:
        raise ValueError(f"count_time must be > 0, given: {count_time}")

    cycles = max(1, round(count_time * mains_hz))
    quantized = cycles / mains_hz

    if abs(quantized - count_time) > 0.5 / mains_hz:
        # Only possible when the request was below half a cycle.
        logger.debug(
            "count time %.6f s raised to one mains cycle (%.6f s)",
            count_time,
            quantized,
        )
    return quantized


def sample_time(values_per_read: int) -> float:
    """Return the FX4's streamed sample period for a ``ValuesPerRead``.

    The FX4 digitises at a fixed 100 kHz and pre-averages ``values_per_read``
    conversions into each streamed sample, so the sample period is
    ``values_per_read x 10 us`` and the streamed rate is
    ``100 kHz / values_per_read``.  The IOC pushes the rate to the device
    itself (``SetValuesPerRead`` -> ``/fx4/adc/sample_frequency``), so this
    period governs gate detection as well as time resolution.

    Parameters
    ----------
    values_per_read : int
        The FX4 ``ValuesPerRead`` setting.

    Returns
    -------
    float
        Sample period, seconds.  Matches ``SampleTime_RBV``.
    """
    return values_per_read * 10e-6


def min_strobe_width_us(
    values_per_read: int,
    periods: int = MIN_STROBE_SAMPLE_PERIODS,
) -> float:
    """Return the narrowest PSO strobe that *values_per_read* can resolve.

    A fly scan in "Ext. bulb" mode delimits its exposures with the HIGH strobe
    of the Aerotech PSO output (``usxAERO:pm1:PulseLength``, microseconds).
    The FX4 only sees that strobe if it is still HIGH when the device takes a
    sample, so the strobe has to be several sample periods wide -- see
    :data:`MIN_STROBE_SAMPLE_PERIODS`.  Too narrow and neighbouring exposures
    merge, which looks exactly like missed PSO pulses in ``TSCurrentPoint``.

    Parameters
    ----------
    values_per_read : int
        The FX4 ``ValuesPerRead`` setting.
    periods : int
        Sample periods of margin required.  Defaults to
        :data:`MIN_STROBE_SAMPLE_PERIODS`.

    Returns
    -------
    float
        Minimum strobe width, microseconds, to compare directly against
        ``usxAERO:pm1:PulseLength``.

    Examples
    --------
    >>> min_strobe_width_us(100)   # 1 ms sample period
    5000.0
    >>> min_strobe_width_us(10)
    500.0
    >>> min_strobe_width_us(5)
    250.0
    """
    return sample_time(values_per_read) * periods * 1e6


def samples_per_reading(count_time: float, values_per_read: int) -> int:
    """Return how many streamed samples one reading of *count_time* contains.

    The FX4 digitises at 100 kHz and pre-averages ``values_per_read``
    conversions into each streamed sample, so ``SampleTime = values_per_read x
    10 us``.  The driver accumulates those samples in a ring buffer whose size
    (``RING_SIZE``, 200000 at 12-ID-E, set in ``FX4.cmd``) caps one reading.  Past
    that cap the oldest samples are silently discarded and the reported mean is
    biased toward the tail of the count.

    Parameters
    ----------
    count_time : float
        Integration time, seconds.
    values_per_read : int
        The FX4 ``ValuesPerRead`` setting.

    Returns
    -------
    int
        Number of streamed samples in one reading.
    """
    return round(count_time * 100_000 / values_per_read)


def max_count_time(values_per_read: int, ring_size: int = RING_SIZE_SAMPLES) -> float:
    """Return the longest unbiased integration time for a ``ValuesPerRead``.

    Above this the driver's ring buffer overflows and the mean is biased.  At
    the 12-ID-E ``RING_SIZE`` of 200000 the relation is ``2 x values_per_read``
    seconds -- 10 s at VPR=5, 20 s at VPR=10, 200 s at VPR=100.

    Parameters
    ----------
    values_per_read : int
        The FX4 ``ValuesPerRead`` setting.
    ring_size : int
        Driver ring-buffer size from ``FX4.cmd``.  Defaults to
        :data:`RING_SIZE_SAMPLES`.

    Returns
    -------
    float
        Longest integration time, seconds, that fits in the ring buffer.
    """
    return ring_size * values_per_read / 100_000
