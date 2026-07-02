"""
Instrument stability verification and overnight data collection plans.

Three plans are provided:

1. stabilityOvernightPlan()
   USAXS time series (15–180 s) + SAXS + WAXS for two samples, cycles
   indefinitely with a configurable sleep between cycles.

2. stabilityWidthScanPlan()
   USAXS-only.  Sweeps the horizontal slit width (PV usxLAX:USAXS_hslit_ap)
   from 1.0 mm down to 0.1 mm in 0.1 mm steps.  At each width, collects
   both samples across the full time series (15–180 s).  No SAXS/WAXS.
   Cycles indefinitely until stopped.

3. stabilityNumPointsScanPlan()
   USAXS-only, single pass.  Collects both samples at each of the four
   NumPulsePositions values (1000, 2000, 4000, 8000) across the full time
   series (15–180 s).  No SAXS/WAXS.  Runs once and stops.

==============================================================================
PLAN 1 — stabilityOvernightPlan
==============================================================================

MEASUREMENT SEQUENCE (one complete cycle):
-----------------------------------------
For each flyscan time in FLYSCAN_TIMES = [15, 30, 60, 90, 120, 150, 180] s:
    1. Set USAXS flyscan time PV (usxLAX:USAXS:FS_ScanTime) to scan_time_s.
    2. USAXSscan — AirBlank   (filename includes flyscan time, e.g. "15s")
    3. USAXSscan — SRM3600    (filename includes flyscan time, e.g. "15s")

After all 7 USAXS times (flyscan time PV is NOT changed for SAXS/WAXS):
    4. saxsExp  — AirBlank   (single measurement)
    5. saxsExp  — SRM3600
    6. waxsExp  — AirBlank
    7. waxsExp  — SRM3600

Sleep 10 minutes (default), then repeat from step 1.

FILENAMES
---------
USAXS : {sample_name}_{scan_time_s}s_{elapsed_min:.0f}min
SAXS  : {sample_name}_SAXS_{elapsed_min:.0f}min
WAXS  : {sample_name}_WAXS_{elapsed_min:.0f}min

==============================================================================
PLAN 2 — stabilityWidthScanPlan
==============================================================================

MEASUREMENT SEQUENCE (one complete cycle):
-----------------------------------------
For each slit width in SLIT_WIDTHS_MM = [1.0, 0.9, ..., 0.1] mm:
    Set PV usxLAX:USAXS_hslit_ap to the width.
    For each flyscan time in FLYSCAN_TIMES = [15, 30, 60, 90, 120, 150, 180] s:
        Set PV usxLAX:USAXS:FS_ScanTime to scan_time_s.
        USAXSscan — AirBlank
        USAXSscan — SRM3600

Repeat until RE.abort().

FILENAMES
---------
USAXS : {sample_name}_{width_label}_{scan_time_s}s
  where width_label is: 1mm, 09mm, 08mm, ..., 01mm

==============================================================================
PLAN 3 — stabilityNumPointsScanPlan
==============================================================================

MEASUREMENT SEQUENCE (single pass):
------------------------------------
For each num_points in NUM_POINTS_LIST = [1000, 2000, 4000, 8000]:
    Set PV usxAERO:pm1:NumPulsePositions to num_points.
    For each flyscan time in FLYSCAN_TIMES = [15, 30, 60, 90, 120, 150, 180] s:
        Set PV usxLAX:USAXS:FS_ScanTime to scan_time_s.
        USAXSscan — AirBlank
        USAXSscan — SRM3600

Runs once, then calls after_command_list() automatically.

FILENAMES
---------
USAXS : {sample_name}_{points_label}_{scan_time_s}s
  where points_label is: 1k, 2k, 4k, 8k

==============================================================================
SAMPLE POSITIONS (all plans)
==============================================================================
AirBlank : sx=20, sy=140, thickness=1 mm
SRM3600  : sx=20, sy=120, thickness=1 mm

==============================================================================
USAGE
==============================================================================

Load:
    %run -im usaxs.user.stability_overnight

Debug mode (no instrument motion, prints actions only):
    loop_debug.put(True)
    RE(stabilityOvernightPlan())
    RE(stabilityWidthScanPlan())
    RE(stabilityNumPointsScanPlan())

Real run:
    loop_debug.put(False)
    RE(stabilityOvernightPlan())          # loops until RE.abort()
    RE(stabilityWidthScanPlan())          # loops until RE.abort()
    RE(stabilityNumPointsScanPlan())      # runs once, then finishes

Stop (plans 1 and 2 only):
    RE.abort()   (or Ctrl-C at the IPython prompt)

    NOTE: after_command_list() does NOT run automatically on abort.
    Run it manually once the plan has stopped:
        RE(after_command_list())

==============================================================================
CHANGE LOG
==============================================================================

    * JIL, 2026-05-30 : Created for instrument stability overnight verification
    * JIL, 2026-05-31 : Added stabilityWidthScanPlan (slit-width sweep, USAXS only)
                        Added stabilityNumPointsScanPlan (num-points sweep, single pass)
"""

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

