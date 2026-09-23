"""Infinite grouped-detector X-ray damage test for a sample container.

Each cycle collects one alternating blank, followed by the requested number of
exposures at each sample position.  Detector order is grouped:

    all USAXS -> all SAXS -> all WAXS

The sample exposure number is cumulative and appears in every filename.  The
same exposure number is used for the USAXS, SAXS, and WAXS measurements that
belong to one sample exposure.

Stop the plan with the ``usxLAX:StopBeforeNextScan`` checkbox -- that path runs
``after_command_list()`` for you before aborting.  With ``RE.abort()`` or
Ctrl-C, Bluesky does not run the post-command list, so run
``RE(after_command_list())`` afterward if instrument cleanup is needed.
"""

import logging

from bluesky import plan_stubs as bps
from ophyd import Signal

from usaxs.plans.command_list import after_command_list
from usaxs.plans.command_list import before_command_list
from usaxs.plans.plans_user_facing import saxsExp
from usaxs.plans.plans_user_facing import waxsExp
from usaxs.plans.plans_usaxs import USAXSscan
from usaxs.utils.obsidian import appendToMdFile, recordFunctionRun

logger = logging.getLogger(__name__)
logger.info(__file__)

# Set True for a dry run.  Debug mode prints the planned scans and does not
# move the instrument or collect data.
containment_debug = Signal(name="containment_debug", value=False)

# [sx, sy, thickness_mm, name]
BLANKS = [
    [0.0, 0.0, 4.0, "Blank1"],
    [0.0, 1.0, 4.0, "Blank2"],
]

# [sx, sy, thickness_mm, name, exposures_per_cycle]
SAMPLES = [
    [0.0, 4.0, 4.0, "Sample1", 1],
    [0.0, 6.0, 4.0, "Sample2", 2],
    [0.0, 8.0, 4.0, "Sample3", 4],
    [0.0, 10.0, 4.0, "Sample4", 8],
    [0.0, 12.0, 4.0, "Sample5", 8],
]


def ContainmentTest(md=None):
    """Run the container damage test indefinitely.

    One blank is measured per cycle, alternating Blank1 and Blank2.  Since one
    cycle contains 23 sample USAXS exposures plus one blank, and a USAXS scan
    takes about two minutes, each blank measurement occurs approximately every
    48 minutes (actual timing depends on SAXS/WAXS and stage overhead).

    Each cycle contains:

    * Blank1, Blank2, ... alternating, once per detector group
    * Sample1: 1 exposure
    * Sample2: 2 exposures
    * Sample3: 4 exposures
    * Sample4: 8 exposures
    * Sample5: 8 exposures

    The file-name format is ``<name>_exp####_<detector>``.  Exposure numbers
    are cumulative for each position over the complete run.
    """
    if md is None:
        md = {}

    def scan_name(name, exposure, detector):
        return f"{name}_exp{exposure:04d}_{detector}"

    def collect(detector, work, debug=False):
        """Collect one grouped detector pass from a list of scan jobs."""
        for sx, sy, thickness, name, exposure in work:
            title = scan_name(name, exposure, detector)
            if debug:
                print(
                    f"[DEBUG] {detector}: {title} "
                    f"pos=({sx}, {sy}), thickness={thickness} mm"
                )
                yield from bps.sleep(0.2)
            elif detector == "USAXS":
                md["title"] = title
                yield from USAXSscan(sx, sy, thickness, title, md={})
            elif detector == "SAXS":
                md["title"] = title
                yield from saxsExp(sx, sy, thickness, title, md={})
            elif detector == "WAXS":
                md["title"] = title
                yield from waxsExp(sx, sy, thickness, title, md={})
            else:
                raise ValueError(f"Unknown detector: {detector}")

    is_debug = containment_debug.get()
    recordFunctionRun()

    if not is_debug:
        yield from before_command_list()

    appendToMdFile(
        "Starting ContainmentTest: alternating blanks every cycle; "
        "grouped all-USAXS, all-SAXS, all-WAXS; infinite loop"
    )

    # Cumulative exposure counters.  A counter increments once per sample
    # exposure set, not once per detector, so USAXS/SAXS/WAXS share a number.
    exposure_count = {entry[3]: 0 for entry in BLANKS + SAMPLES}
    cycle = 0

    while True:
        blank = BLANKS[cycle % len(BLANKS)]
        exposure_count[blank[3]] += 1
        blank_job = (*blank, exposure_count[blank[3]])

        sample_jobs = []
        for sx, sy, thickness, name, exposures in SAMPLES:
            for _ in range(exposures):
                exposure_count[name] += 1
                sample_jobs.append(
                    (sx, sy, thickness, name, exposure_count[name])
                )

        # Blank first, then all requested sample exposures.  The resulting
        # order is preserved in each of the three detector passes.
        work = [blank_job, *sample_jobs]
        logger.info(
            "ContainmentTest cycle %d: %s plus %d sample exposures",
            cycle,
            blank[3],
            len(sample_jobs),
        )

        yield from collect("USAXS", work, is_debug)
        yield from collect("SAXS", work, is_debug)
        yield from collect("WAXS", work, is_debug)
        cycle += 1
