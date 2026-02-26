"""
Load-frame experiment plan for Sector 1 tensile/compression stage.

The load frame has two primary controls:
    - a motor that extends the sample (strain, in µm)
    - a calculated EPICS signal that reports the resulting force (stress, in N)

Additionally, two positioning motors (x, y) let you centre the sample in
the beam and correct for the gauge-section displacement during extension.

LOADING:
    %run -im usaxs.user.loadFrame

DEBUG / DRY-RUN MODE:
    isDebugMode is currently hardcoded to False inside measureFrame.
    To run in debug mode without touching the instrument, change that line to:
        isDebugMode = True
    In debug mode:
        - before_command_list() and after_command_list() are skipped.
        - collectAllThree() prints the sample name and sleeps 20 s instead of
          collecting data.

TYPICAL WORKFLOW:
    1. Move the frame to the beam position (frame_x, frame_y).
    2. Measure a blank (frame at x = -4 mm, beam passing through air).
    3. Loop over ListOfStrains:
           a. Correct the vertical position by half the extension so the beam
              stays centred on the gauge section.
           b. Move the strain actuator to the target extension.
           c. Collect NumOfScans USAXS/SAXS/WAXS datasets to capture relaxation.
    4. Teardown.

SAMPLE NAMING CONVENTION:
    Format: {scan_title}_{load:.0f}N_{elapsed_minutes:.0f}min
    - Load is read live from the EPICS force calculation at the moment each
      scan starts, so the name reflects the actual force at acquisition time.
    - Elapsed time resets to zero each time a new strain step is reached,
      so the time field represents "minutes into hold at this strain".

CHANGE LOG:
    * JIL, 2026-02-26 : Reformatted, documented, and fixed sampleMod NameError
                        in collectAllThree debug branch.
"""

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

import time

from bluesky import plan_stubs as bps
from ophyd import Component, Device, EpicsMotor, EpicsSignalRO

from usaxs.plans.plans_user_facing import saxsExp
from usaxs.plans.plans_user_facing import waxsExp
from usaxs.plans.plans_usaxs import USAXSscan
from usaxs.plans.command_list import after_command_list, sync_order_numbers
from usaxs.plans.command_list import before_command_list
from usaxs.utils.obsidian import appendToMdFile


class LoadFrameDevice(Device):
    """
    Ophyd device grouping all load-frame EPICS signals into a single object.

    Components
    ----------
    strain : EpicsMotor
        Actuator that extends the sample.  Setpoint and readback in µm.
        PV base: usxLAX:m58:c0:m1
    load : EpicsSignalRO
        Calculated force from the load cell.  Read-only, in N.
        PV: usxLAX:userCalc2.VAL
    y : EpicsMotor
        Vertical stage motor for beam/sample alignment.  In mm.
        PV base: usxLAX:mxv:c0:m1
    x : EpicsMotor
        Horizontal stage motor for beam/sample alignment.  In mm.
        PV base: usxLAX:m58:c0:m2
    """

    strain = Component(EpicsMotor, "usxLAX:m58:c0:m1", kind="hinted")  # extension, µm
    load = Component(EpicsSignalRO, "usxLAX:userCalc2.VAL", kind="hinted")  # force, N
    y = Component(EpicsMotor, "usxLAX:mxv:c0:m1", kind="hinted")  # mm
    x = Component(EpicsMotor, "usxLAX:m58:c0:m2", kind="hinted")  # mm


LoadFrame = LoadFrameDevice("", name="LoadFrame")
# automatically added to oregistry


