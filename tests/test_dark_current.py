"""Tests for the robust dark-current statistics.  No EPICS, no apsbits."""

import math

from usaxs.utils.dark_current import dark_is_acceptable
from usaxs.utils.dark_current import robust_dark_statistics


def test_clean_readings_pass_through_unchanged():
    """With no outliers the result is the plain mean and spread."""
    readings = [1.95, 2.0, 2.05, 1.9, 2.1]
    mean, std, kept = robust_dark_statistics(readings)
    assert kept == 5
    assert math.isclose(mean, 2.0)
    assert std < 0.1


def test_a_glitched_reading_is_rejected():
    """The 12-ID-E failure: one transient must not drag the mean negative."""
    readings = [2.0, 1.95, 2.05, 2.02, 1.98, 2.01, 1.99, 2.03, 1.97, -15.0]
    mean, std, kept = robust_dark_statistics(readings)
    assert kept == 9
    assert math.isclose(mean, 2.0, abs_tol=0.01)
    assert dark_is_acceptable(std, kept, len(readings), 0.5)


def test_identical_readings_do_not_reject_everything_else():
    """MAD = 0 must not turn every small difference into an outlier."""
    readings = [2.0] * 8 + [2.005, 1.995]
    _mean, _std, kept = robust_dark_statistics(readings)
    assert kept == 10


def test_non_finite_readings_are_dropped():
    """A NaN from a bad read is ignored, and all-NaN yields NaN, kept 0."""
    _mean, _std, kept = robust_dark_statistics([2.0, float("nan"), 2.0])
    assert kept == 2
    mean, std, kept = robust_dark_statistics([float("nan")])
    assert kept == 0 and math.isnan(mean) and math.isnan(std)


def test_noisy_measurement_is_not_acceptable():
    """A spread like the -1.6 +/- 6 pA one is refused."""
    readings = [-8.0, 5.0, -6.0, 7.0, 0.5, -3.0, 4.0, -9.0, 2.0, -1.5]
    _mean, std, kept = robust_dark_statistics(readings)
    assert not dark_is_acceptable(std, kept, len(readings), 0.5)


def test_acceptance_needs_most_readings_to_survive():
    """If the 'outliers' are the majority, the median is not trusted."""
    assert not dark_is_acceptable(0.01, 4, 10, 0.5)
    assert dark_is_acceptable(0.01, 5, 10, 0.5)
    assert not dark_is_acceptable(float("nan"), 10, 10, 0.5)
