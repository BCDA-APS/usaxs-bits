
"""
stages
"""

__all__ = [
    's_stage',      # sample
    'd_stage',      # detector
    'm_stage',      # collimating (monochromator)
    'ms_stage',     # side-reflecting M
    'a_stage',      # analyzer
    'as_stage',     # side-reflecting A
    'saxs_stage',   # SAXS detector
    'waxsx',        # WAXS detector X translation
    'waxs2x',       # WAXS2 detector X translation
]

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

from ophyd import Component, MotorBundle, EpicsMotor

from ..framework import sd
#from .usaxs_motor_devices import EpicsMotor
from .usaxs_motor_devices import UsaxsMotorTunable
from .usaxs_motor_devices import UsaxsArMotorTunable

class UsaxsDetectorStageDevice(MotorBundle):
    """USAXS detector stage"""
    x = Component(
        UsaxsMotorTunable,
        '9idcAERO:m1',
        labels=("detector", "tunable",))
    y = Component(
        UsaxsMotorTunable,
        '9idcAERO:m2',
        labels=("detector", "tunable",))


class UsaxsSampleStageDevice(MotorBundle):
    """USAXS sample stage"""
    x = Component(
        EpicsMotor,
        '9idcAERO:m8',
        labels=("sample",))
    y = Component(
        EpicsMotor,
        '9idcAERO:m9',
        labels=("sample",))


class UsaxsCollimatorStageDevice(MotorBundle):
    """USAXS Collimator (Monochromator) stage"""
    r = Component(UsaxsMotorTunable, '9idcAERO:m12', labels=("collimator", "tunable",))
    x = Component(EpicsMotor, '9idcAERO:m10', labels=("collimator",))
    y = Component(EpicsMotor, '9idcAERO:m11', labels=("collimator",))
    r2p = Component(UsaxsMotorTunable, '9idcLAX:pi:c0:m2', labels=("collimator", "tunable",))
    isChannelCut = True


class UsaxsCollimatorSideReflectionStageDevice(MotorBundle):
    """USAXS Collimator (Monochromator) side-reflection stage"""
    #r = Component(EpicsMotor, '9idcLAX:xps:c0:m5', labels=("side_collimator",))
    #t = Component(EpicsMotor, '9idcLAX:xps:c0:m3', labels=("side_collimator",))
    x = Component(EpicsMotor, '9idcLAX:m58:c1:m1', labels=("side_collimator",))
    y = Component(EpicsMotor, '9idcLAX:m58:c1:m2')
    rp = Component(UsaxsMotorTunable, '9idcLAX:pi:c0:m3', labels=("side_collimator", "tunable",))


class UsaxsAnalyzerStageDevice(MotorBundle):
    """USAXS Analyzer stage"""
    r = Component(UsaxsArMotorTunable, '9idcAERO:m6', labels=("analyzer", "tunable"))
    x = Component(EpicsMotor, '9idcAERO:m4', labels=("analyzer",))
    y = Component(EpicsMotor, '9idcAERO:m5', labels=("analyzer",))
    #z = Component(EpicsMotor, '9idcLAX:m58:c0:m7', labels=("analyzer",))
    r2p = Component(UsaxsMotorTunable, '9idcLAX:pi:c0:m1', labels=("analyzer", "tunable"))
    rt = Component(EpicsMotor, '9idcLAX:m58:c1:m3', labels=("analyzer",))


class UsaxsAnalyzerSideReflectionStageDevice(MotorBundle):
    """USAXS Analyzer side-reflection stage"""
    #r = Component(EpicsMotor, '9idcLAX:xps:c0:m6', labels=("analyzer",))
    #t = Component(EpicsMotor, '9idcLAX:xps:c0:m4', labels=("analyzer",))
    y = Component(EpicsMotor, '9idcLAX:m58:c1:m4', labels=("analyzer",))
    rp = Component(UsaxsMotorTunable, '9idcLAX:pi:c0:m4', labels=("analyzer", "tunable"))


class SaxsDetectorStageDevice(MotorBundle):
    """SAXS detector stage (aka: pin SAXS stage)"""
    x = Component(EpicsMotor, '9idcAERO:m13', labels=("saxs",))
    y = Component(EpicsMotor, '9idcAERO:m15', labels=("saxs",))
    z = Component(EpicsMotor, '9idcAERO:m14', labels=("saxs",))


s_stage    = UsaxsSampleStageDevice('', name='s_stage')
d_stage    = UsaxsDetectorStageDevice('', name='d_stage')

m_stage    = UsaxsCollimatorStageDevice('', name='m_stage')
ms_stage   = UsaxsCollimatorSideReflectionStageDevice('', name='ms_stage')

a_stage    = UsaxsAnalyzerStageDevice('', name='a_stage')
as_stage   = UsaxsAnalyzerSideReflectionStageDevice('', name='as_stage')

saxs_stage = SaxsDetectorStageDevice('', name='saxs_stage')

waxsx = EpicsMotor(
    '9idcAERO:m3',
    name='waxsx',
    labels=("waxs", "motor"))  # WAXS X

waxs2x = EpicsMotor(
    '9idcAERO:m7',
    name='waxs2x',
    labels=("waxs2", "motor"))  # WAXS2 X

for _s in (s_stage, d_stage, a_stage, m_stage, saxs_stage):
    sd.baseline.append(_s)

sd.baseline.append(waxsx)
sd.baseline.append(waxs2x)
