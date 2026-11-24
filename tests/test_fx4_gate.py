"""Tests for the FX4 fly-scan gating helpers."""

import pytest

from usaxs.utils.fx4_gate import DEFAULT_FLYSCAN_TRIGGER_MODE
from usaxs.utils.fx4_gate import FAST_GATE_FIRMWARE
from usaxs.utils.fx4_gate import FLYSCAN_AVERAGING_TIME
from usaxs.utils.fx4_gate import FLYSCAN_TRIGGER_POLARITY
from usaxs.utils.fx4_gate import TRIGGER_MODE_BULB
from usaxs.utils.fx4_gate import TRIGGER_MODE_TRIG
from usaxs.utils.fx4_gate import FX4FirmwareError
from usaxs.utils.fx4_gate import check_fast_gate_firmware
from usaxs.utils.fx4_gate import expected_flyscan_points
from usaxs.utils.fx4_gate import parse_firmware_version
from usaxs.utils.fx4_gate import point_count_problems
from usaxs.utils.fx4_gate import resolve_flyscan_trigger_mode
from usaxs.utils.fx4_gate import truncated_points


def test_default_is_edge_triggered_on_the_rising_edge():
    """The fly scan defaults to Ext. trig., Positive; bulb stays Negative."""
    assert DEFAULT_FLYSCAN_TRIGGER_MODE == TRIGGER_MODE_TRIG == "Ext. trig."
    assert FLYSCAN_TRIGGER_POLARITY[TRIGGER_MODE_TRIG] == "Positive"
    assert FLYSCAN_TRIGGER_POLARITY[TRIGGER_MODE_BULB] == "Negative"


@pytest.mark.parametrize("requested", [None, ""])
def test_empty_override_means_default(requested):
    """An unset soft signal selects the default mode."""
    assert resolve_flyscan_trigger_mode(requested) == TRIGGER_MODE_TRIG


def test_bulb_can_be_selected():
    """The rollback mode is accepted verbatim."""
    assert resolve_flyscan_trigger_mode("Ext. bulb") == TRIGGER_MODE_BULB


@pytest.mark.parametrize("typo", ["Ext. Trig.", "trig", "Ext. gate", "Free run"])
def test_unknown_mode_is_refused(typo):
    """A typo, including the wrong case, must not silently pick a mode."""
    with pytest.raises(ValueError):
        resolve_flyscan_trigger_mode(typo)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("26.10.151957", (26, 10, 151957)),
        ("26.10.151957\x00", (26, 10, 151957)),
        (" 25.3.1 ", (25, 3, 1)),
        ("", None),
        (None, None),
        ("Unknown", None),
    ],
)
def test_parse_firmware_version(text, expected):
    """Version strings compare as integer tuples; junk is None."""
    assert parse_firmware_version(text) == expected


def test_both_boxes_on_fast_firmware_pass():
    """The configuration verified on 2026-11-17."""
    check_fast_gate_firmware({"fx4": FAST_GATE_FIRMWARE, "fx42": FAST_GATE_FIRMWARE})


def test_newer_firmware_passes():
    """A later release on both boxes is fine."""
    check_fast_gate_firmware({"fx4": "27.1.1", "fx42": "27.1.1"})


@pytest.mark.parametrize(
    "firmware",
    [
        {"fx4": "25.9.1", "fx42": FAST_GATE_FIRMWARE},  # one box not upgraded
        {"fx4": None, "fx42": FAST_GATE_FIRMWARE},  # unreadable is not ready
        {"fx4": "", "fx42": FAST_GATE_FIRMWARE},
        {"fx4": FAST_GATE_FIRMWARE, "fx42": "27.1.1"},  # mismatched
    ],
)
def test_unready_or_mixed_boxes_raise(firmware):
    """Never fly Ext. trig. unless both boxes match on fast-gate firmware."""
    with pytest.raises(FX4FirmwareError):
        check_fast_gate_firmware(firmware)


@pytest.mark.parametrize("mode", [TRIGGER_MODE_TRIG, TRIGGER_MODE_BULB])
def test_n_pulses_give_n_points(mode):
    """Measured: 4000 and 8000 pulses gave 4000 and 8000 points."""
    assert expected_flyscan_points(4000, mode) == 4000
    assert expected_flyscan_points(8000, mode) == 8000


def test_matching_complete_counts_are_clean():
    """Both boxes at the expected count is no problem."""
    assert point_count_problems({"fx4": 8000, "fx42": 8000}, 8000) == []


def test_one_trailing_extra_point_is_tolerated():
    """Seen once in testing; a trailing point does not shift the data."""
    assert point_count_problems({"fx4": 8001, "fx42": 8001}, 8000) == []


def test_missing_points_are_reported():
    """A short count names the box and how many are missing."""
    problems = point_count_problems({"fx4": 3990, "fx42": 3990}, 4000)
    assert len(problems) == 2
    assert "10 missing" in problems[0]


def test_disagreeing_boxes_are_reported():
    """UPD/I0 is only valid point by point if both boxes agree."""
    problems = point_count_problems({"fx4": 4000, "fx42": 4001}, 4000)
    assert any("disagree" in p for p in problems)


def test_unreadable_count_is_reported():
    """An unreadable count is a problem, not silently ignored."""
    problems = point_count_problems({"fx4": 4000, "fx42": None}, 4000)
    assert any("unreadable" in p for p in problems)


def test_unknown_expectation_only_checks_agreement():
    """With NumPulses unreadable, the boxes are still compared."""
    assert point_count_problems({"fx4": 4000, "fx42": 4000}, 0) == []


def test_the_timeout_tail_is_not_a_truncation():
    """The last point always equals AveragingTime; that is by design."""
    channel_time = [0.031, 0.027, 0.0306, 0.014, FLYSCAN_AVERAGING_TIME]
    assert truncated_points(channel_time, FLYSCAN_AVERAGING_TIME) == []


def test_an_interval_that_hit_the_timeout_is_flagged():
    """A mid-scan point closed by the timeout is reported by index."""
    channel_time = [0.03, 0.95, 0.03, 1.0]
    assert truncated_points(channel_time, 1.0) == [1]
