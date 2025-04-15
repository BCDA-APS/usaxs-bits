"""
report how much time remains in flyscan
"""

__all__ = [
    "remaining_time_reporter",
]


import logging
import time

from apstools.utils import run_in_thread

logger = logging.getLogger(__name__)
logger.info(__file__)


@run_in_thread
def remaining_time_reporter(title, duration_s, interval_s=5, poll_s=0.05):
    if duration_s < interval_s:
        return
    t = time.time()
    expires = t + duration_s
    update = t + interval_s
    # print()
    while time.time() < expires:
        remaining = expires - t
        if t > update:
            update += interval_s
            logger.info(f"{title}: {remaining:.1f}s remaining")
        time.sleep(poll_s)
        t = time.time()


def remaining_time_reporter(t0, n, total):
    """Report the estimated remaining time for a process.

    This function calculates and returns the estimated time remaining for a
    process based on the elapsed time and progress so far.

    Args:
        t0 (float): Start time in seconds since epoch
        n (int): Current step number
        total (int): Total number of steps

    Returns:
        str: Formatted string with estimated remaining time
    """
