
"""
shutters
"""
# TODO need PSS system 
__all__ = [
    'white_beam_ready',
]

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

from ophyd import Component
from ophyd import Device
from ophyd import EpicsSignal
from ophyd import Signal

CALC_PV = "usxLAX:userCalc9"
SHUTTER_PV = "PA:12ID:STA_A_FES_OPEN_PL"
APS_CURRENT_PV = "S:SRCurrentAI"
UNDULATOR_ENERGY_PV = "ID12ds:Energy"


class WhiteBeamReadyCalc(Device):
    """
    Compute if white beam is expected to be ready.

    Based on an swait record (such as a userCalc).

    USAGE:

    - signal: ``white_beam_ready.available.get()``
    - property: ``white_beam_ready.is_available``

    If the swait record fields must be reset to default settings
    as used here, call:

        white_beam_ready.initialize_swait_record()

    Watches:

    - white beam shutter
    - APS storage ring current
    - undulator energy

    available = True when (
        shutter is open and
        both current and energy are in range
    )

    - energy must be below undulator_energy_threshold
    - current is too low when < current_off_threshold
    - current becomes OK when > current_on_threshold
    - Hysteresis in current signal is implemented.
    """
    available = Component(Signal, value=False)
    computed_value = Component(EpicsSignal, ".VAL")
    equation = Component(EpicsSignal, ".CALC", string=True)
    description = Component(EpicsSignal, ".DESC", string=True)
    scan_period = Component(EpicsSignal, ".SCAN", string=True)

    pv_last_value = Component(EpicsSignal, ".INAN", string=True)
    pv_shutter_open = Component(EpicsSignal, ".INBN", string=True)
    pv_aps_current = Component(EpicsSignal, ".INCN", string=True)
    aps_current = Component(EpicsSignal, ".C")
    current_on_threshold = Component(EpicsSignal, ".D")
    current_off_threshold = Component(EpicsSignal, ".E")
    pv_undulator_energy = Component(EpicsSignal, ".INFN", string=True)
    undulator_energy_threshold = Component(EpicsSignal, ".G")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # self.initialize_swait_record()
        self.computed_value.subscribe(self.cb_available)

    def initialize_swait_record(self):
        self.description.put("white_beam_ready")
        self.equation.put("B&((!A&(C>D))|A&(C>E))&(F<G)")
        self.pv_last_value.put(f"{self.prefix}.VAL")
        self.scan_period.put("Passive")

        self.pv_shutter_open.put(SHUTTER_PV)

        # mA, expect beam available when APS current > D,
        # declare unusable when current < 2
        self.pv_aps_current.put(APS_CURRENT_PV)
        self.current_on_threshold.put(10)
        self.current_off_threshold.put(2)

        # keV, expect beam when undulator energy < G
        self.pv_undulator_energy.put(UNDULATOR_ENERGY_PV)
        self.undulator_energy_threshold.put(35)

    def cb_available(self, *args, **kwargs):
        """Update our available attribute from {CALC_PV}.VAL."""
        self.available.put(self.computed_value.get() != 0)

    @property
    def is_available(self):
        return self.available.get()


white_beam_ready = WhiteBeamReadyCalc(CALC_PV, name="white_beam_ready")
