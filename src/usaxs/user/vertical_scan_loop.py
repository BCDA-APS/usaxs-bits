"""
Vertical scan loop plan with manual temperature control and thermocouple readback.

Scans two or three samples vertically from sy1 to sy2 in 1 mm steps, collecting
USAXS/SAXS/WAXS at each position for every sample before stepping to the next
vertical position.  The loop repeats until stopped (Ctrl-C or RE.abort()).
Temperature is manually controlled; the thermocouple readback
(usxLAX:adam2:tc1.VAL) is embedded in every scan name, rounded to the nearest
integer degree.

==============================================================================
USAGE
==============================================================================

Load:
    %run -im usaxs.user.vertical_scan_loop

Define samples as a list of (name, sx, thickness) tuples:
    samples = [
        ("Sample1", 25.0, 1.0),   # (sample_name, sx_mm, thickness_mm)
        ("Sample2", 30.0, 1.5),
        ("Sample3", 35.0, 2.0),   # optional third (or more) sample
    ]

Debug mode (no instrument motion):
    loop_debug.put(True)
    RE(verticalScanLoop(10.0, 20.0))

Real run:
    loop_debug.put(False)
    RE(verticalScanLoop(10.0, 20.0))

Stop:
    RE.abort()   (or Ctrl-C at the IPython prompt)

    NOTE: after_command_list() does NOT run automatically on abort.
    Run it manually once the plan has stopped:
        RE(after_command_list())

==============================================================================
PARAMETERS
==============================================================================

    samples : list of (str, float, float)
        List of (sample_name, sx, thickness) tuples — one entry per sample.
        sx and thickness may differ between samples; sy range is shared.
    sy1     : float — starting vertical stage position in mm (common)
    sy2     : float — ending vertical stage position in mm (common)
    md      : dict  — extra metadata (optional)

==============================================================================
SAMPLE NAME FORMAT
==============================================================================

    {sample_name}_TC{temp_C}C_{elapsed}min

    TC      = secondary thermocouple temperature rounded to nearest integer °C
    elapsed = minutes elapsed since the plan started, rounded to nearest integer

==============================================================================
ITERATION ORDER
==============================================================================

    For each sy in [sy1 … sy2] (1 mm steps):
        measure sample[0] at (sx[0], sy)
        measure sample[1] at (sx[1], sy)
        measure sample[2] at (sx[2], sy)   ← only if present
        …

==============================================================================
CHANGE LOG
==============================================================================

    * JIL, 2026-03-31 : Created
    * JIL, 2026-04-01 : Extended to support 2–N samples via samples list
"""

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

import time

from bluesky import plan_stubs as bps
from ophyd import EpicsSignalRO, Signal

from usaxs.plans.plans_user_facing import saxsExp
from usaxs.plans.plans_user_facing import waxsExp
from usaxs.plans.plans_usaxs import USAXSscan
from usaxs.plans.command_list import after_command_list, sync_order_numbers
from usaxs.plans.command_list import before_command_list
from usaxs.utils.obsidian import appendToMdFile, recordFunctionRun

# Secondary thermocouple — measures actual sample temperature.
tc_sample = EpicsSignalRO("usxLAX:adam1:rtd5.VAL", name="tc_sample")

# Convenient time-unit constants.
SECOND = 1
MINUTE = 60 * SECOND
HOUR = 60 * MINUTE

# Debug / dry-run flag.  Set at the IPython prompt before calling RE():
#   loop_debug.put(True)   → debug mode (no instrument motion, 5 s sleep per position)
#   loop_debug.put(False)  → normal operation (default)
loop_debug = Signal(name="loop_debug", value=False)


samples = [
    ("NMRTubeBlank", 25.0, 4.0),  # (sample_name, sx_mm, thickness_mm)
    ("AMC", 55, 4.0),
    ("ACMC50", 75, 4.0),
    ("ACMC75", 115, 4.0),
    ("ACMC25", 135, 4.0),
    # ("NMRTubeBlank2",  55.0, 4.0),   # (sample_name, sx_mm, thickness_mm)
    # ("Sample3", 35.0, 4.0),   # optional third (or more) sample
]


