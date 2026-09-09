"""
External-device template — drive hardware that is not in the USAXS device YAML.

==============================================================================
PURPOSE
==============================================================================

Some user experiments bring their own hardware to the hutch: a load frame, a
syringe pump, a humidity cell, a flow controller, a stepper on a spare motor
channel.  That hardware is not declared in ``src/usaxs/configs/*.yml`` and so
is not in ``oregistry``.  This template shows the supported pattern:

    1. group the EPICS PVs into one small ophyd Device subclass
    2. instantiate it once at module level
    3. step it through a list of setpoints, collecting USAXS/SAXS/WAXS at each
    4. read the live readback back into the scan name, so the file name records
       what the sample actually experienced (not just what was requested)

CHECK FIRST — if the device already exists in the instrument, do NOT redefine
it here.  Fetch it from the registry instead::

    from apsbits.core.instrument_init import oregistry
    ptc10 = oregistry["ptc10"]

``device_skills_*.md`` in the repository root lists every catalogued device,
its class, and its PVs.  Only fall back to this template for hardware that is
genuinely absent from that list.

==============================================================================
USAGE
==============================================================================

Copy to a new file, edit MyExternalDevice (PVs) and SetpointList, then:

Load:
    %run -im usaxs.user.<new_filename>

Debug / dry-run (no USAXS data collection; the external device IS still
driven, so the setpoint sequence and timing are exercised for real):
    device_debug.put(True)
    RE(measureVsSetpoint(0, 0, 1.0, "MySample"))

Real run:
    device_debug.put(False)
    RE(measureVsSetpoint(0, 0, 1.0, "MySample"))

==============================================================================
SAMPLE NAME FORMAT
==============================================================================

    {scan_title}_{readback:.0f}{units}_{elapsed_minutes:.0f}min

The readback is read live at the moment each scan starts, so it reflects the
real state of the device rather than the requested setpoint.

CHANGE LOG:
    * JIL, 2026-09-09 : Initial external-device template
"""

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

import time

from bluesky import plan_stubs as bps
from ophyd import Component
from ophyd import Device
from ophyd import EpicsMotor
from ophyd import EpicsSignal
from ophyd import EpicsSignalRO
from ophyd import Signal

from usaxs.plans.command_list import after_command_list
from usaxs.plans.command_list import before_command_list
from usaxs.plans.command_list import sync_order_numbers
from usaxs.plans.plans_usaxs import USAXSscan
from usaxs.plans.plans_user_facing import saxsExp
from usaxs.plans.plans_user_facing import waxsExp
from usaxs.utils.obsidian import appendToMdFile
from usaxs.utils.obsidian import recordFunctionRun

# Convenient time-unit constants.
SECOND = 1
MINUTE = 60 * SECOND
HOUR = 60 * MINUTE

# Debug / dry-run flag.  Set at the IPython prompt BEFORE calling RE():
#   device_debug.put(True)   → skip USAXS/SAXS/WAXS collection and the
#                              before/after_command_list() instrument scripts;
#                              the external device is still driven normally
#   device_debug.put(False)  → normal mode (default)
device_debug = Signal(name="device_debug", value=False)


class MyExternalDevice(Device):
    """
    Ophyd device grouping the user hardware PVs into one object.

    Replace the components and PV names below with the real hardware.  Use:

      * ``EpicsMotor``    for anything with a full EPICS motor record
        (setpoint, readback, .DMOV, limits).  ``bps.mv`` blocks until the
        motor reports done.
      * ``EpicsSignal``   for a writable non-motor setpoint (a temperature,
        a flow rate, a voltage).  ``bps.mv`` returns as soon as the put
        completes — it does NOT wait for the physical quantity to settle.
      * ``EpicsSignalRO`` for a readback-only value (a load cell, a
        thermocouple, a pressure gauge).

    Components
    ----------
    setpoint : EpicsSignal
        Writable target value for the controlled quantity.
    readback : EpicsSignalRO
        Live measured value of the controlled quantity.
    stage : EpicsMotor
        Optional positioner belonging to the user hardware (mm).
    """

    setpoint = Component(EpicsSignal, "usxLAX:userCalc1.A", kind="hinted")
    readback = Component(EpicsSignalRO, "usxLAX:userCalc1.VAL", kind="hinted")
    stage = Component(EpicsMotor, "usxLAX:m58:c0:m1", kind="hinted")


# Instantiate once at module level; the ophyd registry picks it up automatically.
# The empty prefix is correct when every Component carries its own full PV.
my_device = MyExternalDevice("", name="my_device")

# Units string used only for building scan names (e.g. "N", "C", "kPa", "pct").
UNITS = "N"

