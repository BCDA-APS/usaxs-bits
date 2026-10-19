"""Tests for the FX4 count-time helpers."""

import pytest

from usaxs.utils.count_time import MAINS_FREQUENCY_HZ
from usaxs.utils.count_time import MIN_STROBE_SAMPLE_PERIODS
from usaxs.utils.count_time import RING_SIZE_SAMPLES
from usaxs.utils.count_time import max_count_time
from usaxs.utils.count_time import min_strobe_width_us
from usaxs.utils.count_time import quantize_count_time
from usaxs.utils.count_time import sample_time
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


@pytest.mark.parametrize("values_per_read", [5, 10, 20, 50, 100])
def test_max_count_time_matches_the_ring_buffer(values_per_read):
    """A reading of exactly the ceiling fills the ring buffer and no more.

    Stated against RING_SIZE_SAMPLES rather than hard-coded seconds: the IOC's
    RING_SIZE has been raised twice (10000 -> 100000 -> 200000) and the literal
    version of this test went stale both times.
    """
    longest = max_count_time(values_per_read)
    assert samples_per_reading(longest, values_per_read) == RING_SIZE_SAMPLES


def test_max_count_time_at_the_current_ring_size():
    """At RING_SIZE=200000 the ceiling is 2 x ValuesPerRead seconds."""
    assert RING_SIZE_SAMPLES == 200_000
    assert max_count_time(5) == pytest.approx(10.0)
    assert max_count_time(100) == pytest.approx(200.0)


def test_samples_per_reading():
    """Sample count follows count_time x 100 kHz / ValuesPerRead."""
    assert samples_per_reading(0.1, 100) == 100
    assert samples_per_reading(1.0, 10) == 10_000
    assert samples_per_reading(5.0, 100) == 5_000


@pytest.mark.parametrize(
    "values_per_read, period_us",
    [(1, 10.0), (5, 50.0), (10, 100.0), (100, 1000.0)],
)
def test_sample_time_is_values_per_read_times_10_us(values_per_read, period_us):
    """SampleTime = ValuesPerRead x 10 us, matching SampleTime_RBV."""
    assert sample_time(values_per_read) == pytest.approx(period_us * 1e-6)


def test_min_strobe_width_scales_with_the_sample_period():
    """The gate is sampled at the streamed rate, so the floor scales with VPR."""
    assert min_strobe_width_us(5) == pytest.approx(250.0)
    assert min_strobe_width_us(10) == pytest.approx(500.0)
    assert min_strobe_width_us(100) == pytest.approx(5000.0)


def test_the_strobe_check_would_have_caught_the_2026_09_27_pairing():
    """1200 us was set believing VPR=10; the boxes were at 100 and merged."""
    assert 1200.0 >= min_strobe_width_us(10)  # as intended: fine
    assert 1200.0 < min_strobe_width_us(100)  # as it actually ran: not fine


def test_600_us_strobe_is_within_reach_at_vpr_5():
    """The configuration under test: 600 us needs VPR <= 10, comfortably at 5."""
    assert 600.0 >= min_strobe_width_us(5)
    assert 600.0 >= min_strobe_width_us(10)
    assert 600.0 < min_strobe_width_us(20)


def test_min_strobe_width_honours_a_different_margin():
    """3 sample periods is the optimistic end of the documented 3-5 window."""
    assert MIN_STROBE_SAMPLE_PERIODS == 5
    assert min_strobe_width_us(10, periods=3) == pytest.approx(300.0)
