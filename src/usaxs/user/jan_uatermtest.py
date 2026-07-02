"""
UATerm parameter sweep — USAXS-only, single pass across 7 samples.

PURPOSE:
    Test the effect of the UATerm parameter (PV: usxLAX:USAXS:UATerm) on USAXS
    data quality.  For each UATerm value the plan collects all samples at each
    of the selected flyscan times, then moves on to the next UATerm value.
    No SAXS or WAXS is collected — USAXS only.  Runs once and finishes.

MEASUREMENT SEQUENCE (single pass):
------------------------------------
For each UATerm in UATERM_VALUES (0.2, 0.3, …, 1.2):
    Set PV usxLAX:USAXS:UATerm to the value.
    For each scan time in FLYSCAN_TIMES (60, 90, 120, 180 s):
        Set PV usxLAX:USAXS:FS_ScanTime to the value.
        For each sample in SampleList:
            Collect one USAXSscan.

Total scans = 11 UATerm values × 4 times × 7 samples = 308 USAXS scans.

NOTE: UATerm is left at its last value when the plan finishes.  Restore it
manually if needed.

FILE-NAMING CONVENTION:
    {sampleName}_{uaterm_label}_{scan_time_s}s
    where uaterm_label encodes UATerm × 10, zero-padded to 2 digits:
        UATerm 0.2  → "UA02"
        UATerm 0.9  → "UA09"
        UATerm 1.0  → "UA10"
        UATerm 1.2  → "UA12"

EDIT BEFORE EACH RUN:
    1. Update SampleList below with correct positions, names, and thicknesses.
    2. Reload:  %run -im usaxs.user.jan_uatermtest
    3. Debug:   loop_debug.put(True)  ; RE(janUAtermTest())
    4. Run:     loop_debug.put(False) ; RE(janUAtermTest())

LOADING:
    %run -im usaxs.user.jan_uatermtest

DEBUG / DRY-RUN MODE:
    loop_debug.put(True)   → enable debug mode (no instrument motion)
    loop_debug.put(False)  → restore normal operation (default)

CHANGE LOG:
    * JIL, 2026-06-28 : Initial plan (AI-generated)
"""

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

import time

from bluesky import plan_stubs as bps
from ophyd import EpicsSignal, Signal

from usaxs.plans.plans_usaxs import USAXSscan
from usaxs.plans.command_list import after_command_list, sync_order_numbers
from usaxs.plans.command_list import before_command_list
from usaxs.utils.obsidian import appendToMdFile, recordFunctionRun

# ---------------------------------------------------------------------------
# USAXS flyscan scan-time signal (PV: usxLAX:USAXS:FS_ScanTime).
# ---------------------------------------------------------------------------
flyscan_scan_time = EpicsSignal(
    "usxLAX:USAXS:FS_ScanTime", name="flyscan_scan_time"
)

# ---------------------------------------------------------------------------
# UATerm signal (PV: usxLAX:USAXS:UATerm).
# ---------------------------------------------------------------------------
uaterm = EpicsSignal(
    "usxLAX:USAXS:UATerm", name="uaterm"
)

# Convenient time-unit constants.
SECOND = 1
MINUTE = 60 * SECOND
HOUR   = 60 * MINUTE

# Debug / dry-run flag.
#   loop_debug.put(True)   → debug mode (no instrument motion, prints only)
#   loop_debug.put(False)  → normal operation (default)
loop_debug = Signal(name="loop_debug", value=False)

# ---------------------------------------------------------------------------
# UATerm values to sweep (0.2 → 1.2 in 0.1 steps, 11 values total).
# ---------------------------------------------------------------------------
UATERM_VALUES = [round(v * 0.1, 1) for v in range(2, 13)]   # [0.2, 0.3, …, 1.2]

# ---------------------------------------------------------------------------
# USAXS flyscan times to collect at each UATerm value (seconds).
# ---------------------------------------------------------------------------
FLYSCAN_TIMES = [60, 90, 120, 180]

# ---------------------------------------------------------------------------
# MODULE-LEVEL SampleList  ← EDIT BEFORE EACH RUN, then reload.
#
# Format: [sampleName, sx_mm, sy_mm, thickness_mm]
# ---------------------------------------------------------------------------
SampleList = [
    # sampleName          sx      sy      thickness
    ["AirBlank",        20.0,   40.0,   1.0],
    ["GC_SRM3600",      20.0,   60.0,   1.0],
    ["tapeBlank",       20.0,   80.0,   1.0],
    ["Carbon1",         20.0,  100.0,   1.0],
    ["Carbon2",         20.0,  120.0,   1.0],
    ["Carbon3",         20.0,  140.0,   1.0],
    ["Powder",          20.0,  160.0,   1.0],
]


# ---------------------------------------------------------------------------
# Filename label helper
# ---------------------------------------------------------------------------