# ==============================================================================
# EDIT THIS LIST, then reload the file with %run -im ...
# One USAXS/SAXS/WAXS set is collected at each setpoint, in order.
# ==============================================================================
SetpointList = [0, 10, 20, 50, 100]

# Seconds to wait after each setpoint change before collecting, so the sample
# can equilibrate.  Set to 0 when the device readback is trustworthy on arrival.
SETTLE_TIME = 60 * SECOND


def measureVsSetpoint(pos_X, pos_Y, thickness, scan_title, numScans=1, md={}):
    """
    Step the external device through SetpointList, collecting data at each step.

    At every setpoint the plan waits SETTLE_TIME seconds, then collects
    numScans complete USAXS → SAXS → WAXS sets.  Use numScans > 1 to follow
    relaxation or kinetics while the setpoint is held.

    Parameters
    ----------
    pos_X, pos_Y : float
        Sample stage X/Y position in mm.
    thickness : float
        Sample thickness in mm (used for transmission correction).
    scan_title : str
        Base name for all scans.  Readback and elapsed time are appended.
    numScans : int, optional
        Number of USAXS/SAXS/WAXS sets collected at each setpoint.  Default 1.
    md : dict, optional
        Extra metadata.

    Notes
    -----
    Elapsed time in the scan name is reset at each setpoint, so it reads as
    "minutes into this step" rather than minutes since the plan started.

    Load:
        %run -im usaxs.user.<new_filename>

    Run:
        RE(measureVsSetpoint(0, 0, 1.0, "MySample", numScans=4))
    """

    # ------------------------------------------------------------------
    # Inner helper functions
    # ------------------------------------------------------------------

    def getSampleName():
        """
        Return scan name encoding the live device readback and elapsed minutes.

        Format: {scan_title}_{readback:.0f}{UNITS}_{elapsed_minutes:.0f}min
        """
        return (
            f"{scan_title}"
            f"_{my_device.readback.get():.0f}{UNITS}"
            f"_{(time.time() - t0) / MINUTE:.0f}min"
        )

    def collectAllThree(debug=False):
        """
        Collect USAXS → SAXS → WAXS at (pos_X, pos_Y).

        The name is rebuilt before each detector so every file records the
        device readback at its own acquisition time.  sync_order_numbers()
        first, so the three scans share one scan-group number.

        Parameters
        ----------
        debug : bool
            True → print the sample name and sleep instead of collecting.
            Always pass isDebugMode; never hardcode.
        """
        sampleMod = getSampleName()
        if debug:
            print(f"[DEBUG] collectAllThree: {sampleMod}")
            yield from bps.sleep(20)
        else:
            yield from sync_order_numbers()
            sampleMod = getSampleName()
            md["title"] = sampleMod
            logger.info("USAXSscan: %s", sampleMod)
            yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = getSampleName()
            md["title"] = sampleMod
            logger.info("saxsExp: %s", sampleMod)
            yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = getSampleName()
            md["title"] = sampleMod
            logger.info("waxsExp: %s", sampleMod)
            yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    # ------------------------------------------------------------------
    # Execution sequence
    # ------------------------------------------------------------------

    isDebugMode = device_debug.get()
    recordFunctionRun()
    logger.info(
        "Starting measureVsSetpoint | sample=%s | %d setpoints | %d scans each "
        "| debug=%s",
        scan_title,
        len(SetpointList),
        numScans,
        isDebugMode,
    )

    if not isDebugMode:
        yield from before_command_list()
    else:
        logger.info("[DEBUG] Skipping before_command_list()")

    appendToMdFile(
        f"## External device run: {scan_title}\n"
        f"- **Position:** x={pos_X} mm, y={pos_Y} mm, thickness={thickness} mm\n"
        f"- **Setpoints ({UNITS}):** {SetpointList}\n"
        f"- **Settle time:** {SETTLE_TIME} s\n"
        f"- **Scans per setpoint:** {numScans}"
    )

    t0 = time.time()

    for setpoint in SetpointList:
        logger.info("Moving external device to %s %s", setpoint, UNITS)
        yield from bps.mv(my_device.setpoint, setpoint)
        appendToMdFile(f"Setpoint changed to {setpoint} {UNITS}")

        if SETTLE_TIME > 0:
            logger.info("Settling for %s s", SETTLE_TIME)
            yield from bps.sleep(SETTLE_TIME)

        # Reset t0 so the name reports minutes into THIS step.
        t0 = time.time()

        for _scan in range(numScans):
            yield from collectAllThree(isDebugMode)

    logger.info("measureVsSetpoint finished for sample %s", scan_title)
    appendToMdFile(f"External device run complete: {scan_title}")

    if not isDebugMode:
        yield from after_command_list()
    else:
        logger.info("[DEBUG] Skipping after_command_list()")