import time

from bluesky import plan_stubs as bps
from ophyd import EpicsSignal, Signal

from usaxs.plans.plans_user_facing import saxsExp
from usaxs.plans.plans_user_facing import waxsExp
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
# Horizontal slit aperture width (PV: usxLAX:USAXS_hslit_ap).
# Used by stabilityWidthScanPlan.
# ---------------------------------------------------------------------------
usaxs_hslit_width = EpicsSignal(
    "usxLAX:USAXS_hslit_ap", name="usaxs_hslit_width"
)

# ---------------------------------------------------------------------------
# Number of pulse positions (PV: usxAERO:pm1:NumPulsePositions).
# Used by stabilityNumPointsScanPlan.
# ---------------------------------------------------------------------------
num_pulse_positions = EpicsSignal(
    "usxAERO:pm1:NumPulsePositions", name="num_pulse_positions"
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
# USAXS flyscan times shared by all three plans (seconds).
# ---------------------------------------------------------------------------
FLYSCAN_TIMES = [15, 30, 60, 90, 120, 150, 180]

# ---------------------------------------------------------------------------
# Slit widths for stabilityWidthScanPlan (mm, decreasing).
# ---------------------------------------------------------------------------
SLIT_WIDTHS_MM = [round(w * 0.1, 1) for w in range(10, 0, -1)]  # 1.0 → 0.1

# ---------------------------------------------------------------------------
# NumPulsePositions values for stabilityNumPointsScanPlan.
# ---------------------------------------------------------------------------
NUM_POINTS_LIST = [1000, 2000, 4000, 8000]

# ---------------------------------------------------------------------------
# Sample definitions.  Edit positions here; reload the file to update.
# Format: [pos_X_mm, pos_Y_mm, thickness_mm, "SampleName"]
# Order matters — AirBlank is always measured before SRM3600.
# ---------------------------------------------------------------------------
SampleList = [
    [20, 140, 1, "AirBlank"],
    [20, 120, 1, "SRM3600"],
]


# ---------------------------------------------------------------------------
# Filename label helpers
# ---------------------------------------------------------------------------

def _width_label(width_mm):
    """
    Return a filename-safe label for a slit width value.

    Examples
    --------
    _width_label(1.0)  → "1mm"
    _width_label(0.9)  → "09mm"
    _width_label(0.1)  → "01mm"
    """
    tenths = int(round(width_mm * 10))
    if tenths >= 10:
        return f"{tenths // 10}mm"
    return f"0{tenths}mm"


def _points_label(n):
    """
    Return a filename-safe label for a NumPulsePositions value.

    Examples
    --------
    _points_label(1000) → "1k"
    _points_label(8000) → "8k"
    """
    return f"{n // 1000}k"


# ==============================================================================
# PLAN 1 — stabilityOvernightPlan
# ==============================================================================

def stabilityOvernightPlan(sleep_min=10, md={}):
    """
    Overnight stability plan: USAXS time series + SAXS/WAXS, repeat with sleep.

    One complete cycle:
        - For each scan time in FLYSCAN_TIMES (15, 30, 60, 90, 120, 150, 180 s):
            set PV usxLAX:USAXS:FS_ScanTime, then collect USAXS for each sample
            in SampleList in order (AirBlank first, SRM3600 second).
        - Collect one SAXS measurement per sample (AirBlank, then SRM3600).
        - Collect one WAXS measurement per sample (AirBlank, then SRM3600).
        - Sleep sleep_min minutes.
        - Repeat.

    The plan loops indefinitely until stopped with RE.abort().  After stopping,
    run  RE(after_command_list())  manually to restore the instrument.

    Parameters
    ----------
    sleep_min : float, optional
        Sleep time in minutes between consecutive cycles (default 10 min).
    md : dict, optional
        Extra metadata forwarded to each scan.

    Load:
        %run -im usaxs.user.stability_overnight

    Debug mode (no instrument motion):
        loop_debug.put(True)

    Run:
        RE(stabilityOvernightPlan())

    Stop:
        RE.abort()
        RE(after_command_list())   # run manually after abort
    """

    # ------------------------------------------------------------------
    # Inner helper functions
    # ------------------------------------------------------------------

    def getSampleName(scan_title, suffix=""):
        """
        Return scan filename encoding scan_title, an optional suffix, and
        elapsed minutes since t0.

        Format (no suffix):    {scan_title}_{elapsed_min:.0f}min
        Format (with suffix):  {scan_title}_{suffix}_{elapsed_min:.0f}min

        Examples
        --------
        getSampleName("AirBlank", "15s")   → "AirBlank_15s_0min"
        getSampleName("SRM3600",  "SAXS")  → "SRM3600_SAXS_12min"
        """
        elapsed = (time.time() - t0) / MINUTE
        if suffix:
            return f"{scan_title}_{suffix}_{elapsed:.0f}min"
        return f"{scan_title}_{elapsed:.0f}min"

    def collectUSAXS(pos_X, pos_Y, thickness, scan_title, scan_time_s, debug=False):
        """
        Set the flyscan time then collect one USAXS scan for a single sample.

        The flyscan time (seconds) is embedded in the scan filename so that
        datasets at different times are uniquely identified.

        Parameters
        ----------
        pos_X, pos_Y : float
            Stage position in mm for this sample.
        thickness : float
            Sample thickness in mm.
        scan_title : str
            Base sample name (from SampleList).
        scan_time_s : int
            USAXS flyscan time in seconds; embedded in the filename.
        debug : bool
            True → print action and sleep briefly; never hardcode.
        """
        suffix = f"{scan_time_s}s"
        if debug:
            sampleMod = getSampleName(scan_title, suffix)
            print(
                f"[DEBUG] USAXS [{scan_title}] t={scan_time_s}s: "
                f"{sampleMod}  pos=({pos_X}, {pos_Y})"
            )
            yield from bps.sleep(5)
        else:
            yield from bps.mv(flyscan_scan_time, scan_time_s)
            yield from sync_order_numbers()
            sampleMod = getSampleName(scan_title, suffix)
            md["title"] = sampleMod
            logger.info(
                "USAXSscan [%s, %ds]: %s", scan_title, scan_time_s, sampleMod
            )
            yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})

    def collectSAXS(pos_X, pos_Y, thickness, scan_title, debug=False):
        """
        Collect one SAXS scan for a single sample.

        Parameters
        ----------
        pos_X, pos_Y : float  — stage position in mm
        thickness : float     — sample thickness in mm
        scan_title : str      — base sample name
        debug : bool          — pass isDebugMode; never hardcode
        """
        if debug:
            sampleMod = getSampleName(scan_title, "SAXS")
            print(
                f"[DEBUG] SAXS [{scan_title}]: {sampleMod}"
                f"  pos=({pos_X}, {pos_Y})"
            )
            yield from bps.sleep(5)
        else:
            sampleMod = getSampleName(scan_title, "SAXS")
            md["title"] = sampleMod
            logger.info("saxsExp [%s]: %s", scan_title, sampleMod)
            yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    def collectWAXS(pos_X, pos_Y, thickness, scan_title, debug=False):
        """
        Collect one WAXS scan for a single sample.

        Parameters
        ----------
        pos_X, pos_Y : float  — stage position in mm
        thickness : float     — sample thickness in mm
        scan_title : str      — base sample name
        debug : bool          — pass isDebugMode; never hardcode
        """
        if debug:
            sampleMod = getSampleName(scan_title, "WAXS")
            print(
                f"[DEBUG] WAXS [{scan_title}]: {sampleMod}"
                f"  pos=({pos_X}, {pos_Y})"
            )
            yield from bps.sleep(5)
        else:
            sampleMod = getSampleName(scan_title, "WAXS")
            md["title"] = sampleMod
            logger.info("waxsExp [%s]: %s", scan_title, sampleMod)
            yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    # ------------------------------------------------------------------
    # Execution sequence
    # ------------------------------------------------------------------

    isDebugMode = loop_debug.get()
    recordFunctionRun()
    times_str = ", ".join(str(t) for t in FLYSCAN_TIMES)
    sample_names = ", ".join(s[3] for s in SampleList)
    logger.info(
        "Starting stabilityOvernightPlan | samples=[%s] | "
        "USAXS times=[%s] s | sleep=%s min | debug=%s",
        sample_names, times_str, sleep_min, isDebugMode,
    )

    if not isDebugMode:
        yield from before_command_list()
    else:
        logger.info("[DEBUG] Skipping before_command_list()")

    appendToMdFile(
        f"Starting stabilityOvernightPlan: samples=[{sample_names}], "
        f"USAXS times=[{times_str}] s, then SAXS+WAXS per sample, "
        f"sleep {sleep_min} min between cycles — runs until RE.abort()"
    )

    t0 = time.time()
    cycle = 0

    while True:
        elapsed_min = (time.time() - t0) / MINUTE
        logger.info(
            "=== Cycle %d start (%.0f min elapsed) ===", cycle + 1, elapsed_min
        )

        # --- USAXS time series -------------------------------------------
        # For each flyscan time, set the PV and measure every sample in order.
        for scan_time_s in FLYSCAN_TIMES:
            logger.info(
                "  Cycle %d | USAXS flyscan time = %d s", cycle + 1, scan_time_s
            )
            for pos_X, pos_Y, thickness, scan_title in SampleList:
                yield from collectUSAXS(
                    pos_X, pos_Y, thickness, scan_title, scan_time_s, isDebugMode
                )

        # --- Single SAXS measurement per sample (no time change) ----------
        logger.info("  Cycle %d | SAXS measurements", cycle + 1)
        for pos_X, pos_Y, thickness, scan_title in SampleList:
            yield from collectSAXS(
                pos_X, pos_Y, thickness, scan_title, isDebugMode
            )

        # --- Single WAXS measurement per sample (no time change) ----------
        logger.info("  Cycle %d | WAXS measurements", cycle + 1)
        for pos_X, pos_Y, thickness, scan_title in SampleList:
            yield from collectWAXS(
                pos_X, pos_Y, thickness, scan_title, isDebugMode
            )

        cycle += 1
        elapsed_min = (time.time() - t0) / MINUTE
        logger.info(
            "Cycle %d complete (%.0f min elapsed) — sleeping %.0f min",
            cycle, elapsed_min, sleep_min,
        )
        appendToMdFile(
            f"stabilityOvernightPlan cycle {cycle} complete, "
            f"{elapsed_min:.0f} min elapsed, sleeping {sleep_min} min"
        )

        yield from bps.sleep(sleep_min * MINUTE)

    # NOTE: The while-loop above runs until RE.abort() is called.
    # The lines below are unreachable in normal overnight use.
    # After abort, restore the instrument manually:
    #     RE(after_command_list())


