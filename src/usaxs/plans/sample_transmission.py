"""
Measure sample transmission in USAXS and SAXS modes.

This module provides functions for measuring sample transmission in both USAXS
and SAXS modes. It includes functions for setting up the correct instrument
configuration, inserting appropriate filters, and collecting transmission data
using various detectors.
"""

import logging

import numpy as np
from apsbits.core.instrument_init import oregistry
from bluesky import plan_stubs as bps
from bluesky import preprocessors as bpp
from bluesky.utils import plan

from ..utils.constants import constants
from .filter_plans import insertScanFilters
from .filter_plans import insertTransmissionFilters
from .fx4_autorange_plan import autoscale_amplifiers
from .fx4_setup import any_near_full_scale
from .fx4_setup import prepare_fx4_counting
from .fx4_setup import select_fx4_channel
from .fx4_setup import usaxs_electrometers
from .mode_changes import mode_SAXS
from .mode_changes import mode_USAXS
from .no_run import no_run_trigger_and_wait

logger = logging.getLogger(__name__)


# Device instances
I0_controls = oregistry["I0_controls"]
trd_controls = oregistry["trd_controls"]
upd_controls = oregistry["upd_controls"]

a_stage = oregistry["a_stage"]
saxs_stage = oregistry["saxs_stage"]
terms = oregistry["terms"]
usaxs_shutter = oregistry["usaxs_shutter"]
user_data = oregistry["user_data"]

# fx4 carries TRD (and UPD), fx42 carries I0.  Both are triggered for every
# transmission measurement.
FX4_DETECTORS = usaxs_electrometers()


@plan
def _restore_upd_channel():
    """Plan: hand usxFX4's shared Range back to UPD.

    Every transmission measurement points ``seq01:channel`` at TRD, and one
    Range serves all four channels of an electrometer.  Both callers of these
    plans -- ``USAXSscanStep`` and ``Flyscan`` -- start scanning immediately
    afterwards, so leaving the channel on TRD would range the whole scan for
    the transmitted beam.  Because the reading is gain-independent the result
    would still look like a plausible current, which is exactly why this runs
    from a finaliser rather than on the success path.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    yield from select_fx4_channel(upd_controls)


@plan
def _count_transmission(count_time):
    """Plan: take one reading on both electrometers.

    Parameters
    ----------
    count_time : float
        Integration time, seconds.  Quantised to whole mains cycles.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.

    Returns
    -------
    tuple of float
        ``(diode pA, I0 pA)``.
    """
    yield from prepare_fx4_counting(count_time)
    # Both boxes fire before either is waited on, so their integration windows
    # differ by a channel-access round trip rather than a whole exposure.
    yield from no_run_trigger_and_wait(FX4_DETECTORS)
    return trd_controls.signal.get(), I0_controls.signal.get()


@plan
def measure_USAXS_Transmission():
    """Bluesky plan: measure sample transmission in USAXS mode.

    Wraps the measurement so that usxFX4's shared Range is always handed back
    to UPD, including on an exception or an abort -- see
    :func:`_restore_upd_channel`.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    yield from bpp.finalize_wrapper(
        _measure_USAXS_Transmission(), _restore_upd_channel()
    )