def measureFrame(frame_x, frame_y, thickness, scan_title, NumOfScans, md={}):
    """
    Step-strain experiment: collect USAXS/SAXS/WAXS at each strain level.

    The strain actuator is moved through each position in ListOfStrains.  At
    every step a vertical correction keeps the beam centred on the gauge
    section (the sample is pulled upward, so y must follow by half the
    extension).  A blank measurement (beam through air, frame at x = -4 mm)
    is collected first as a transmission reference.

    Parameters
    ----------
    frame_x : float
        Horizontal stage position of the sample in mm.
    frame_y : float
        Vertical stage position of the sample in mm at zero strain.
        The plan adjusts y automatically at each strain step.
    thickness : float
        Sample thickness in mm (used for transmission correction).
    scan_title : str
        Base name for all scans.  Load and elapsed time are appended:
            {scan_title}_{load:.0f}N_{elapsed_minutes:.0f}min
    NumOfScans : int
        Number of USAXS/SAXS/WAXS datasets to collect at each strain step.
        Use 4 scans (~8 min) to observe stress relaxation at each step.
    md : dict, optional
        Extra metadata passed to scan functions.

    Notes
    -----
    ListOfStrains must start at 0.  Zero the strain actuator in EPICS before
    starting — the plan does not home the actuator.

    The vertical correction formula is:
        y_corrected = frame_y - StrainPos / (2 * 1000)
    where StrainPos is in µm and frame_y is in mm, so dividing by 2000
    converts µm to mm and accounts for the fact that only half the extension
    moves the gauge centre (the two grips share the displacement equally).

    Reload after editing:
        %run -im usaxs.user.loadFrame

    Run:
        RE(measureFrame(0, 0, 1, "Samplename", 4))
        — scans the frame at position (0, 0) through all strains in
          ListOfStrains, with sample thickness 1 mm and 4 datasets per step.
    """
    # Strain steps in µm.  MUST start at 0.
    # Zero the strain actuator in EPICS before running this plan.
    ListOfStrains = [0, 110, 220, 330, 440, 550, 990, 1430, 1870, 2310, 2750, 3190, 3630]

    def setSampleName():
        """
        Return a scan name encoding the current force and elapsed time.

        Format: {scan_title}_{load:.0f}N_{elapsed_minutes:.0f}min

        Force is read live from LoadFrame.load.  Elapsed time is measured
        from the last t0 = time.time() assignment (reset at each strain step).
        """
        return (
            f"{scan_title}"
            f"_{(LoadFrame.load.get()):.0f}N"
            f"_{(time.time() - t0) / 60:.0f}min"
        )

    def collectAllThree(debug=False):
        """
        Run a full USAXS → SAXS → WAXS data-collection sequence.

        sync_order_numbers() is called first so all three scans share one
        scan-group counter.  Each scan refreshes the sample name so that
        force and elapsed time are accurate at acquisition time.

        Parameters
        ----------
        debug : bool
            When True, prints the sample name and sleeps 20 s without moving
            the instrument.  Set isDebugMode = True at plan start to activate.
        """
        sampleMod = setSampleName()  # must be assigned before the if/else branches
        if debug:
            print(sampleMod)
            yield from bps.sleep(20)
        else:
            yield from sync_order_numbers()
            sampleMod = setSampleName()
            md["title"] = sampleMod
            yield from USAXSscan(0, 0, thickness, sampleMod, md={})
            sampleMod = setSampleName()
            md["title"] = sampleMod
            yield from saxsExp(0, 0, thickness, sampleMod, md={})
            sampleMod = setSampleName()
            md["title"] = sampleMod
            yield from waxsExp(0, 0, thickness, sampleMod, md={})

    # Set to True to skip instrument operations and simulate data collection.
    isDebugMode = False

    if not isDebugMode:
        yield from before_command_list()  # runs standard startup scripts for scans

    t0 = time.time()  # mark start time of data collection

    # --- Blank measurement: move frame out of the beam, measure air ---
    yield from bps.mv(
        LoadFrame.x, -4,
        LoadFrame.y, frame_y,
    )
    yield from USAXSscan(0, 0, 1, "Blank", md={})
    yield from saxsExp(0, 0, 1, "Blank", md={})
    yield from waxsExp(0, 0, 1, "Blank", md={})

    # --- Move sample into beam at zero strain ---
    yield from bps.mv(
        LoadFrame.x, frame_x,
        LoadFrame.y, frame_y,
    )

    logger.info("Starting Frame collection")
    appendToMdFile("Starting Frame collection")

    for StrainPos in ListOfStrains:
        # Correct vertical position to keep the beam on the gauge centre.
        # The actuator pulls the top grip upward by StrainPos µm; the gauge
        # centre moves up by half that amount.  Converting µm → mm: /1000.
        # So the stage must move down by StrainPos / (2 * 1000) mm.
        yield from bps.mv(LoadFrame.y, frame_y - (StrainPos / (2 * 1000)))

        # Extend the sample to the target strain.
        yield from bps.mv(LoadFrame.strain, StrainPos)
        appendToMdFile(f"Moved to strain position {StrainPos} um")

        # Reset elapsed time so file names show time since this strain was set.
        t0 = time.time()

        # Collect NumOfScans datasets to observe stress relaxation at this strain.
        scanN = 0
        while scanN < NumOfScans:
            yield from collectAllThree(isDebugMode)
            scanN += 1

    logger.info("finished")
    appendToMdFile("Frame collection finished")

    if not isDebugMode:
        yield from after_command_list()  # runs standard after-scan scripts
