
"""
motor functions
"""

__all__ = [
    'move_motors',
]

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

from apstools.utils import pairwise
import ophyd

def move_motors(*args):
    """
    move one or more motors at the same time, returns when all moves are done

    move_motors(m1, 0)
    move_motors(m2, 0, m3, 0, m4, 0)
    """
    status = []
    for m, v in pairwise(args):
        status.append(m.move(v, wait=False))

    for st in status:
        ophyd.status.wait(st)
