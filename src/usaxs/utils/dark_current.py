"""
Robust statistics for FX4 dark-current readings.

Kept free of EPICS, ophyd and ``apsbits`` so it can be unit-tested anywhere;
the plan that takes the readings is ``plans.fx4_autorange_plan.
measure_background``.

Why not a plain mean and standard deviation
-------------------------------------------
At high q the scattered signal is *smaller* than the dark current, so the
stored dark is subtracted from numbers it dominates.  A single glitched
reading -- a range switch still settling, a stale mean -- used to pull the
mean of five readings to -1.6 pA with a spread of 6 pA, against a normal
2 pA +/- 0.05.  The median and the median absolute deviation (MAD) are not
moved by one or two such readings, so outliers are rejected against them
before the mean and spread are computed from what is left.
"""

import numpy as np

MAD_TO_SIGMA = 1.4826
"""Scale factor from MAD to the standard deviation of a normal distribution."""

DEFAULT_REJECTION = 5.0
"""Readings farther than this many robust sigmas from the median are dropped."""

DEFAULT_MAD_FLOOR_PA = 0.01
"""Smallest robust sigma used for rejection, pA.

Without a floor, a set of readings that are mostly identical (MAD = 0) would
reject every reading that differs from them by any amount at all.
"""


def robust_dark_statistics(
    readings,
    rejection=DEFAULT_REJECTION,
    mad_floor_pA=DEFAULT_MAD_FLOOR_PA,
):
    """Return the mean and spread of dark readings after rejecting outliers.

    Parameters
    ----------
    readings : sequence of float
        Dark-current readings, pA.  Non-finite values are dropped.
    rejection : float
        Rejection threshold in robust sigmas (``MAD_TO_SIGMA * MAD``).
    mad_floor_pA : float
        Lower bound on the robust sigma, pA.

    Returns
    -------
    tuple
        ``(mean, std, n_kept)`` of the readings that survived.  ``mean`` and
        ``std`` are NaN when no reading survived.
    """
    values = np.asarray(readings, dtype=float)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return float("nan"), float("nan"), 0
    median = np.median(values)
    deviation = np.abs(values - median)
    sigma = max(MAD_TO_SIGMA * float(np.median(deviation)), mad_floor_pA)
    kept = values[deviation <= rejection * sigma]
    return float(np.mean(kept)), float(np.std(kept)), int(kept.size)


def dark_is_acceptable(std, n_kept, n_readings, max_error_pA):
    """Return True when a dark measurement is good enough to store.

    Parameters
    ----------
    std : float
        Spread of the surviving readings, pA.
    n_kept : int
        Number of readings that survived outlier rejection.
    n_readings : int
        Number of readings taken.
    max_error_pA : float
        Largest acceptable spread, pA.

    Returns
    -------
    bool
        False if the spread is too large or non-finite, or if fewer than half
        of the readings survived -- in that case the "outliers" are the
        majority and the median is not to be trusted either.
    """
    if not np.isfinite(std):
        return False
    if 2 * n_kept < n_readings:
        return False
    return std <= max_error_pA
