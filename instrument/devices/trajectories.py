
"""
USAXS Fly Scan trajectories
"""

__all__ = [
    'flyscan_trajectories',
    ]

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

from ophyd import Component, Device, EpicsSignal


class Trajectories(Device):
    """fly scan trajectories"""
    ar = Component(EpicsSignal, "usxLAX:traj1:M1Traj")
    ax = Component(EpicsSignal, "usxLAX:traj3:M1Traj")
    dx = Component(EpicsSignal, "usxLAX:traj2:M1Traj")
    num_pulse_positions = Component(EpicsSignal, "usxLAX:traj1:NumPulsePositions")

flyscan_trajectories = Trajectories(name="flyscan_trajectories")
