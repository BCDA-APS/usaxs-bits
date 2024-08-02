
"""
measure the sample transmission
"""

__all__ = """
    measure_SAXS_Transmission
    measure_USAXS_Transmission
""".split()

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

from bluesky import plans as bp
from bluesky import plan_stubs as bps
import numpy as np
import pyRestTable

from ..devices import a_stage, saxs_stage
from ..devices import autoscale_amplifiers, I0_controls, trd_controls
from ..devices import constants
from ..devices import scaler0
from ..devices import terms
from ..devices import ti_filter_shutter
from ..devices import user_data
from .filters import insertScanFilters, insertTransmissionFilters
from .mode_changes import mode_SAXS, mode_USAXS
from .no_run import no_run_trigger_and_wait


def measure_USAXS_Transmission(md={}):
    """
    measure the sample transmission in USAXS mode
    """
    trmssn = terms.USAXS.transmission   # for convenience
    yield from user_data.set_state_plan("Measure USAXS transmission")
    if trmssn.measure.get():
        yield from mode_USAXS()
        ax_target = terms.SAXS.ax_in.get() + constants["USAXS_AY_OFFSET"] + 12*np.sin(terms.USAXS.ar_val_center.get() * np.pi/180)
        yield from bps.mv(
            trmssn.ax, ax_target,
            a_stage.x, ax_target,
            ti_filter_shutter, "open",
        )
        yield from insertTransmissionFilters()

        yield from autoscale_amplifiers([I0_controls, trd_controls])

        yield from bps.mv(
            scaler0.preset_time, trmssn.count_time.get()
        )
        md["plan_name"] = "measure_USAXS_Transmission"
        scaler0.select_channels(["I0_USAXS", "TR diode"])
        yield from no_run_trigger_and_wait([scaler0])
        scaler0.select_channels(None)
        s = scaler0.read()
        secs = s["scaler0_time"]["value"]
        _tr_diode = s["TR diode"]["value"]
        _I0 = s["I0_USAXS"]["value"]

        if _tr_diode > secs*constants["TR_MAX_ALLOWED_COUNTS"]  or _I0 > secs*constants["TR_MAX_ALLOWED_COUNTS"] :
            yield from autoscale_amplifiers([I0_controls, trd_controls])

            yield from bps.mv(
                scaler0.preset_time, trmssn.count_time.get()
            )
            scaler0.select_channels(["I0_USAXS", "TR diode"])
            yield from no_run_trigger_and_wait([scaler0])
            scaler0.select_channels(None)
            s = scaler0.read()

        yield from bps.mv(
            a_stage.x, terms.USAXS.AX0.get(),
            ti_filter_shutter, "close",
        )
        yield from insertScanFilters()
        yield from bps.mv(
            trmssn.diode_counts, s["TR diode"]["value"],
            trmssn.diode_gain, trd_controls.femto.gain.get(),
            trmssn.I0_counts, s["I0_USAXS"]["value"],
            trmssn.I0_gain, I0_controls.femto.gain.get(),
        )
        tbl = pyRestTable.Table()
        tbl.addLabel("detector")
        tbl.addLabel("counts")
        tbl.addLabel("gain")
        tbl.addRow(("pinDiode", f"{trmssn.diode_counts.get():f}", f"{trmssn.diode_gain.get()}"))
        tbl.addRow(("I0", f"{trmssn.I0_counts.get():f}", f"{trmssn.I0_gain.get()}"))
        msg = "Measured USAXS transmission values:\n"
        msg += str(tbl.reST())
        logger.info(msg)

    else:
        yield from bps.mv(
            trmssn.diode_counts, 0,
            trmssn.diode_gain, 0,
            trmssn.I0_counts, 0,
            trmssn.I0_gain, 0,
        )
        logger.info("Did not measure USAXS transmission.")


def measure_SAXS_Transmission(md={}):
    """
    measure the sample transmission in SAXS mode
    """
    # FIXME: this failed when USAXS was already in position
    yield from user_data.set_state_plan("Measure SAXS transmission")
    yield from mode_SAXS()
    yield from insertTransmissionFilters()
    pinz_target = terms.SAXS.z_in.get() + constants["SAXS_PINZ_OFFSET"]
    pinx_target = terms.SAXS.x_in.get() + constants["SAXS_TR_PINY_OFFSET"]
    # z has to move before x can move.
    yield from bps.mv(saxs_stage.z, pinz_target)
    #now x can put diode in the beam, open shutter...
    yield from bps.mv(
        saxs_stage.x, pinx_target,
        ti_filter_shutter, "open",
    )

    yield from autoscale_amplifiers([I0_controls, trd_controls])
    yield from bps.mv(
        scaler0.preset_time, constants["SAXS_TR_TIME"],
    )
    md["plan_name"] = "measure_SAXS_Transmission"
    yield from no_run_trigger_and_wait([scaler0])
    s = scaler0.read()
    secs = s["scaler0_time"]["value"]
    _tr_diode = s["TR diode"]["value"]
    _I0 = s["I0_USAXS"]["value"]

    if _tr_diode > secs*constants["TR_MAX_ALLOWED_COUNTS"] or _I0 > secs*constants["TR_MAX_ALLOWED_COUNTS"] :
        yield from autoscale_amplifiers([I0_controls, trd_controls])

        yield from bps.mv(
            scaler0.preset_time, constants["SAXS_TR_TIME"],
        )
        yield from no_run_trigger_and_wait([scaler0])
        s = scaler0.read()

    # x has to move before z, close shutter...
    yield from bps.mv(
        saxs_stage.x, terms.SAXS.x_in.get(),
        ti_filter_shutter, "close",
    )
    # z can move.
    yield from bps.mv(saxs_stage.z, terms.SAXS.z_in.get())

    yield from insertScanFilters()
    yield from bps.mv(
        terms.SAXS_WAXS.diode_transmission, s["TR diode"]["value"],
        terms.SAXS_WAXS.diode_gain, trd_controls.femto.gain.get(),
        terms.SAXS_WAXS.I0_transmission, s["I0_USAXS"]["value"],
        terms.SAXS_WAXS.I0_gain, I0_controls.femto.gain.get(),
    )
    logger.info((
        "Measured SAXS transmission values"
        f", pinDiode cts ={terms.USAXS.transmission.diode_counts.get():f}"
        f" with gain {terms.USAXS.transmission.diode_gain.get()}"
        f" and I0 cts {terms.USAXS.transmission.I0_counts.get()}"
        f" with gain {terms.USAXS.transmission.I0_gain.get()}"
    ))

