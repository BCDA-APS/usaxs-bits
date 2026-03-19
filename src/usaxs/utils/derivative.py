"""
Numerical first derivative of two vectors y(x).

Returns y'(x) evaluated at midpoints of the input x array using a
central finite-difference scheme.
"""

import numpy as np


def numerical_derivative(x, y):
    """Compute the first derivative dy/dx at midpoints of x.

    Uses a simple finite-difference formula: yp[i] = (y[i+1] - y[i]) / (x[i+1] - x[i]).
    The returned xp array has one fewer element than the input and sits at
    the midpoints between adjacent x values.

    Parameters
    ----------
    x : array-like
        Independent variable values (must be monotonic for meaningful results).
        At least 10 points are required; fewer points produce unreliable
        derivatives for the peak-fitting routines that call this function.
    y : array-like
        Dependent variable values, same length as x.

    Returns
    -------
    xp : ndarray
        Midpoints of adjacent x values, length len(x) - 1.
    yp : ndarray
        Slope (dy/dx) at each midpoint, length len(x) - 1.

    Raises
    ------
    ValueError
        If len(x) < 10 or len(x) != len(y).
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
