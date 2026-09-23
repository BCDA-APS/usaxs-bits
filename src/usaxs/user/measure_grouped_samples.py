"""Collect four samples in grouped detector order.

The collection order is:

    all USAXS → all SAXS → all WAXS

Samples are measured in the order listed in ``SampleList``.  Edit that list
before loading this module.
"""

import logging

from bluesky import plan_stubs as bps
from ophyd import Signal

from usaxs.plans.command_list import after_command_list
from usaxs.plans.command_list import before_command_list
from usaxs.plans.plans_usaxs import USAXSscan
from usaxs.plans.plans_user_facing import saxsExp
from usaxs.plans.plans_user_facing import waxsExp
from usaxs.utils.obsidian import appendToMdFile
from usaxs.utils.obsidian import recordFunctionRun

logger = logging.getLogger(__name__)

# Set this before running the plan:
#   grouped_debug.put(True)   # dry run, no instrument operations
#   grouped_debug.put(False)  # real data collection
grouped_debug = Signal(name="grouped_debug", value=False)

# Format: [sample stage X (mm), sample stage Y (mm), thickness (mm), name]
SampleList = [
    [20.0, 40.0, 1.0, "AirBlank"],
    [60.0, 181.0, 3.5, "Randy3"],
    [100.0, 181.0, 3.5, "Randy1"],
    [100.0, 142.0, 3.5, "Randy2"],
]


def measure_grouped_samples(md=None):
    """Collect one USAXS/SAXS/WAXS set for every sample.

    Detector order is explicitly grouped:

    1. USAXS at all samples
    2. SAXS at all samples
    3. WAXS at all samples

    Parameters
    ----------
    md : dict, optional
        Additional metadata applied to each scan.  The scan title is updated
        for each detector and is also passed as the positional scan title.
    """
    if md is None:
        md = {}

    is_debug = grouped_debug.get()
    recordFunctionRun()

    if not is_debug:
        yield from before_command_list()

    sample_names = ", ".join(sample[3] for sample in SampleList)
    appendToMdFile(
        "Starting grouped sample collection: "
        f"{len(SampleList)} samples ({sample_names}); "
        "all USAXS, then all SAXS, then all WAXS"
    )

    def scan_metadata(sample_name):
        scan_md = dict(md)
        scan_md["title"] = sample_name
        return scan_md

    if is_debug:
        for detector in ("USAXS", "SAXS", "WAXS"):
            for pos_x, pos_y, thickness, sample_name in SampleList:
                print(
                    f"[DEBUG] {detector}: {sample_name} "
                    f"pos=({pos_x}, {pos_y}) mm, thickness={thickness} mm"
                )
                yield from bps.sleep(1)
    else:
        # All USAXS scans.
        for pos_x, pos_y, thickness, sample_name in SampleList:
            logger.info("USAXSscan: %s", sample_name)
            yield from USAXSscan(
                pos_x,
                pos_y,
                thickness,
                sample_name,
                md=scan_metadata(sample_name),
            )

        # All SAXS scans.
        for pos_x, pos_y, thickness, sample_name in SampleList:
            logger.info("saxsExp: %s", sample_name)
            yield from saxsExp(
                pos_x,
                pos_y,
                thickness,
                sample_name,
                md=scan_metadata(sample_name),
            )

        # All WAXS scans.
        for pos_x, pos_y, thickness, sample_name in SampleList:
            logger.info("waxsExp: %s", sample_name)
            yield from waxsExp(
                pos_x,
                pos_y,
                thickness,
                sample_name,
                md=scan_metadata(sample_name),
            )

    appendToMdFile(
        "Grouped sample collection complete: "
        f"{len(SampleList)} samples, all USAXS/SAXS/WAXS collected"
    )

    if not is_debug:
        yield from after_command_list()
