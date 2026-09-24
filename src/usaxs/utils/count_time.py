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


def samples_per_reading(count_time: float, values_per_read: int) -> int:
    """Return how many streamed samples one reading of *count_time* contains.

    The FX4 digitises at 100 kHz and pre-averages ``values_per_read``
    conversions into each streamed sample, so ``SampleTime = values_per_read x
    10 us``.  The driver accumulates those samples in a ring buffer whose size
    (``RING_SIZE``, default 10000, set in ``FX4.cmd``) caps one reading.  Past
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


def max_count_time(values_per_read: int, ring_size: int = 10_000) -> float:
    """Return the longest unbiased integration time for a ``ValuesPerRead``.

    Above this the driver's ring buffer overflows and the mean is biased.  At
    the default ``RING_SIZE`` the relation is simply ``values_per_read / 10``
    seconds -- 1 s at VPR=10, 10 s at VPR=100.

    Parameters
    ----------
    values_per_read : int
        The FX4 ``ValuesPerRead`` setting.
    ring_size : int
        Driver ring-buffer size from ``FX4.cmd``.  Default 10000.

    Returns
    -------
    float
        Longest integration time, seconds, that fits in the ring buffer.
    """
    return ring_size * values_per_read / 100_000
