"""
EPICS data about the sample
"""

from typing import Any
from typing import Generator

from bluesky import plan_stubs as bps
from ophyd import Component
from ophyd import Device
from ophyd import EpicsSignal


class SampleDataDevice(Device):
    """Sample information, (initially) based on NeXus requirements.

    This device provides access to various sample properties and parameters
    that are stored in EPICS PVs.
    """

    temperature: Component[EpicsSignal] = Component(
        EpicsSignal, "usxSample:Temperature"
    )
    concentration: Component[EpicsSignal] = Component(
        EpicsSignal, "usxSample:Concentration"
    )
    volume_fraction: Component[EpicsSignal] = Component(
        EpicsSignal, "usxSample:VolumeFraction"
    )
    scattering_length_density: Component[EpicsSignal] = Component(
        EpicsSignal, "usxSample:ScatteringLengthDensity"
    )
    magnetic_field: Component[EpicsSignal] = Component(
        EpicsSignal, "usxSample:MagneticField"
    )
    stress_field: Component[EpicsSignal] = Component(
        EpicsSignal, "usxSample:StressField"
    )
    electric_field: Component[EpicsSignal] = Component(
        EpicsSignal, "usxSample:ElectricField"
    )
    x_translation: Component[EpicsSignal] = Component(
        EpicsSignal, "usxSample:XTranslation"
    )
    rotation_angle: Component[EpicsSignal] = Component(
        EpicsSignal, "usxSample:RotationAngle"
    )

    magnetic_field_dir: Component[EpicsSignal] = Component(
        EpicsSignal, "usxSample:MagneticFieldDir", string=True
    )
    stress_field_dir: Component[EpicsSignal] = Component(
        EpicsSignal, "usxSample:StressFieldDir", string=True
    )
    electric_field_dir: Component[EpicsSignal] = Component(
        EpicsSignal, "usxSample:ElectricFieldDir", string=True
    )

    description: Component[EpicsSignal] = Component(
        EpicsSignal, "usxSample:Description", string=True
    )
    chemical_formula: Component[EpicsSignal] = Component(
        EpicsSignal, "usxSample:ChemicalFormula", string=True
    )

    def resetAll(self) -> Generator[Any, None, None]:
        """Bluesky plan to reset all to preset values."""
        yield from bps.mv(
            self.temperature,
            25,
            self.concentration,
            1,
            self.volume_fraction,
            1,
            self.scattering_length_density,
            1,
            self.magnetic_field,
            0,
            self.stress_field,
            0,
            self.electric_field,
            0,
            self.x_translation,
            0,
            self.rotation_angle,
            0,
            self.magnetic_field_dir,
            "X",
            self.stress_field_dir,
            "X",
            self.electric_field_dir,
            "X",
            self.description,
            "",
            self.chemical_formula,
            "",
        )


sample_data = SampleDataDevice(name="sample_data")

