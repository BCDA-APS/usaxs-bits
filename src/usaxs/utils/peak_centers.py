"""
Center-of-mass and RMS width of a peak y(x).

Used to characterise tuning peaks on the USAXS Bonse-Hart instrument.
"""

import numpy as np


def peak_center(x, y, use_area=False):
    """Calculate center-of-mass and RMS width (2σ) of a peak.

    Parameters
    ----------
    x : array-like
        Independent variable (e.g. motor positions).  At least 10 points required.
    y : array-like
        Peak intensity values, same length as x.
    use_area : bool, optional
        If True, weight by trapezoidal bin areas (∫ y dx per interval) rather
        than raw y values.  Default is False.

    Returns
    -------
    x_bar : float
        Center-of-mass position along x.
    width : float
        2 * sqrt(|variance|), a measure of peak width.
        Uses absolute value to guard against numerical noise giving a tiny
        negative variance; however, if sum(y) == 0 the result will be nan.

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

    if use_area:
        x1 = np.array(x[:-1])  # all but the last
        x2 = np.array(x[1:])  # all but the first
        y1 = np.array(y[:-1])  # ditto
        y2 = np.array(y[1:])

        x = (x1 + x2) / 2  # midpoints
        y = 0.5 * (y1 + y2) * (x2 - x1)  # areas
    else:
        x = np.array(x)
        y = np.array(y)

    # let numpy do this work with arrays
    sum_y = y.sum()
    sum_yx = (y * x).sum()
    sum_yxx = (y * x * x).sum()

    x_bar = sum_yx / sum_y
    variance = sum_yxx / sum_y - x_bar * x_bar
    width = 2 * np.sqrt(abs(variance))
    return x_bar, width