def _uaterm_label(ua_value):
    """
    Return a filename-safe label for a UATerm value.

    Encodes UATerm × 10 as a zero-padded 2-digit integer prefixed with "UA".

    Examples
    --------
    _uaterm_label(0.2)  → "UA02"
    _uaterm_label(0.9)  → "UA09"
    _uaterm_label(1.0)  → "UA10"
    _uaterm_label(1.2)  → "UA12"
    """
    tenths = int(round(ua_value * 10))
    return f"UA{tenths:02d}"


# ==============================================================================
# PLAN: janUAtermTest
# Single-pass UATerm sweep across all samples.
# ==============================================================================

def janUAtermTest(md={}):
    """
    Sweep UATerm from 0.2 to 1.2 collecting USAXS at 4 flyscan times per step.

    Outer loop:  UATerm values in UATERM_VALUES (0.2, 0.3, …, 1.2).
    Middle loop: flyscan times in FLYSCAN_TIMES (60, 90, 120, 180 s).
    Inner loop:  samples in SampleList.

    Each scan is named:  {sampleName}_{uaterm_label}_{scan_time_s}s
        e.g.  "Sample_1_UA06_90s"

    Runs once, then calls after_command_list() automatically.
    No SAXS or WAXS — USAXS only.

    Edit SampleList at the top of this file, then reload and run:
        %run -im usaxs.user.jan_uatermtest

    Debug mode (no instrument motion):
        loop_debug.put(True)

    Run:
        RE(janUAtermTest())
    """

    # ------------------------------------------------------------------
    # Inner helper function
    # ------------------------------------------------------------------

    def collectUSAXS(sampleName, sx, sy, thickness, ua_value, scan_time_s, debug=False):
        """
        Set UATerm and flyscan time, then collect one USAXS scan.

        Parameters
        ----------
        sampleName : str
            Base name for this sample (from SampleList).
        sx, sy : float
            Stage positions in mm.
        thickness : float
            Sample thickness in mm.
        ua_value : float
            UATerm value set before this scan.
        scan_time_s : int
            USAXS flyscan time in seconds.
        debug : bool
            True → print action and sleep briefly; always pass isDebugMode.
        """
        sampleMod = f"{sampleName}_{_uaterm_label(ua_value)}_{scan_time_s}s"
        if debug:
            print(
                f"[DEBUG] USAXS [{sampleName}] UATerm={ua_value:.1f} "
                f"t={scan_time_s}s: {sampleMod}  pos=({sx}, {sy})"
            )
            yield from bps.sleep(5)
        else:
            yield from bps.mv(uaterm, ua_value)
            yield from bps.mv(flyscan_scan_time, scan_time_s)
            yield from sync_order_numbers()
            md["title"] = sampleMod
            logger.info(
                "USAXSscan [%s, UATerm=%.1f, t=%ds]: %s",
                sampleName, ua_value, scan_time_s, sampleMod,
            )
            yield from USAXSscan(sx, sy, thickness, sampleMod, md={})

    # ------------------------------------------------------------------
    # Execution sequence
    # ------------------------------------------------------------------

    isDebugMode = loop_debug.get()
    recordFunctionRun()

    total_scans = len(UATERM_VALUES) * len(FLYSCAN_TIMES) * len(SampleList)
    ua_str      = ", ".join(f"{v:.1f}" for v in UATERM_VALUES)
    times_str   = ", ".join(str(t) for t in FLYSCAN_TIMES)
    sample_names = ", ".join(row[0] for row in SampleList)

    logger.info(
        "Starting janUAtermTest | %d samples | UATerm=[%s] | "
        "times=[%s] s | %d total scans | debug=%s",
        len(SampleList), ua_str, times_str, total_scans, isDebugMode,
    )

    if not isDebugMode:
        yield from before_command_list()
    else:
        logger.info("[DEBUG] Skipping before_command_list()")

    appendToMdFile(
        f"Starting janUAtermTest: {len(SampleList)} samples ({sample_names}), "
        f"UATerm=[{ua_str}], USAXS times=[{times_str}] s, "
        f"{total_scans} scans total — USAXS only, single pass"
    )

    t0 = time.time()

    for ua_value in UATERM_VALUES:
        logger.info(
            "  UATerm = %.1f (%s)", ua_value, _uaterm_label(ua_value)
        )
        for scan_time_s in FLYSCAN_TIMES:
            logger.info(
                "    UATerm=%.1f | flyscan time = %d s", ua_value, scan_time_s
            )
            for sampleName, sx, sy, thickness in SampleList:
                yield from collectUSAXS(
                    sampleName, sx, sy, thickness,
                    ua_value, scan_time_s, isDebugMode,
                )

    elapsed_min = (time.time() - t0) / MINUTE
    logger.info(
        "janUAtermTest complete | %d scans | %.1f min total",
        total_scans, elapsed_min,
    )
    appendToMdFile(
        f"janUAtermTest complete: {total_scans} USAXS scans, "
        f"{elapsed_min:.0f} min total"
    )

    if not isDebugMode:
        yield from after_command_list()
    else:
        logger.info("[DEBUG] Skipping after_command_list()")
