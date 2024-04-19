
"""
monochromator
"""

__all__ = [
    'monochromator',
    'MONO_FEEDBACK_OFF',
    'MONO_FEEDBACK_ON',
    ]

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

# from apstools.devices import KohzuSeqCtl_Monochromator
from apstools.devices import PVPositionerSoftDoneWithStop
from apstools.utils import run_in_thread
from ophyd import Component, Device, EpicsSignal, EpicsSignalRO, EpicsMotor

from .emails import email_notices
from ..framework import sd


class My20idDcmEnergy(PVPositionerSoftDoneWithStop):
    readback = Component(EpicsSignalRO, "9idcLAX:userCalc2.VAL")
    setpoint = Component(EpicsSignal, "9idcLAX:userCalc5.A")
    egu = "keV"
    stop_signal = Component(EpicsSignal, "20id:MonoSTOP", kind="omitted")
    stop_value = 1


class My20idWavelengthRO(EpicsSignalRO):

    @property
    def position(self):
        return self.get()


class My20IdDcm(Device):
    energy = Component(
        My20idDcmEnergy,
        "",  # PV prefix should be blank, in this case
        # must be defined and different from each other
        setpoint_pv="setpoint",  # ignore since 'setpoint' is already defined
        readback_pv="readback",  # ignore since 'readback' is already defined
    )
    wavelength = Component(My20idWavelengthRO, "9idcLAX:userCalc3.VAL")
    theta = Component(EpicsMotor, "20id:m41")


# simple enumeration used by DCM_Feedback()
MONO_FEEDBACK_OFF, MONO_FEEDBACK_ON = range(2)


class DCM_Feedback(Device):
    """
    monochromator EPID-record-based feedback program: fb_epid
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
            logger.warning("!"*15)
            logger.warning(subject, message)
            logger.warning("!"*15)


class MyMonochromator(Device):
    #dcm = Component(KohzuSeqCtl_Monochromator, "9ida:")
    dcm = Component(My20IdDcm, "")
    feedback = Component(DCM_Feedback, "9idcLAX:fbe:omega")
    #temperature = Component(EpicsSignal, "9ida:DP41:s1:temp")
    #cryo_level = Component(EpicsSignal, "9idCRYO:MainLevel:val")


monochromator = MyMonochromator(name="monochromator")
sd.baseline.append(monochromator)
