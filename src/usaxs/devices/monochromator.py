"""
Double-crystal monochromator (DCM) support for the 12-ID-E USAXS instrument.

``My12EidDcmEnergy``
    PVPositionerSoftDoneWithStop for the DCM energy axis (keV).  Reads from
    the energy-calibration calc record and drives via the E2P converter.
``My12EidWavelengthRO``
    Read-only wavelength signal with a ``.position`` property for uniform
    positioner-style access (Å).
``My12IdEDcm``
    Composite device grouping energy, wavelength, and theta motor.
``DCM_Feedback``
    EPID-record-based feedback controller (``fb_epid``) for the mono piezo.
    Driven through ``usxLAX:fbe:omega`` with Galil A-out channel.
``MyMonochromator``
    Top-level device aggregating DCM and feedback sub-devices.
"""

import logging

from apstools.devices import PVPositionerSoftDoneWithStop
from ophyd import Component
from ophyd import Device
from ophyd import EpicsMotor
from ophyd import EpicsSignal
from ophyd import EpicsSignalRO

logger = logging.getLogger(__name__)


class My12EidDcmEnergy(PVPositionerSoftDoneWithStop):
    """PVPositioner for DCM energy in keV.

    ``readback`` reads from ``12ida2:EnCalc`` (energy-calibration calc record).
    ``setpoint`` drives ``12ida2:E2P_driveValue.A`` (energy-to-piezo converter).
    ``stop_signal`` writes 1 to ``12ida2:Mono_STOP`` to halt motion.
    Settled when |readback − setpoint| < 0.0002 keV.
    """

    readback = Component(EpicsSignalRO, "12ida2:EnCalc")
    setpoint = Component(EpicsSignal, "12ida2:E2P_driveValue.A")
    egu = "keV"
    stop_signal = Component(EpicsSignal, "12ida2:Mono_STOP", kind="omitted")
    stop_value = 1


class My12EidWavelengthRO(EpicsSignalRO):
    """Read-only wavelength signal with a ``.position`` property.

    Allows uniform positioner-style access (``wavelength.position``) alongside
    the standard EpicsSignalRO ``.get()`` interface.
    """

    @property
    def position(self) -> float:
        """Return the current wavelength in Å."""
        return self.get()


class My12IdEDcm(Device):
    """Double-crystal monochromator axes for 12-ID-E.

    ``energy``
        Energy positioner in keV (:class:`My12EidDcmEnergy`).  The
        ``setpoint_pv`` / ``readback_pv`` keyword arguments are required by
        ``PVPositionerSoftDoneWithStop`` but are ignored here because the
        sub-Components already define ``readback`` and ``setpoint`` explicitly.
    ``wavelength``
        Read-only wavelength in Å (``12ida2:LambdaCalc``).
    ``theta``
        DCM theta motor (``12ida2:m19``).
    """

    energy = Component(
        My12EidDcmEnergy,
        "",
        setpoint_pv="setpoint",   # ignored — Component already defined
        readback_pv="readback",   # ignored — Component already defined
        tolerance=0.0002,
    )
    wavelength = Component(My12EidWavelengthRO, "12ida2:LambdaCalc")
    theta = Component(EpicsMotor, "12ida2:m19")


class DCM_Feedback(Device):
    """EPID-record-based monochromator piezo feedback (``fb_epid``).

    Instantiated with the ``usxLAX:fbe:omega`` prefix.  All PV suffixes are
    relative to that prefix.

    ``control`` — EPID output (the prefix PV itself, empty suffix).
    ``on``       — enable/disable the feedback loop (``:on``).
    ``drvh``     — high drive limit (``.DRVH``).
    ``drvl``     — low drive limit (``.DRVL``).
    ``oval``     — current output value (``.OVAL``).
    """

    control = Component(EpicsSignal, "")
    on = Component(EpicsSignal, ":on")
    drvh = Component(EpicsSignal, ".DRVH")
    drvl = Component(EpicsSignal, ".DRVL")
    oval = Component(EpicsSignal, ".OVAL")

    @property
    def is_on(self) -> bool:
        """Return True if the feedback loop is enabled (``on`` == 1)."""
        return self.on.get() == 1


class MyMonochromator(Device):
    """Top-level monochromator device for 12-ID-E USAXS.

    ``dcm``      — double-crystal monochromator axes (:class:`My12IdEDcm`).
    ``feedback`` — EPID piezo feedback controller (:class:`DCM_Feedback`).
    """

    dcm = Component(My12IdEDcm, "")
    feedback = Component(DCM_Feedback, "usxLAX:fbe:omega")
