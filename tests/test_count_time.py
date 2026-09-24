"""Tests for the FX4 count-time helpers."""

import pytest

from usaxs.utils.count_time import MAINS_FREQUENCY_HZ
from usaxs.utils.count_time import max_count_time
from usaxs.utils.count_time import quantize_count_time
from usaxs.utils.count_time import samples_per_reading


@pytest.mark.parametrize(
    "requested, cycles",
    [
        (0.1, 6),  # a tune count: exactly 6 cycles already
        (0.2, 12),
        (1.0, 60),
        (3.0, 180),
        (0.1 / 3, 2),  # uascan dynamic time, short third
        (0.1 * 2, 12),  # uascan dynamic time, long third
        (0.05, 3),
        (0.017, 1),
    ],
)
def test_quantize_lands_on_whole_mains_cycles(requested, cycles):
    """Every quantised count time is an integer number of mains cycles."""
    result = quantize_count_time(requested)
    assert result == pytest.approx(cycles / MAINS_FREQUENCY_HZ)
    assert round(result * MAINS_FREQUENCY_HZ) == cycles


def test_quantize_never_returns_zero():
    """A request below half a cycle is raised to one full cycle."""
    assert quantize_count_time(1e-6) == pytest.approx(1 / MAINS_FREQUENCY_HZ)


def test_quantize_stays_close_to_the_request():
    """Quantising never moves a count time by more than half a cycle."""
    half_cycle = 0.5 / MAINS_FREQUENCY_HZ
    for requested in (0.037, 0.44, 1.23, 4.9):
        assert abs(quantize_count_time(requested) - requested) <= half_cycle


@pytest.mark.parametrize("bad", [0, -1.0])
def test_quantize_rejects_nonpositive(bad):
    """A non-positive count time is a programming error, not a default."""
    with pytest.raises(ValueError):
        quantize_count_time(bad)


def test_quantize_honours_a_different_mains_frequency():
    """50 Hz mains gives 20 ms cycles."""
    assert quantize_count_time(0.1, mains_hz=50) == pytest.approx(0.1)
    assert quantize_count_time(0.03, mains_hz=50) == pytest.approx(0.04)


@pytest.mark.parametrize(
    "values_per_read, longest",
    [(10, 1.0), (20, 2.0), (50, 5.0), (100, 10.0)],
)
def test_max_count_time_matches_the_ring_buffer(values_per_read, longest):
    """The unbiased ceiling is ValuesPerRead/10 seconds at RING_SIZE=10000."""
    assert max_count_time(values_per_read) == pytest.approx(longest)
    # exactly at the limit the reading still fits
    assert samples_per_reading(longest, values_per_read) == 10_000


def test_samples_per_reading():
    """Sample count follows count_time x 100 kHz / ValuesPerRead."""
    assert samples_per_reading(0.1, 100) == 100
    assert samples_per_reading(1.0, 10) == 10_000
    assert samples_per_reading(5.0, 100) == 5_000
