"""
conversion functions
"""

__all__ = [
    "angle2q",
    "q2angle",
]

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

import numpy as np


def angle2q(angle, wavelength):
    "angle is in 2theta"
    return (4 * np.pi / wavelength) * np.sin(angle * np.pi / 2 / 180)


def q2angle(q, wavelength):
    "angle is in 2theta"
    return np.arcsin(wavelength * q / 4 / np.pi) * 180 * 2 / np.pi
