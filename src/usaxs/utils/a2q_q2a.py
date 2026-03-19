"""
Angle ↔ Q conversion functions for SAXS/USAXS data.

Q is the momentum transfer (Å⁻¹).  Angles are in degrees (2θ convention).
Wavelength must be supplied in the same units as Q (typically Å).
"""

import numpy as np


def angle2q(angle, wavelength):
    """Convert scattering angle to momentum transfer Q.

    Parameters
    ----------
    angle : float or array-like
        Scattering angle in degrees (2θ).
    wavelength : float
        X-ray wavelength in Å.

    Returns
    -------
    float or ndarray
        Momentum transfer Q in Å⁻¹.
    """
    return (4 * np.pi / wavelength) * np.sin(angle * np.pi / 2 / 180)


def q2angle(q, wavelength):
    """Convert momentum transfer Q to scattering angle.

    Parameters
    ----------
    q : float or array-like
        Momentum transfer Q in Å⁻¹.
    wavelength : float
        X-ray wavelength in Å.

    Returns
    -------
    float or ndarray
        Scattering angle in degrees (2θ).
    """
    return np.arcsin(wavelength * q / 4 / np.pi) * 180 * 2 / np.pi
