"""
example motors
"""

__all__ = """
    m1  m2  m3  m4
    m5  m6  m7  m8
""".split()

import logging

logger = logging.getLogger(__name__)

logger.info(__file__)

from ophyd import EpicsMotor

from .. import iconfig

IOC = iconfig.get("GP_IOC_PREFIX", "usxLAX:m58:c0:")

m1 = EpicsMotor(f"{IOC}m1", name="LAXm1", labels=("LAXm1",))
m2 = EpicsMotor(f"{IOC}m2", name="LAXm2", labels=("LAXm2",))
m3 = EpicsMotor(f"{IOC}m3", name="LAXm3", labels=("LAXm3",))
m4 = EpicsMotor(f"{IOC}m4", name="LAXm4", labels=("LAXm4",))
m5 = EpicsMotor(f"{IOC}m5", name="LAXm5", labels=("LAXtcam",))
m6 = EpicsMotor(f"{IOC}m6", name="LAXm6", labels=("LAXgsY",))
m7 = EpicsMotor(f"{IOC}m7", name="LAXm7", labels=("LAXgsX",))
m8 = EpicsMotor(f"{IOC}m8", name="LAXm8", labels=("LAXm8",))