# ==============================================================================
# PLAN 2 — stabilityWidthScanPlan
# ==============================================================================

def stabilityWidthScanPlan(md={}):
    """
    USAXS-only slit-width sweep, repeated until stopped.

    Sweeps the horizontal slit width (PV usxLAX:USAXS_hslit_ap) from 1.0 mm
    down to 0.1 mm in 0.1 mm steps.  At each width the plan collects both
    samples (AirBlank first, SRM3600 second) across all FLYSCAN_TIMES.
    No SAXS or WAXS is collected.

    The plan loops indefinitely until stopped with RE.abort().  After stopping,
    run  RE(after_command_list())  manually to restore the instrument.

    Filenames encode the width and scan time:
        {sample_name}_{width_label}_{scan_time_s}s
    where width_label is: 1mm, 09mm, 08mm, …, 01mm

    Parameters
    ----------
    md : dict, optional
        Extra metadata forwarded to each scan.

    Run:
        RE(stabilityWidthScanPlan())

    Stop:
        RE.abort()
        RE(after_command_list())   # run manually after abort
    """

    def makeWidthSampleName(scan_title, width_mm, scan_time_s):
        """Return filename: {scan_title}_{width_label}_{scan_time_s}s."""
        return f"{scan_title}_{_width_label(width_mm)}_{scan_time_s}s"

    def collectUSAXS_width(pos_X, pos_Y, thickness, scan_title,
                           width_mm, scan_time_s, debug=False):
        """
        Set slit width and flyscan time, then collect one USAXS scan.

        Parameters
        ----------
        pos_X, pos_Y : float  — stage position in mm
        thickness : float     — sample thickness in mm
        scan_title : str      — base sample name
        width_mm : float      — target slit width in mm
        scan_time_s : int     — USAXS flyscan time in seconds
        debug : bool          — pass isDebugMode; never hardcode
        """
        sampleMod = makeWidthSampleName(scan_title, width_mm, scan_time_s)
        if debug:
            print(
                f"[DEBUG] USAXS [{scan_title}] width={width_mm:.1f}mm "
                f"t={scan_time_s}s: {sampleMod}  pos=({pos_X}, {pos_Y})"
            )
            yield from bps.sleep(5)
        else:
            yield from bps.mv(usaxs_hslit_width, width_mm)
            yield from bps.mv(flyscan_scan_time, scan_time_s)
            yield from sync_order_numbers()
            md["title"] = sampleMod
            logger.info(
                "USAXSscan [%s, width=%.1fmm, t=%ds]: %s",
                scan_title, width_mm, scan_time_s, sampleMod,
            )
            yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})

    # ------------------------------------------------------------------
    # Execution sequence
    # ------------------------------------------------------------------

    isDebugMode = loop_debug.get()
    recordFunctionRun()
    widths_str = ", ".join(f"{w:.1f}" for w in SLIT_WIDTHS_MM)
    times_str  = ", ".join(str(t) for t in FLYSCAN_TIMES)
    sample_names = ", ".join(s[3] for s in SampleList)
    logger.info(
        "Starting stabilityWidthScanPlan | samples=[%s] | "
        "widths=[%s] mm | USAXS times=[%s] s | debug=%s",
        sample_names, widths_str, times_str, isDebugMode,
    )

    if not isDebugMode:
        yield from before_command_list()
    else:
        logger.info("[DEBUG] Skipping before_command_list()")

    appendToMdFile(
        f"Starting stabilityWidthScanPlan: samples=[{sample_names}], "
        f"slit widths=[{widths_str}] mm, USAXS times=[{times_str}] s — "
        f"runs until RE.abort()"
    )

    cycle = 0

    while True:
        logger.info("=== Width scan cycle %d start ===", cycle + 1)

        for width_mm in SLIT_WIDTHS_MM:
            logger.info(
                "  Cycle %d | slit width = %.1f mm", cycle + 1, width_mm
            )
            for scan_time_s in FLYSCAN_TIMES:
                for pos_X, pos_Y, thickness, scan_title in SampleList:
                    yield from collectUSAXS_width(
                        pos_X, pos_Y, thickness, scan_title,
                        width_mm, scan_time_s, isDebugMode,
                    )

        cycle += 1
        logger.info("Width scan cycle %d complete — repeating", cycle)
        appendToMdFile(
            f"stabilityWidthScanPlan cycle {cycle} complete, repeating"
        )

    # NOTE: loops until RE.abort().  Run RE(after_command_list()) manually.


