"""
rotate the sample with PI C867 motor
"""

__all__ = """
    PI_Off
    PI_onF
    PI_onR
""".split()

import logging
from typing import Any
from typing import Dict
from typing import Generator
from typing import Optional

from bluesky import plan_stubs as bps

from ..devices import pi_c867

logger = logging.getLogger(__name__)
logger.info(__file__)


def PI_Off(
    timeout: float = 1, md: Optional[Dict[str, Any]] = None
) -> Generator[Any, None, None]:
    """
    Plan: stop rotating sample in either direction.

    NOTE:
        Do NOT stop either jog by sending 1 to the
        motor `.STOP` field.  That will result in a
        `FailedStatus` exception if the motor is
        in motion.
    """
    yield from bps.mv(
        pi_c867.jog_forward,
        0,
        pi_c867.jog_reverse,
        0,
        timeout=1,
    )


def PI_onF(
    timeout: float = 20, md: Optional[Dict[str, Any]] = None
) -> Generator[Any, None, None]:
    """Plan: start rotating sample in forward direction."""
    yield from bps.mv(pi_c867.home, "forward", timeout=timeout)
    yield from bps.abs_set(pi_c867.jog_forward, 1)


def PI_onR(
    timeout: float = 20, md: Optional[Dict[str, Any]] = None
) -> Generator[Any, None, None]:
    """Plan: start rotating sample in reverse direction."""
    yield from bps.mv(pi_c867.home, "reverse", timeout=timeout)
    yield from bps.abs_set(pi_c867.jog_reverse, 1)
