"""Stage tuning plans for the USAXS instrument.

This module provides plans for tuning various stages of the USAXS instrument,
including alignment and optimization procedures.
"""

from typing import Any
from typing import Dict
from typing import Generator
from typing import Optional

from ..startup import oregistry
from bluesky.plans import lineup2

# Device instances
scaler0 = oregistry["scaler0"]


def tune(
    self,
    md: Optional[Dict[str, Any]] = None,
    RE: Optional[Any] = None,
    bec: Optional[Any] = None,
    specwriter: Optional[Any] = None,
) -> Generator[Any, None, Any]:
    """Execute a tuning plan.

    This function performs a scan to tune a stage motor by optimizing
    a detector signal.

    Parameters
    ----------
    self : Any
        The stage motor to tune
    md : Optional[Dict[str, Any]], optional
        Metadata dictionary, by default None
    RE : Optional[Any], optional
        Bluesky RunEngine instance, by default None
    bec : Optional[Any], optional
        Bluesky Live Callbacks instance, by default None
    specwriter : Optional[Any], optional
        SPEC file writer instance, by default None

    Returns
    -------
    Generator[Any, None, Any]
        A sequence of plan messages

    USAGE:  ``RE(tune(stage_motor))``
    """
    if md is None:
        md = {}
    if RE is None:
        raise ValueError("RunEngine instance must be provided")
    if bec is None:
        raise ValueError("Bluesky Live Callbacks instance must be provided")
    if specwriter is None:
        raise ValueError("SPEC file writer instance must be provided")

    _md = {}
    _md.update(md or {})

    def _inner() -> Generator[Any, None, Any]:
        if self.pre_tune_hook is not None:
            yield from self.pre_tune_hook()

        # TODO: if self.signal_stats is None, create one and use it
        print(self.detectors)
        scaler0 = oregistry["scaler0"]
        yield from lineup2(
            # self.detectors,
            [scaler0],
            self,  # this motor is the mover
            -self.tune_range.get(),  # rel_start
            self.tune_range.get(),  # rel_end
            self.points,
            peak_factor=self.peak_factor,
            width_factor=self.width_factor,
            feature=self.feature,
            nscans=self.nscans,
            signal_stats=self.signal_stats,
            md=_md,
        )
        # TODO: Need to report from signal_stats
        # Motor: m1
        # ========== ==================
        # statistic  noisy
        # ========== ==================
        # n          11
        # centroid   0.8237310041584432
        # sigma      0.6472728236075987
        # x_at_max_y 0.90963
        # max_y      7549.789982466793
        # min_y      22.338609615249936
        # mean_y     872.4897763435542
        # stddev_y   2236.733696611285
        # ========== ==================

        if self.post_tune_hook is not None:
            yield from self.post_tune_hook()

    return (yield from _inner())
