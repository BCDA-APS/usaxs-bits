"""
USAXS Fly Scan trajectories
"""

from ophyd import Component
from ophyd import Device
from ophyd import EpicsSignal


class Trajectories(Device):
    """Fly scan trajectories for USAXS instrument.

    This device manages the trajectory signals for different motor positions
    during fly scans. It provides access to position signals for ar, ax, and dx
    motors, as well as the number of pulse positions.

    Attributes:
        ar: EpicsSignal for ar motor positions
        ax: EpicsSignal for ax motor positions
        dx: EpicsSignal for dx motor positions
        num_pulse_positions: EpicsSignal for number of points in the trajectory
    """

    # ar = Component(EpicsSignal, "usxLAX:traj1:M1Traj")
    # ax = Component(EpicsSignal, "usxLAX:traj3:M1Traj")
    # dx = Component(EpicsSignal, "usxLAX:traj2:M1Traj")
    ar: Component[EpicsSignal] = Component(EpicsSignal, "usxAERO:pm1:M6Positions")
    ax: Component[EpicsSignal] = Component(EpicsSignal, "usxAERO:pm1:M4Positions")
    dx: Component[EpicsSignal] = Component(EpicsSignal, "usxAERO:pm1:M1Positions")
    # num_pulse_positions = Component(EpicsSignal, "usxLAX:traj1:NumPulsePositions")
    num_pulse_positions: Component[EpicsSignal] = Component(
        EpicsSignal, "usxAERO:pm1:NumPoints"
    )