# ==============================================================================
# PLAN 3 — stabilityNumPointsScanPlan
# ==============================================================================

def stabilityNumPointsScanPlan(md={}):
    """
    USAXS-only NumPulsePositions sweep, single pass.

    Iterates over NUM_POINTS_LIST = [1000, 2000, 4000, 8000].  At each value
    the plan sets PV usxAERO:pm1:NumPulsePositions, then collects both samples
    (AirBlank first, SRM3600 second) across all FLYSCAN_TIMES.  No SAXS or
    WAXS is collected.  Runs once and then calls after_command_list()
    automatically.

    Filenames encode the point count and scan time:
        {sample_name}_{points_label}_{scan_time_s}s
    where points_label is: 1k, 2k, 4k, 8k

    Parameters
    ----------
    md : dict, optional
        Extra metadata forwarded to each scan.

    Run:
        RE(stabilityNumPointsScanPlan())
    """

    def makePointsSampleName(scan_title, n_points, scan_time_s):
        """Return filename: {scan_title}_{points_label}_{scan_time_s}s."""
        return f"{scan_title}_{_points_label(n_points)}_{scan_time_s}s"

    def collectUSAXS_points(pos_X, pos_Y, thickness, scan_title,
                            n_points, scan_time_s, debug=False):
        """
        Set NumPulsePositions and flyscan time, then collect one USAXS scan.

        Parameters
        ----------
        pos_X, pos_Y : float  — stage position in mm
        thickness : float     — sample thickness in mm
        scan_title : str      — base sample name
        n_points : int        — target NumPulsePositions value
        scan_time_s : int     — USAXS flyscan time in seconds
        debug : bool          — pass isDebugMode; never hardcode
        """
        sampleMod = makePointsSampleName(scan_title, n_points, scan_time_s)
        if debug:
            print(
                f"[DEBUG] USAXS [{scan_title}] npts={n_points} "
                f"t={scan_time_s}s: {sampleMod}  pos=({pos_X}, {pos_Y})"
            )
            yield from bps.sleep(5)
        else:
            yield from bps.mv(num_pulse_positions, n_points)
            yield from bps.mv(flyscan_scan_time, scan_time_s)
            yield from sync_order_numbers()
            md["title"] = sampleMod
            logger.info(
                "USAXSscan [%s, npts=%d, t=%ds]: %s",
                scan_title, n_points, scan_time_s, sampleMod,
            )
            yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})

    # ------------------------------------------------------------------
    # Execution sequence
    # ------------------------------------------------------------------

    isDebugMode = loop_debug.get()
    recordFunctionRun()
    points_str   = ", ".join(str(n) for n in NUM_POINTS_LIST)
    times_str    = ", ".join(str(t) for t in FLYSCAN_TIMES)
    sample_names = ", ".join(s[3] for s in SampleList)
    logger.info(
        "Starting stabilityNumPointsScanPlan | samples=[%s] | "
        "num_points=[%s] | USAXS times=[%s] s | debug=%s",
        sample_names, points_str, times_str, isDebugMode,
    )

    if not isDebugMode:
        yield from before_command_list()
    else:
        logger.info("[DEBUG] Skipping before_command_list()")

    appendToMdFile(
        f"Starting stabilityNumPointsScanPlan: samples=[{sample_names}], "
        f"num_points=[{points_str}], USAXS times=[{times_str}] s — single pass"
    )

    for n_points in NUM_POINTS_LIST:
        logger.info("  NumPulsePositions = %d (%s)", n_points, _points_label(n_points))
        for scan_time_s in FLYSCAN_TIMES:
            for pos_X, pos_Y, thickness, scan_title in SampleList:
                yield from collectUSAXS_points(
                    pos_X, pos_Y, thickness, scan_title,
                    n_points, scan_time_s, isDebugMode,
                )

    logger.info("stabilityNumPointsScanPlan complete.")
    appendToMdFile("stabilityNumPointsScanPlan complete — single pass finished")

    if not isDebugMode:
        yield from after_command_list()
    else:
        logger.info("[DEBUG] Skipping after_command_list()")
