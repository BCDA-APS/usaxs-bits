"""
USAXS Fly Scan trajectories
"""

from ophyd import Component
from ophyd import Device
from ophyd import EpicsSignal


class Trajectories(Device):
    """fly scan trajectories"""

    # ar = Component(EpicsSignal, "usxLAX:traj1:M1Traj")
    # ax = Component(EpicsSignal, "usxLAX:traj3:M1Traj")
    # dx = Component(EpicsSignal, "usxLAX:traj2:M1Traj")
    ar = Component(EpicsSignal, "usxAERO:pm1:M6Positions")
    ax = Component(EpicsSignal, "usxAERO:pm1:M4Positions")
    dx = Component(EpicsSignal, "usxAERO:pm1:M1Positions")
    # num_pulse_positions = Component(EpicsSignal, "usxLAX:traj1:NumPulsePositions")
    num_pulse_positions = Component(EpicsSignal, "usxAERO:pm1:NumPoints")

