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
from bluesky.utils import plan

from ..utils.constants import constants
from .amplifiers_plan import autoscale_amplifiers
from .filter_plans import insertScanFilters
from .filter_plans import insertTransmissionFilters
from .mode_changes import mode_SAXS
from .mode_changes import mode_USAXS
from .no_run import no_run_trigger_and_wait

logger = logging.getLogger(__name__)


# Device instances
I0_controls = oregistry["I0_controls"]
trd_controls = oregistry["trd_controls"]

a_stage = oregistry["a_stage"]
saxs_stage = oregistry["saxs_stage"]
scaler0 = oregistry["scaler0"]
terms = oregistry["terms"]
usaxs_shutter = oregistry["usaxs_shutter"]
user_data = oregistry["user_data"]


@plan
def measure_USAXS_Transmission():
    """
    Measure the sample transmission in USAXS mode and update EPICS PVs.

    This plan does not (should not) generate a bluesky run.

    This function measures the sample transmission by:
    1. Setting up the instrument in USAXS mode
    2. Moving the analyzer stage to the correct position
    3. Inserting transmission filters
    4. Collecting data from the transmission diode and I0 detector
    5. Storing the results in the appropriate EPICS PVs

    Yields
    ------
    Generator[Any, None, None]
        A generator that yields plan steps
    """
    try:
        yield from bps.checkpoint() # add checkpoint for suspenders
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

            yield from bps.mv(scaler0.preset_time, trmssn.count_time.get())
            scaler0.select_channels(["I0", "TRD"])
            yield from no_run_trigger_and_wait([scaler0])
            scaler0.select_channels()
            s = scaler0.read()
            secs = s["scaler0_time"]["value"]
            _tr_diode = s["TRD"]["value"]
            _I0 = s["I0"]["value"]

            if (
                _tr_diode > secs * constants["TR_MAX_ALLOWED_COUNTS"]
                or _I0 > secs * constants["TR_MAX_ALLOWED_COUNTS"]
            ):
                yield from autoscale_amplifiers([I0_controls, trd_controls])

                yield from bps.mv(scaler0.preset_time, trmssn.count_time.get())
                scaler0.select_channels(["I0", "TRD"])
                yield from no_run_trigger_and_wait([scaler0])
                scaler0.select_channels(None)
                s = scaler0.read()

            yield from bps.mv(
                # fmt: off
                a_stage.x,
                terms.USAXS.AX0.get(),
                usaxs_shutter,
                "close",
                # fmt: on
            )
            yield from insertScanFilters()
            yield from bps.mv(
                # fmt: off
                trmssn.diode_counts,
                s["TRD"]["value"],
                trmssn.diode_gain,
                trd_controls.femto.gain.get(),
                trmssn.I0_counts,
                s["I0"]["value"],
                trmssn.I0_gain,
                I0_controls.femto.gain.get(),
                # fmt: on
            )
            # tbl = pyRestTable.Table()
            # tbl.addLabel("detector")
            # tbl.addLabel("counts")
            # tbl.addLabel("gain")
            # tbl.addRow(
            #     (
            #         "pinDiode",
            #         f"{trmssn.diode_counts.get():f}",
            #         f"{trmssn.diode_gain.get()}",
            #     )
            # )
            # tbl.addRow(("I0", f"{trmssn.I0_counts.get():f}",
            # f"{trmssn.I0_gain.get()}"))
            # msg = "Measured USAXS transmission values:\n"
            # msg += str(tbl.reST())
            logger.info(
                "Measured USAXS transmission values :"
                f" Diode = {terms.USAXS.transmission.diode_counts.get():.0f}"
                f" with gain {terms.USAXS.transmission.diode_gain.get():g}"
                f" and I0 = {terms.USAXS.transmission.I0_counts.get():.0f}"
                f" with gain {terms.USAXS.transmission.I0_gain.get():g}"
            )
            # logger.info(msg)

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
    """
    Measure the sample transmission in SAXS mode and update EPICS PVs.

    This function measures the sample transmission by:
    1. Setting up the instrument in SAXS mode
    2. Moving the SAXS stage to the correct position
    3. Inserting transmission filters
    4. Collecting data from the transmission diode and I0 detector
    5. Storing the results in the appropriate EPICS PVs

    Yields
    ------
    Generator[Any, None, None]
        A generator that yields plan steps
    """
    try:
        yield from bps.checkpoint()         #add checkpoint for suspenders
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

        # yield from autoscale_amplifiers([I0_controls, trd_controls])
        yield from bps.mv(
            # fmt: off
            scaler0.preset_time,
            constants["SAXS_TR_TIME"],
            # fmt: on
        )
        scaler0.select_channels(["I0", "TRD"])
        yield from no_run_trigger_and_wait([scaler0])
        scaler0.select_channels(None)
        s = scaler0.read()
        secs = s["scaler0_time"]["value"]
        _tr_diode = s["TRD"]["value"]
        _I0 = s["I0"]["value"]

        if (
            _tr_diode > secs * constants["TR_MAX_ALLOWED_COUNTS"]
            or _I0 > secs * constants["TR_MAX_ALLOWED_COUNTS"]
        ):
            yield from autoscale_amplifiers([I0_controls, trd_controls])

            yield from bps.mv(
                # fmt: off
                scaler0.preset_time,
                constants["SAXS_TR_TIME"],
                # fmt: on
            )
            yield from no_run_trigger_and_wait([scaler0])
            s = scaler0.read()

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
        yield from bps.mv(
            # fmt: off
            terms.SAXS_WAXS.diode_transmission,
            s["TRD"]["value"],
            terms.SAXS_WAXS.diode_gain,
            trd_controls.femto.gain.get(),
            terms.SAXS_WAXS.I0_transmission,
            s["I0"]["value"],
            terms.SAXS_WAXS.I0_gain,
            I0_controls.femto.gain.get(),
            # fmt: on
        )
        logger.info(
            (
                "Measured SAXS transmission values :"
                f" Diode = {terms.USAXS.transmission.diode_counts.get():.0f}"
                f" with gain {terms.USAXS.transmission.diode_gain.get():g}"
                f" and I0 = {terms.USAXS.transmission.I0_counts.get():.0f}"
                f" with gain {terms.USAXS.transmission.I0_gain.get():g}"
            )
        )

    except Exception as e:
        logger.error(f"Error in measure_SAXS_Transmission: {str(e)}")
        raise
