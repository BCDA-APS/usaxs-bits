"""
derivative of two vectors: y(x), returns y'(x)
"""

__all__ = [
    "numerical_derivative",
]


import numpy as np


def numerical_derivative(x, y):
    """
    computes first derivative yp(xp) of y(x), returns tuple (xp, yp)

    here, xp is at midpoints of x
    """
    if len(x) < 10:
        raise ValueError(f"Need more points to analyze, received {len(x)}")
    if len(x) != len(y):
        raise ValueError(
            f"X & Y arrays must be same length to analyze, x:{len(x)} y:{len(y)}"
        )
    x1 = np.array(x[:-1])  # all but the last
    x2 = np.array(x[1:])  # all but the first
    y1 = np.array(y[:-1])  # ditto
    y2 = np.array(y[1:])
    # let numpy do this work with arrays
    xp = (x2 + x1) / 2  # midpoint
    yp = (y2 - y1) / (x2 - x1)  # slope
    return xp, yp
