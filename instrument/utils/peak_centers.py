
"""
center-of-mass and sqrt(variance) of y(x)
"""

__all__ = ["peak_center",]

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

import numpy as np

def peak_center(x, y, use_area=False):
    """
    calculate center-of-mass and sqrt(variance) of y vs. x
    """
    if len(x) < 10:
        raise ValueError(f"Need more points to analyze, received {len(x)}")
    if len(x) != len(y):
        raise ValueError(f"X & Y arrays must be same length to analyze, x:{len(x)} y:{len(y)}")

    if use_area:
        x1 = np.array(x[:-1])       # all but the last
        x2 = np.array(x[1:])        # all but the first
        y1 = np.array(y[:-1])       # ditto
        y2 = np.array(y[1:])

        x = (x1+x2)/2               # midpoints
        y = 0.5*(y1+y2) * (x2-x1)   # areas
    else:
        x = np.array(x)
        y = np.array(y)

    # let numpy do this work with arrays
    sum_y = y.sum()
    sum_yx = (y*x).sum()
    sum_yxx = (y*x*x).sum()

    x_bar = sum_yx / sum_y
    variance = sum_yxx / sum_y - x_bar*x_bar
    width = 2 * np.sqrt(abs(variance))
    return x_bar, width