def verticalScanLoop(sy1, sy2, md={}):
    """
    Scan sy1 → sy2 in 1 mm steps, measuring every sample at each position; repeat until stopped.

    Edit the module-level ``samples`` list before running to define which
    samples to measure and their positions::

        samples = [
            ("PEO_film",  25.0, 0.5),   # (name, sx_mm, thickness_mm)
            ("PS_film",   30.0, 1.0),
            ("blend",     35.0, 0.8),   # add or remove entries as needed
        ]
        RE(verticalScanLoop(10.0, 20.0))

    At each vertical position *sy* the plan iterates through all entries in
    *samples* in order before moving to the next *sy*.  Temperature is manually
    controlled; the thermocouple at usxLAX:adam2:tc1.VAL is read and embedded
    (as an integer) in every scan name so data can be sorted by temperature in
    post-processing.

    Parameters
    ----------
    sy1 : float
        Starting vertical stage position in mm (common to all samples).
    sy2 : float
        Ending vertical stage position in mm, inclusive (common to all samples).
    md : dict, optional
        Extra metadata attached to every scan.

    Sample name format::

        {sample_name}_TC{temp_C}C_{elapsed}min

    ``elapsed`` is the number of minutes since the plan started, rounded to
    the nearest integer.

    The plan loops forever; stop it with RE.abort() or Ctrl-C.
    After stopping, run teardown manually if needed::

        RE(after_command_list())

    Load:
        %run -im usaxs.user.vertical_scan_loop

    Debug:
        loop_debug.put(True)
        RE(verticalScanLoop(10.0, 20.0))

    Real run:
        loop_debug.put(False)
        RE(verticalScanLoop(10.0, 20.0))
    """

    # Build position list: sy1 to sy2 inclusive, 1 mm steps.
    step = 1.0 if sy2 >= sy1 else -1.0
    n_pos = int(abs(sy2 - sy1) / 1.0) + 1
    positions = [sy1 + i * step for i in range(n_pos)]

    def getSampleName(sample_name):
        """Return scan name with TC temperature (integer) and elapsed minutes."""
        tc_temp = tc_sample.get()
        elapsed_min = round((time.time() - t0) / MINUTE)
        return f"{sample_name}_{round(tc_temp)}C_{elapsed_min}min"
        # return f"{sample_name}_{elapsed_min}min"

    def collectAtPosition(sample_name, sx, thickness, sy, debug=False):
        """Collect USAXS → SAXS → WAXS for one sample at vertical position sy."""
        if debug:
            sampleMod = getSampleName(sample_name)
            print(f"[DEBUG] collectAtPosition: {sampleMod}  pos=({sx}, {sy:.1f})")
            yield from bps.sleep(5)
        else:
            yield from sync_order_numbers()
            sampleMod = getSampleName(sample_name)
            md["title"] = sampleMod
            logger.info("USAXSscan: %s  Y=%.1f mm", sampleMod, sy)
            yield from USAXSscan(sx, sy, thickness, sampleMod, md={})
            sampleMod = getSampleName(sample_name)
            md["title"] = sampleMod
            logger.info("saxsExp:   %s  Y=%.1f mm", sampleMod, sy)
            yield from saxsExp(sx, sy, thickness, sampleMod, md={})
            sampleMod = getSampleName(sample_name)
            md["title"] = sampleMod
            logger.info("waxsExp:   %s  Y=%.1f mm", sampleMod, sy)
            yield from waxsExp(sx, sy, thickness, sampleMod, md={})

    # --- Execution sequence ---
    t0 = time.time()
    isDebugMode = loop_debug.get()
    recordFunctionRun()

    sample_names = [name for name, _sx, _th in samples]
    logger.info(
        "Starting verticalScanLoop | samples=%s | "
        "Y: %.1f → %.1f (%d positions, 1 mm step) | debug=%s",
        sample_names,
        sy1,
        sy2,
        len(positions),
        isDebugMode,
    )

    if not isDebugMode:
        yield from before_command_list()
    else:
        logger.info("[DEBUG] Skipping before_command_list()")

    sample_lines = "\n".join(
        f"  - **{name}**: sx={sx} mm, thickness={th} mm" for name, sx, th in samples
    )
    appendToMdFile(
        f"## Vertical scan loop: {', '.join(sample_names)}\n"
        f"- **Samples:**\n{sample_lines}\n"
        f"- **Y range:** {sy1} → {sy2} mm  ({len(positions)} positions, 1 mm steps)\n"
        f"- **TC PV:** usxLAX:adam2:tc1.VAL\n"
        f"- **Name format:** <sample>_TC<T>C_<min>min"
    )

    sweep = 0

    while True:
        sweep += 1
        tc_now = tc_sample.get()
        logger.info(
            "Sweep %d | TC=%.1f C (%d°C) | %d positions × %d samples | %.1f min elapsed",
            sweep,
            tc_now,
            round(tc_now),
            len(positions),
            len(samples),
            (time.time() - t0) / MINUTE,
        )
        for sy in positions:
            for sample_name, sx, thickness in samples:
                yield from collectAtPosition(
                    sample_name, sx, thickness, sy, isDebugMode
                )