@plan
def _measure_USAXS_Transmission():
    """Bluesky plan: measure sample transmission in USAXS mode.

    Does not create a Bluesky run.  Moves the analyzer stage to the
    transmission position, opens the shutter, inserts transmission filters,
    autoscales amplifiers, counts on the TRD and I0 channels, then stores
    the results in ``terms.USAXS.transmission.*`` EPICS PVs.  If
    ``terms.USAXS.transmission.measure`` is not set, clears the PVs to zero.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    try:
        yield from bps.checkpoint()  # add checkpoint for suspenders
        trmssn = terms.USAXS.transmission  # for convenience
        yield from user_data.set_state_plan("Measure USAXS transmission")
        if trmssn.measure.get():
            yield from mode_USAXS()
            ax_target = (
                terms.SAXS.ax_in.get()
                + constants["USAXS_AY_OFFSET"]
                + 12 * np.sin(terms.USAXS.ar_val_center.get() * np.pi / 180)
            )
            yield from bps.mv(
                # fmt: off
                trmssn.ax,
                ax_target,
                a_stage.x,
                ax_target,
                usaxs_shutter,
                "open",
                # fmt: on
            )
            yield from insertTransmissionFilters()

            yield from autoscale_amplifiers([I0_controls, trd_controls])

            _tr_diode, _I0 = yield from _count_transmission(
                trmssn.count_time.get()
            )

            # Topped out means the range is wrong, so re-range and re-measure.
            # Judged as a fraction of the active range rather than an absolute
            # number: the FX4's useful maximum moves with the range.
            if any_near_full_scale(
                [trd_controls, I0_controls], constants["TR_MAX_FRACTION_OF_RANGE"]
            ):
                yield from autoscale_amplifiers([I0_controls, trd_controls])
                _tr_diode, _I0 = yield from _count_transmission(
                    trmssn.count_time.get()
                )

            yield from bps.mv(
                # fmt: off
                a_stage.x,
                terms.USAXS.AX0.get(),
                usaxs_shutter,
                "close",
                # fmt: on
            )
            yield from insertScanFilters()
            # The FX4 reading is gain-independent picoamps, so transmission is
            # just diode / I0.  The *_gain PVs are kept at 1.0 rather than
            # retired: anything downstream that still divides by them then gets
            # the right answer.  Writing the FX4 range index here instead would
            # be silently wrong by orders of magnitude.
            yield from bps.mv(
                # fmt: off
                trmssn.diode_counts,
                _tr_diode,
                trmssn.diode_gain,
                1.0,
                trmssn.I0_counts,
                _I0,
                trmssn.I0_gain,
                1.0,
                # fmt: on
            )
            logger.info(
                "Measured USAXS transmission:"
                f" diode = {_tr_diode:.4g} pA,"
                f" I0 = {_I0:.4g} pA,"
                f" ratio = {_tr_diode / _I0 if _I0 else float('nan'):.4g}"
            )

        else:
            yield from bps.mv(
                # fmt:off
                trmssn.diode_counts,
                0,
                trmssn.diode_gain,
                0,
                trmssn.I0_counts,
                0,
                trmssn.I0_gain,
                0,
                # fmt:on
            )
            logger.info("Did not measure USAXS transmission.")

    except Exception as e:
        logger.error(f"Error in measure_USAXS_Transmission: {str(e)}")
        raise


@plan
def measure_SAXS_Transmission():
    """Bluesky plan: measure sample transmission in SAXS mode.

    Wraps the measurement so that usxFX4's shared Range is always handed back
    to UPD, including on an exception or an abort -- see
    :func:`_restore_upd_channel`.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    yield from bpp.finalize_wrapper(
        _measure_SAXS_Transmission(), _restore_upd_channel()
    )


@plan
def _measure_SAXS_Transmission():
    """Bluesky plan: measure sample transmission in SAXS mode.

    Does not create a Bluesky run.  Moves the SAXS pinhole stage to the
    transmission position, opens the shutter, inserts transmission filters,
    counts on the TRD and I0 channels (autoscaling if saturated), then
    stores the results in ``terms.SAXS_WAXS.*`` EPICS PVs.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    try:
        yield from bps.checkpoint()  # add checkpoint for suspenders
        yield from user_data.set_state_plan("Measure SAXS transmission")
        yield from mode_SAXS()
        yield from insertTransmissionFilters()
        pinz_target = terms.SAXS.z_in.get() + constants["SAXS_PINZ_OFFSET"]
        pinx_target = terms.SAXS.x_in.get() + constants["SAXS_TR_PINY_OFFSET"]
        # z has to move before x can move.
        yield from bps.mv(saxs_stage.z, pinz_target)
        # now x can put diode in the beam, open shutter...
        yield from bps.mv(
            # fmt: off
            saxs_stage.x,
            pinx_target,
            usaxs_shutter,
            "open",
            # fmt: on
        )

        _tr_diode, _I0 = yield from _count_transmission(constants["SAXS_TR_TIME"])

        if any_near_full_scale(
            [trd_controls, I0_controls], constants["TR_MAX_FRACTION_OF_RANGE"]
        ):
            yield from autoscale_amplifiers([I0_controls, trd_controls])
            _tr_diode, _I0 = yield from _count_transmission(
                constants["SAXS_TR_TIME"]
            )

        # x has to move before z, close shutter...
        yield from bps.mv(
            # fmt: off
            saxs_stage.x,
            terms.SAXS.x_in.get(),
            usaxs_shutter,
            "close",
            # fmt: on
        )
        # z can move.
        yield from bps.mv(saxs_stage.z, terms.SAXS.z_in.get())

        yield from insertScanFilters()
        # gain = 1.0: the FX4 reading is already gain-independent pA.  See the
        # matching note in measure_USAXS_Transmission.
        yield from bps.mv(
            # fmt: off
            terms.SAXS_WAXS.diode_transmission,
            _tr_diode,
            terms.SAXS_WAXS.diode_gain,
            1.0,
            terms.SAXS_WAXS.I0_transmission,
            _I0,
            terms.SAXS_WAXS.I0_gain,
            1.0,
            # fmt: on
        )
        logger.info(
            "Measured SAXS transmission:"
            f" diode = {_tr_diode:.4g} pA,"
            f" I0 = {_I0:.4g} pA,"
            f" ratio = {_tr_diode / _I0 if _I0 else float('nan'):.4g}"
        )

    except Exception as e:
        logger.error(f"Error in measure_SAXS_Transmission: {str(e)}")
        raise
