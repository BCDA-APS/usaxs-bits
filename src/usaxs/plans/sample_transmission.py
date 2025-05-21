"""
Measure sample transmission in USAXS and SAXS modes.

This module provides functions for measuring sample transmission in both USAXS
and SAXS modes. It includes functions for setting up the correct instrument
configuration, inserting appropriate filters, and collecting transmission data
using various detectors.
"""

import logging
from typing import Any
from typing import Dict
from typing import Optional

import numpy as np
import pyRestTable
from apsbits.core.instrument_init import oregistry
from bluesky import plan_stubs as bps
from bluesky import preprocessors as bpp

from .filter_plans import insertScanFilters
from .filter_plans import insertTransmissionFilters
from .mode_changes import mode_SAXS
from .mode_changes import mode_USAXS
from .no_run import no_run_trigger_and_wait

logger = logging.getLogger(__name__)


# Device instances
I0_controls = oregistry["I0_controls"]
a_stage = oregistry["a_stage"]
autoscale_amplifiers = oregistry["autoscale_amplifiers"]
constants = oregistry["constants"]
saxs_stage = oregistry["saxs_stage"]
scaler0 = oregistry["scaler0"]
terms = oregistry["terms"]
usaxs_shutter = oregistry["usaxs_shutter"]
trd_controls = oregistry["trd_controls"]
user_data = oregistry["user_data"]


def measure_USAXS_Transmission(
    md: Optional[Dict[str, Any]] = None,
):
    """
    Measure the sample transmission in USAXS mode.

    This function measures the sample transmission by:
    1. Setting up the instrument in USAXS mode
    2. Moving the analyzer stage to the correct position
    3. Inserting transmission filters
    4. Collecting data from the transmission diode and I0 detector
    5. Storing the results in the appropriate EPICS PVs

    Parameters
    ----------
    md : Optional[Dict[str, Any]], optional
        Metadata dictionary to be added to the scan, by default None

    Yields
    ------
    Generator[Any, None, None]
        A generator that yields plan steps
    """
    if md is None:
        md = {}

    try:
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
                trmssn.ax,
                ax_target,
                a_stage.x,
                ax_target,
                usaxs_shutter,
                "open",
            )
            yield from insertTransmissionFilters()

            yield from autoscale_amplifiers([I0_controls, trd_controls])

            yield from bps.mv(scaler0.preset_time, trmssn.count_time.get())
            md["plan_name"] = "measure_USAXS_Transmission"
            scaler0.select_channels(["I0_USAXS", "TR diode"])
            yield from no_run_trigger_and_wait([scaler0])
            scaler0.select_channels(None)
            s = scaler0.read()
            secs = s["scaler0_time"]["value"]
            _tr_diode = s["TR diode"]["value"]
            _I0 = s["I0_USAXS"]["value"]

            if (
                _tr_diode > secs * constants["TR_MAX_ALLOWED_COUNTS"]
                or _I0 > secs * constants["TR_MAX_ALLOWED_COUNTS"]
            ):
                yield from autoscale_amplifiers([I0_controls, trd_controls])

                yield from bps.mv(scaler0.preset_time, trmssn.count_time.get())
                scaler0.select_channels(["I0_USAXS", "TR diode"])
                yield from no_run_trigger_and_wait([scaler0])
                scaler0.select_channels(None)
                s = scaler0.read()

            yield from bps.mv(
                a_stage.x,
                terms.USAXS.AX0.get(),
                usaxs_shutter,
                "close",
            )
            yield from insertScanFilters()
            yield from bps.mv(
                trmssn.diode_counts,
                s["TR diode"]["value"],
                trmssn.diode_gain,
                trd_controls.femto.gain.get(),
                trmssn.I0_counts,
                s["I0_USAXS"]["value"],
                trmssn.I0_gain,
                I0_controls.femto.gain.get(),
            )
            tbl = pyRestTable.Table()
            tbl.addLabel("detector")
            tbl.addLabel("counts")
            tbl.addLabel("gain")
            tbl.addRow(
                (
                    "pinDiode",
                    f"{trmssn.diode_counts.get():f}",
                    f"{trmssn.diode_gain.get()}",
                )
            )
            tbl.addRow(("I0", f"{trmssn.I0_counts.get():f}", f"{trmssn.I0_gain.get()}"))
            msg = "Measured USAXS transmission values:\n"
            msg += str(tbl.reST())
            logger.info(msg)

        else:
            yield from bps.mv(
                trmssn.diode_counts,
                0,
                trmssn.diode_gain,
                0,
                trmssn.I0_counts,
                0,
                trmssn.I0_gain,
                0,
            )
            logger.info("Did not measure USAXS transmission.")

    except Exception as e:
        logger.error(f"Error in measure_USAXS_Transmission: {str(e)}")
        raise


