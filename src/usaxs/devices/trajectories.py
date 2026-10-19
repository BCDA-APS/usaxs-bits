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
    ``num_pulse_positions``— number of waypoints in the trajectory
                             (``usxAERO:pm1:NumPoints``).
    ``num_pulses``         — number of PSO strobes the sweep will emit, i.e.
                             the number of data points
                             (``usxAERO:pm1:NumPulses``).
    ``pulse_length``       — width of each PSO strobe, **microseconds**
                             (``usxAERO:pm1:PulseLength``).
    ``pulse_period``       — minimum spacing between strobes, **microseconds**
                             (``usxAERO:pm1:PulsePeriod``).  The Aerotech
                             driver forces ``period = length + 1`` if it is
                             not already larger, so raise it first when
                             widening the strobe.

    .. note::
       ``pulse_length`` and ``pulse_period`` carry no ``.EGU``; the unit is
       microseconds, from the records' ``.DESC`` ("pulse length in
       microseconds").  The strobe width matters to the counting chain, not
       just to the motion controller: in "Ext. bulb" mode the FX4 delimits
       its exposures on that strobe and can only see one that is several of
       its sample periods wide -- see
       ``utils.count_time.min_strobe_width_us`` and
       ``docs/FX4_PSO_trigger_issue.md``.

    .. note::
       Despite its name, ``num_pulse_positions`` is ``NumPoints`` -- the
       *waypoint* count, of order a couple of hundred.  The pulse count is
       ``NumPulses``, of order a few thousand.  ``ADconfigs/Flyscan_config/
       saveFlyData.xml`` is explicit about this: it records ``NumPulses`` as
       ``AR_pulses``/``AR_count`` and ``NumPoints`` as ``AR_waytpointsNum``.
       The misleading name predates this branch and is left alone because
       existing code reads it; new code should use ``num_pulses``.
    """

    ar = Component(EpicsSignal, "usxAERO:pm1:M6Positions")
    ax = Component(EpicsSignal, "usxAERO:pm1:M4Positions")
    dx = Component(EpicsSignal, "usxAERO:pm1:M1Positions")
    num_pulse_positions = Component(EpicsSignal, "usxAERO:pm1:NumPoints")
    num_pulses = Component(EpicsSignal, "usxAERO:pm1:NumPulses")
    pulse_length = Component(EpicsSignal, "usxAERO:pm1:PulseLength")
    pulse_period = Component(EpicsSignal, "usxAERO:pm1:PulsePeriod")
