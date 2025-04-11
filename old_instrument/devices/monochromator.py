"""
monochromator
"""

__all__ = [
    "monochromator",
    "MONO_FEEDBACK_OFF",
    "MONO_FEEDBACK_ON",
]

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

# from apstools.devices import KohzuSeqCtl_Monochromator
from apstools.devices import PVPositionerSoftDoneWithStop
from apstools.utils import run_in_thread
from ophyd import Component
from ophyd import Device
from ophyd import EpicsMotor
from ophyd import EpicsSignal
from ophyd import EpicsSignalRO

from ..framework import sd
from .emails import email_notices


class My12EidDcmEnergy(PVPositionerSoftDoneWithStop):
    readback = Component(EpicsSignalRO, "12ida2:EnCalc")
    setpoint = Component(EpicsSignal, "12ida2:E2P_driveValue.A")
    egu = "keV"
    stop_signal = Component(EpicsSignal, "12ida2:Mono_STOP", kind="omitted")
    stop_value = 1


class My12EidWavelengthRO(EpicsSignalRO):
    @property
    def position(self):
        return self.get()


class My12IdEDcm(Device):
    energy = Component(
        My12EidDcmEnergy,
        "",  # PV prefix should be blank, in this case
        # must be defined and different from each other
        setpoint_pv="setpoint",  # ignore since 'setpoint' is already defined
        readback_pv="readback",  # ignore since 'readback' is already defined
        tolerance=0.0002,  # difference between set and read when done is declared.
    )
    wavelength = Component(My12EidWavelengthRO, "12ida2:LambdaCalc")
    theta = Component(EpicsMotor, "12ida2:m19")


# simple enumeration used by DCM_Feedback()
MONO_FEEDBACK_OFF, MONO_FEEDBACK_ON = range(2)


# TODO: fix feedback system when ready.


class DCM_Feedback(Device):
    """
    monochromator EPID-record-based feedback program: fb_epid
    12ide will for now use usxLAX:fbe:omega with
    Galil using A-out usxRIO:Galil:Ao0_SP.VAL channel for control
    of mono Piezo.
    """

    control = Component(EpicsSignal, "")
    on = Component(EpicsSignal, ":on")
    drvh = Component(EpicsSignal, ".DRVH")
    drvl = Component(EpicsSignal, ".DRVL")
    oval = Component(EpicsSignal, ".OVAL")

    @property
    def is_on(self):
        return self.on.get() == 1

    @run_in_thread
    def _send_emails(self, subject, message):
        email_notices.send(subject, message)

    def check_position(self):
        diff_hi = self.drvh.get() - self.oval.get()
        diff_lo = self.oval.get() - self.drvl.get()
        if min(diff_hi, diff_lo) < 0.2:
            subject = "USAXS Feedback problem"
            message = "Feedback is very close to its limits."
            if email_notices.notify_on_feedback:
                self._send_emails(subject, message)
            logger.warning("!" * 15)
            logger.warning(subject)
            logger.warning(message)
            logger.warning("!" * 15)


class MyMonochromator(Device):
    # dcm = Component(KohzuSeqCtl_Monochromator, "9ida:")
    dcm = Component(My12IdEDcm, "")
    feedback = Component(DCM_Feedback, "usxLAX:fbe:omega")
    # temperature = Component(EpicsSignal, "9ida:DP41:s1:temp")
    # cryo_level = Component(EpicsSignal, "9idCRYO:MainLevel:val")


monochromator = MyMonochromator(name="monochromator")
sd.baseline.append(monochromator)
