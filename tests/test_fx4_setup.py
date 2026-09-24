"""Tests for the FX4 configuration helpers that need no EPICS connection."""

import pytest

from usaxs.devices.fx4_quadem import FX4RangeConflictError
from usaxs.plans.fx4_setup import DEFAULT_SCALER_VPR
from usaxs.plans.fx4_setup import VPR_LADDER
from usaxs.plans.fx4_setup import choose_values_per_read
from usaxs.plans.fx4_setup import group_controls_by_box
from usaxs.utils.count_time import max_count_time


class FakeBox:
    """Stand-in for a ``QuadFX4``; ``group_controls_by_box`` only reads .name."""

    def __init__(self, name):
        """Record the electrometer's ophyd name."""
        self.name = name


class FakeControls:
    """Stand-in for ``FX4DetectorControls`` with no EPICS behind it."""

    def __init__(self, nickname, box, channel, autoranged=True):
        """Record the detector nickname, box, channel and autorange state."""
        self.nickname = nickname
        self.quadem = box
        self.channel_number = channel
        self.auto = object() if autoranged else None

    @property
    def autoranged(self):
        """Return True when an autorange sequence program is attached."""
        return self.auto is not None


@pytest.mark.parametrize("count_time", [0.1, 1.0, 5.0, 10.0])
def test_chosen_vpr_keeps_the_reading_inside_the_ring_buffer(count_time):
    """The chosen ValuesPerRead always supports the requested count time."""
    vpr = choose_values_per_read(count_time)
    assert vpr in VPR_LADDER
    assert count_time <= max_count_time(vpr)


def test_chosen_vpr_respects_the_minimum():
    """Short counts still get the default VPR, not the smallest that fits."""
    assert choose_values_per_read(0.1) == DEFAULT_SCALER_VPR


def test_chosen_vpr_rises_for_long_counts():
    """A count longer than the default VPR allows moves up the ladder."""
    assert max_count_time(DEFAULT_SCALER_VPR) == pytest.approx(10.0)
    assert choose_values_per_read(20.0) > DEFAULT_SCALER_VPR


def test_chosen_vpr_refuses_the_impossible():
    """Beyond the ladder the fix is RING_SIZE, so say so instead of guessing."""
    with pytest.raises(ValueError, match="RING_SIZE"):
        choose_values_per_read(10_000.0)


def test_one_autoranged_channel_per_box_is_fine():
    """UPD on fx4 and I0 on fx42 is the normal case."""
    fx4, fx42 = FakeBox("fx4"), FakeBox("fx42")
    upd = FakeControls("UPD", fx4, 1)
    i0 = FakeControls("I0", fx42, 1)
    grouped = group_controls_by_box([upd, i0])
    assert grouped == {"fx4": upd, "fx42": i0}


def test_fixed_range_detectors_are_skipped():
    """A detector with no sequence program has nothing to converge."""
    fx4, fx42 = FakeBox("fx4"), FakeBox("fx42")
    upd = FakeControls("UPD", fx4, 1)
    i0 = FakeControls("I0", fx42, 1, autoranged=False)
    assert group_controls_by_box([upd, i0]) == {"fx4": upd}


def test_fixed_range_detectors_do_not_cause_a_conflict():
    """I0 and I00 both fixed on fx42 is legal; neither is autoranged."""
    fx42 = FakeBox("fx42")
    i0 = FakeControls("I0", fx42, 1, autoranged=False)
    i00 = FakeControls("I00", fx42, 2, autoranged=False)
    assert group_controls_by_box([i0, i00]) == {}


def test_two_autoranged_channels_on_one_box_is_an_error():
    """UPD and TRD share one Range; converging both is not possible."""
    fx4 = FakeBox("fx4")
    upd = FakeControls("UPD", fx4, 1)
    trd = FakeControls("TRD", fx4, 4)
    with pytest.raises(FX4RangeConflictError) as exc:
        group_controls_by_box([upd, trd])
    # the message must name both detectors, so the log says what to fix
    assert "UPD" in str(exc.value)
    assert "TRD" in str(exc.value)


def test_group_controls_rejects_a_bare_control():
    """Passing one control instead of a list is a common slip."""
    with pytest.raises(ValueError):
        group_controls_by_box(FakeControls("UPD", FakeBox("fx4"), 1))
