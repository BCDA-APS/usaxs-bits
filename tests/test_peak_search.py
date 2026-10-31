"""Tests for the find_* peak-bracketing decision.  No EPICS, no apsbits."""

import numpy as np

from usaxs.utils.peak_search import FLAT
from usaxs.utils.peak_search import HIGH_EDGE
from usaxs.utils.peak_search import INSIDE
from usaxs.utils.peak_search import LOW_EDGE
from usaxs.utils.peak_search import locate_peak

# find_ar scan 33, 2026-10-31: the wide scan that lineup2 accepted as a peak.
# UPD (pA) only climbs; the rocking curve is beyond the upper edge.
SCAN_33_UPD = [
    4.9501, 4.7346, 4.6346, 4.651, 4.65, 5.0204, 4.8155, 4.8565, 5.1213,
    5.1982, 5.1068, 5.0188, 5.5007, 5.2827, 5.4527, 5.7433, 5.5521, 5.4761,
    5.9584, 6.0233, 5.8798, 6.1786, 5.9739, 6.7896, 6.6169, 6.8148, 6.6236,
    6.4421, 7.2382, 7.2356, 7.1847, 7.3394, 7.4168, 7.1029, 7.9839, 8.2628,
    8.3206, 7.992, 8.6283, 9.5171, 8.6916, 8.9413, 9.8005, 10.611, 10.749,
    10.969, 10.941, 11.035, 11.731, 12.066, 12.52, 12.6, 13.75, 13.706,
    14.91, 14.856, 15.69, 16.208, 16.716, 17.367, 19.029,
]  # fmt: skip
SCAN_33_AR = np.linspace(13.331140, 13.334143, len(SCAN_33_UPD))


def _gaussian(x, center, fwhm, height=500.0, base=2.0):
    sigma = fwhm / 2.3548
    return base + height * np.exp(-0.5 * ((x - center) / sigma) ** 2)


def test_scan_33_slope_is_not_a_peak():
    """The recorded failure: the walk must go up, not tune on the slope."""
    where, _x = locate_peak(SCAN_33_AR, SCAN_33_UPD)
    assert where == HIGH_EDGE


def test_reversed_slope_walks_down():
    """A falling slope points the walk to the low edge."""
    where, _x = locate_peak(SCAN_33_AR, SCAN_33_UPD[::-1])
    assert where == LOW_EDGE


def test_peak_inside_is_found_at_its_maximum():
    """A noisy rocking curve inside the scan is located."""
    x = np.linspace(-0.0015, 0.0015, 61)
    rng = np.random.default_rng(1)
    y = _gaussian(x, 0.0004, 0.0002) + rng.normal(0, 0.5, x.size)
    where, x_at_max = locate_peak(x, y)
    assert where == INSIDE
    assert abs(x_at_max - 0.0004) < 0.0001


def test_peak_near_but_not_at_an_edge_is_still_inside():
    """A peak a few points in from an edge needs no step."""
    x = np.linspace(-0.0015, 0.0015, 61)
    where, _x = locate_peak(x, _gaussian(x, -0.0010, 0.0002))
    assert where == INSIDE


def test_noisy_slope_with_interior_bump_is_still_a_slope():
    """Noise near the top of a ramp must not pass as an interior peak."""
    x = np.linspace(0, 1, 61)
    y = 5 + 10 * x
    y[50] += 3  # one bump, ten points from the end
    where, _x = locate_peak(x, y)
    assert where == HIGH_EDGE


def test_no_signal_is_flat():
    """Noise with no beam gives no direction to walk in."""
    x = np.linspace(0, 1, 61)
    rng = np.random.default_rng(2)
    where, _x = locate_peak(x, 4.6 + rng.normal(0, 0.2, x.size))
    assert where == FLAT


def test_no_signal_is_flat_whatever_the_offset():
    """Pure noise is FLAT on a small dark offset too, where a ratio test fails."""
    x = np.linspace(0, 1, 61)
    for seed in range(20):
        rng = np.random.default_rng(seed)
        where, _x = locate_peak(x, 2.0 + rng.normal(0, 0.3, x.size))
        assert where == FLAT, seed
