
"""
EPICS data about the sample
"""

__all__ = [
    'sample_data',
    ]

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

from apstools.utils import trim_string_for_EPICS
from bluesky import plan_stubs as bps
from ophyd import Component, Device, EpicsSignal

from ..framework import sd


class SampleDataDevice(Device):
    """sample information, (initially) based on NeXus requirements"""
    temperature = Component(EpicsSignal, "9idcSample:Temperature")
    concentration = Component(EpicsSignal, "9idcSample:Concentration")
    volume_fraction = Component(EpicsSignal, "9idcSample:VolumeFraction")
    scattering_length_density = Component(EpicsSignal, "9idcSample:ScatteringLengthDensity")
    magnetic_field = Component(EpicsSignal, "9idcSample:MagneticField")
    stress_field = Component(EpicsSignal, "9idcSample:StressField")
    electric_field = Component(EpicsSignal, "9idcSample:ElectricField")
    x_translation = Component(EpicsSignal, "9idcSample:XTranslation")
    rotation_angle = Component(EpicsSignal, "9idcSample:RotationAngle")

    magnetic_field_dir = Component(EpicsSignal, "9idcSample:MagneticFieldDir", string=True)
    stress_field_dir = Component(EpicsSignal, "9idcSample:StressFieldDir", string=True)
    electric_field_dir = Component(EpicsSignal, "9idcSample:ElectricFieldDir", string=True)

    description = Component(EpicsSignal, "9idcSample:Description", string=True)
    chemical_formula = Component(EpicsSignal, "9idcSample:ChemicalFormula", string=True)

    def resetAll(self):
        """bluesky plan to reset all to preset values"""
        yield from bps.mv(
            self.temperature, 25,
            self.concentration, 1,
            self.volume_fraction, 1,
            self.scattering_length_density, 1,
            self.magnetic_field, 0,
            self.stress_field, 0,
            self.electric_field, 0,
            self.x_translation, 0,
            self.rotation_angle, 0,

            self.magnetic_field_dir, "X",
            self.stress_field_dir, "X",
            self.electric_field_dir, "X",

            self.description, "",
            self.chemical_formula, "",
        )


sample_data = SampleDataDevice(name="sample_data")
sd.baseline.append(sample_data)