def measure_SAXS_Transmission(
    md: Optional[Dict[str, Any]] = None,
):
    """
    Measure the sample transmission in SAXS mode.

    This function measures the sample transmission by:
    1. Setting up the instrument in SAXS mode
    2. Moving the SAXS stage to the correct position
    3. Inserting transmission filters
    4. Collecting data from the transmission diode and I0 detector
    5. Storing the results in the appropriate EPICS PVs

    Parameters
    ----------
    md : Optional[Dict[str, Any]], optional
        Metadata dictionary to be added to the scan, by default None

    Yields
    ------
    Generator[Any, None, None]
        A generator that yields plan steps
    """
    if md is None:
        md = {}

    try:
        yield from user_data.set_state_plan("Measure SAXS transmission")
        yield from mode_SAXS()
        yield from insertTransmissionFilters()
        pinz_target = terms.SAXS.z_in.get() + constants["SAXS_PINZ_OFFSET"]
        pinx_target = terms.SAXS.x_in.get() + constants["SAXS_TR_PINY_OFFSET"]
        # z has to move before x can move.
        yield from bps.mv(saxs_stage.z, pinz_target)
        # now x can put diode in the beam, open shutter...
        yield from bps.mv(
            saxs_stage.x,
            pinx_target,
            usaxs_shutter,
            "open",
        )

        yield from autoscale_amplifiers([I0_controls, trd_controls])
        yield from bps.mv(
            scaler0.preset_time,
            constants["SAXS_TR_TIME"],
        )
        md["plan_name"] = "measure_SAXS_Transmission"
        scaler0.select_channels(["I0_USAXS", "TR diode"])
        yield from no_run_trigger_and_wait([scaler0])
        scaler0.select_channels(None)
        s = scaler0.read()
        secs = s["scaler0_time"]["value"]
        _tr_diode = s["TR diode"]["value"]
        _I0 = s["I0_USAXS"]["value"]

        if (
            _tr_diode > secs * constants["TR_MAX_ALLOWED_COUNTS"]
            or _I0 > secs * constants["TR_MAX_ALLOWED_COUNTS"]
        ):
            yield from autoscale_amplifiers([I0_controls, trd_controls])

            yield from bps.mv(
                scaler0.preset_time,
                constants["SAXS_TR_TIME"],
            )
            yield from no_run_trigger_and_wait([scaler0])
            s = scaler0.read()

        # x has to move before z, close shutter...
        yield from bps.mv(
            saxs_stage.x,
            terms.SAXS.x_in.get(),
            usaxs_shutter,
            "close",
        )
        # z can move.
        yield from bps.mv(saxs_stage.z, terms.SAXS.z_in.get())

        yield from insertScanFilters()
        yield from bps.mv(
            terms.SAXS_WAXS.diode_transmission,
            s["TR diode"]["value"],
            terms.SAXS_WAXS.diode_gain,
            trd_controls.femto.gain.get(),
            terms.SAXS_WAXS.I0_transmission,
            s["I0_USAXS"]["value"],
            terms.SAXS_WAXS.I0_gain,
            I0_controls.femto.gain.get(),
        )
        logger.info(
            (
                "Measured SAXS transmission values"
                f", pinDiode cts ={terms.USAXS.transmission.diode_counts.get():f}"
                f" with gain {terms.USAXS.transmission.diode_gain.get()}"
                f" and I0 cts {terms.USAXS.transmission.I0_counts.get()}"
                f" with gain {terms.USAXS.transmission.I0_gain.get()}"
            )
        )

    except Exception as e:
        logger.error(f"Error in measure_SAXS_Transmission: {str(e)}")
        raise


def measure_transmission(
    count_time: float = 1.0,
    md: Optional[Dict[str, Any]] = None,
    RE: Optional[Any] = None,
    bec: Optional[Any] = None,
    specwriter: Optional[Any] = None,
):
    """Measure sample transmission.

    This function measures the transmission of a sample by comparing
    the incident and transmitted beam intensities.

    Parameters
    ----------
    count_time : float, optional
        Count time in seconds, by default 1.0
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

    USAGE:  ``RE(measure_transmission(count_time=1.0))``
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

    @bpp.run_decorator(md=_md)
    def _inner():
        yield from user_data.set_state_plan("measuring transmission")
        yield from bps.mv(scaler0.preset_time, count_time)
        yield from bps.trigger(scaler0, group="transmission")
        yield from bps.wait(group="transmission")

    return (yield from _inner())
