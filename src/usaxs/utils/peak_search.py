"""
Decide whether a wide alignment scan contains its peak, or only a slope.

``apstools.plans.lineup2`` cannot make that distinction: a monotonic ramp
passes its "strong peak" test and has a well-defined centroid, so a wide scan
that sits on the flank of a rocking curve is reported as a success and the
rescans narrow in on the middle of the slope.  That is what ``find_ar`` did on
2026-10-31 (scan 33, UPD rising 4.6 -> 19 pA to the last point).

:func:`locate_peak` looks only at where the (smoothed) maximum lies, so the
find_* plans can walk uphill until the peak is inside a scan.  No EPICS, no
apsbits: ``tests/test_peak_search.py`` runs it on recorded data.
"""

import numpy as np

INSIDE = "inside"
LOW_EDGE = "low_edge"
HIGH_EDGE = "high_edge"
FLAT = "flat"


def _smooth(y, window):
    """Running mean that does not sag at the ends (no zero padding)."""
    kernel = np.ones(window)
    return np.convolve(y, kernel, mode="same") / np.convolve(
        np.ones_like(y), kernel, mode="same"
    )


def locate_peak(
    x,
    y,
    edge_fraction=0.1,
    min_snr=6.0,
    min_prominence=0.2,
    window=5,
):
    """Classify one scan as peak inside, peak beyond an edge, or no signal.

    Parameters
    ----------
    x, y : sequence of float
        Positioner readback and detector signal, in scan order.
    edge_fraction : float
        A maximum within this fraction of the points from either end counts
        as being at that edge.
    min_snr : float
        The smoothed swing (max - min) must exceed this many times the
        point-to-point noise, else the scan is "no signal" (``FLAT``) and
        there is no direction to walk in.  A ratio test (max / min) is not
        used: it depends on the dark offset and misjudges noisy scan ends.
    min_prominence : float
        An interior maximum must stand above the higher end of the scan by
        this fraction of the scan's full swing, otherwise the scan is still
        on a slope (with noise) and the higher end is the way to go.
    window : int
        Points in the running mean applied before any of the above, so a
        single noisy reading does not decide the direction.

    Returns
    -------
    (str, float)
        One of ``INSIDE``, ``LOW_EDGE``, ``HIGH_EDGE``, ``FLAT``, and the x
        of the smoothed maximum.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    n = len(y)
    if n < 3:
        return FLAT, float(x[0]) if n else float("nan")
    ys = _smooth(y, max(1, min(window, n)))
    imax = int(np.argmax(ys))
    x_at_max = float(x[imax])
    y_max, y_min = ys[imax], ys.min()

    # Robust noise: for Gaussian noise of sigma, median |dy| is 0.954 sigma.
    # Point-to-point differences barely see a slope or a peak, so this is
    # the noise even on a scan full of signal.
    noise = np.median(np.abs(np.diff(y))) / 0.954
    if y_max - y_min <= min_snr * noise:
        return FLAT, x_at_max

    edge = max(1, int(round(edge_fraction * n)))
    low_is_higher_end = ys[0] >= ys[-1]
    if imax < edge:
        return LOW_EDGE, x_at_max
    if imax >= n - edge:
        return HIGH_EDGE, x_at_max
    if y_max - max(ys[0], ys[-1]) < min_prominence * (y_max - y_min):
        return (LOW_EDGE if low_is_higher_end else HIGH_EDGE), x_at_max
    return INSIDE, x_at_max
