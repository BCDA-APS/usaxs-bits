"""
Configure matplotlib in interactive mode for IPython console
"""

__all__ = [
    "plt",
]

import logging

logger = logging.getLogger(__name__)

logger.info(__file__)

import matplotlib
import matplotlib.pyplot as plt
import PyQt5
# print(f"{PyQt5.__file__=!r}")

plt.ion()

# print(f"{matplotlib.backends.backend=!r}")
matplotlib.use("qt5Agg")
if matplotlib.backends.backend not in ("qtagg", "qt5Agg"):
    # https://github.com/APS-USAXS/bluesky/issues/7
    raise RuntimeError(
        f"Wrong MatPlotLib backend: {matplotlib.backends.backend=!r}"
    )
