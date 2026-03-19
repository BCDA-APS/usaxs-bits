"""
USAXS fly-scan trajectory device for the 12-ID-E USAXS instrument.

Wraps the Aerotech ``usxAERO:pm1:`` position-memory PVs that store the
pre-computed motor positions for each fly-scan point.
"""

from ophyd import Component
from ophyd import Device
from ophyd import EpicsSignal


class Trajectories(Device):
    """Pre-computed fly-scan motor trajectories stored in the Aerotech controller.

    ``ar``                 — analyzer-rotation positions (``usxAERO:pm1:M6Positions``).
    ``ax``                 — a-stage X positions (``usxAERO:pm1:M4Positions``).
    ``dx``                 — detector X positions (``usxAERO:pm1:M1Positions``).
    ``num_pulse_positions``— number of valid points in the trajectory
                             (``usxAERO:pm1:NumPoints``).
    """

    ar = Component(EpicsSignal, "usxAERO:pm1:M6Positions")
    ax = Component(EpicsSignal, "usxAERO:pm1:M4Positions")
    dx = Component(EpicsSignal, "usxAERO:pm1:M1Positions")
    num_pulse_positions = Component(EpicsSignal, "usxAERO:pm1:NumPoints")
