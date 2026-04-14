"""
Sample metadata device for the 12-ID-E USAXS instrument.

Exposes NeXus-required sample properties (temperature, concentration, fields,
etc.) as EPICS PVs under the ``usxSample:`` prefix.
"""

from bluesky import plan_stubs as bps
from ophyd import Component
from ophyd import Device
from ophyd import EpicsSignal


class SampleDataDevice(Device):
    """EPICS PVs describing the current sample, based on NeXus requirements.

    Numeric fields (SI units):
        ``temperature``              — sample temperature (°C)
        ``concentration``            — concentration
        ``volume_fraction``          — volume fraction
        ``scattering_length_density``— SLD
        ``magnetic_field``           — applied magnetic field
        ``stress_field``             — applied stress field
        ``electric_field``           — applied electric field
        ``x_translation``            — sample X translation (mm)
        ``rotation_angle``           — sample rotation angle (°)

    Direction strings (``"X"``, ``"Y"``, ``"Z"``, …):
        ``magnetic_field_dir``, ``stress_field_dir``, ``electric_field_dir``

    Text fields:
        ``description``, ``chemical_formula``
    """

    temperature = Component(EpicsSignal, "usxSample:Temperature")
    concentration = Component(EpicsSignal, "usxSample:Concentration")
    volume_fraction = Component(EpicsSignal, "usxSample:VolumeFraction")
    scattering_length_density = Component(
        EpicsSignal, "usxSample:ScatteringLengthDensity"
    )
    magnetic_field = Component(EpicsSignal, "usxSample:MagneticField")
    stress_field = Component(EpicsSignal, "usxSample:StressField")
    electric_field = Component(EpicsSignal, "usxSample:ElectricField")
    x_translation = Component(EpicsSignal, "usxSample:XTranslation")
    rotation_angle = Component(EpicsSignal, "usxSample:RotationAngle")

    magnetic_field_dir = Component(
        EpicsSignal, "usxSample:MagneticFieldDir", string=True
    )
    stress_field_dir = Component(
        EpicsSignal, "usxSample:StressFieldDir", string=True
    )
    electric_field_dir = Component(
        EpicsSignal, "usxSample:ElectricFieldDir", string=True
    )

    description = Component(EpicsSignal, "usxSample:Description", string=True)
    chemical_formula = Component(
        EpicsSignal, "usxSample:ChemicalFormula", string=True
    )

    def resetAll(self):
        """Bluesky plan: reset all sample fields to their default values.

        Defaults: temperature=25 °C, concentration=volume_fraction=SLD=1,
        all fields=0, all directions="X", description=chemical_formula="".

        Yields
        ------
        Bluesky messages.
        """
        yield from bps.mv(
            # fmt: off
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
            # fmt: on
        )
