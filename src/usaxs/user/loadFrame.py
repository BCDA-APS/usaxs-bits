"""
This is for load frame from sector 1, the device has two controls -
motor to extend the sample (strain) and calculation to report the stress

%run -im usaxs.user.loadFrame

"""

# import needed stuff
import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

from apstools.callbacks import SpecWriterCallback2
from bluesky import RunEngine, plans as bp, plan_stubs as bps
from bluesky.callbacks.best_effort import BestEffortCallback
from ophyd import Component, Device, EpicsSignal, EpicsMotor, EpicsSignalRO

import time

from usaxs.plans.plans_user_facing import saxsExp
from usaxs.plans.plans_user_facing import waxsExp
from usaxs.plans.plans_usaxs import USAXSscan
from usaxs.plans.command_list import after_command_list, sync_order_numbers
from usaxs.plans.command_list import before_command_list
from ophyd import Signal
from usaxs.utils.obsidian import appendToMdFile


# # this is using simply adding strain and load as EpicsMotor and EpicsSignal
# strain = EpicsMotor("usxLAX:m58:c2:m1", name="strain", kind="hinted")
# load = EpicsSignal("usxLAX:userCalc2.VAL", name="load", kind="hinted")
# strain.wait_for_connection()
# load.wait_for_connection()


class LoadFrameDevice(Device):
    """Group these together."""

    strain = Component(
        EpicsMotor, "usxLAX:m58:c0:m1", kind="hinted"
    )  # extension, microns
    load = Component(EpicsSignalRO, "usxLAX:userCalc2.VAL", kind="hinted")  # force, N
    y = Component(EpicsMotor, "usxLAX:mxv:c0:m1", kind="hinted")  # mm
    x = Component(EpicsMotor, "usxLAX:m58:c0:m2", kind="hinted")  # mm


LoadFrame = LoadFrameDevice("", name="LoadFrame")
# automatically added to oregistry


def measureFrame(frame_x, frame_y, thickness, scan_title, NumOfScans, md={}):
    """
    Will run Frame from StrainStart to StrainEnd in StrainSteps, starin is in um
    frame_x and frame_y are specific motors controlling the frame position
    NOTE: make sure normal sx and sy can be in 0, 0 positions, they will be moved there if not there.
    Sample name will contain load read from frame.load

    final name: Samplename_250N_6min_XYZ.hdf where
        force is read at start of each measurement and
        time is reset after each starin is set

    reload by
    %run -im usaxs.user.loadFrame

    run as
                    RE(measureFrame(0, 0, 1,"Samplename", 4))
    would scan frame positioned at 0, 0 at all strains on listOfStrains
    Sample thickness is 1mm and "Samplename" is sample name.
    each sample will be measured
    """
    # this list MUST start from 0, you need to 0 styrain in epics before start
    # we assume in samply_Y correction that this list starts from 0 and is in um.
   
    ListOfStrains = [0, 110, 220, 330, 440, 550, 990, 1430, 1870, 2310, 2750, 3190, 3630]

    def setSampleName():
        return (
            f"{scan_title}"
            f"_{(LoadFrame.load.get()):.0f}N"
            f"_{(time.time()-t0)/60:.0f}min"
        )

    def collectAllThree(debug=False):
        if debug:
            # for testing purposes, set debug=True
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

    isDebugMode = False
    # isDebugMode = False

    if isDebugMode is not True:
        yield from before_command_list()  # this will run usual startup scripts for scans

    t0 = time.time()  # mark start time of data collection.

    # move sample in place, make sure we are at start strain
    yield from bps.mv(
        LoadFrame.x,
        -4,
        LoadFrame.y,
        frame_y,
    )
    yield from USAXSscan(0, 0, 1, "Blank", md={})
    yield from saxsExp(0, 0, 1, "Blank", md={})
    yield from waxsExp(0, 0, 1, "Blank", md={})

    # move sample in place, make sure we are at start strain
    yield from bps.mv(
        LoadFrame.x,
        frame_x,
        LoadFrame.y,
        frame_y,
    )
    # now do the loop.
    logger.info("Starting Frame collection")
    appendToMdFile("Starting Frame collection")

    for StrainPos in ListOfStrains:
        # first is move to vertically to correct for extension by half distance
        # sample is pulled up, so we need to go 1/2 distacne down and also, strain is in micron,
        #  LoadFrame.y, frame_y are in mm
        #  this should be what we need as change    frame_y-(StrainPos)/(2*1000)
        # basically, is we extend the sample by 1000um = 1mm (StrainPos), dividng by 2000 will give 0.5mm
        # and we need to move by 0.5mm down, so frame_y - 0.5
        yield from bps.mv(LoadFrame.y, frame_y - (StrainPos / (2 * 1000)))

        # move frame strain position, in example above, this extends the sample up by 1000um, 1mm up.
        yield from bps.mv(LoadFrame.strain, StrainPos)
        appendToMdFile(f"Moved to strain position {StrainPos} um")
        # reset time to know we started measurement at this strain. This is convenience information.
        t0 = time.time()
        # collect NumOfScans data sets, 2min each, 4 are about 8 minutes
        # this is to observe any relaxation at each strain.
        scanN = 0
        while scanN < NumOfScans:
            yield from collectAllThree(isDebugMode)
            scanN += 1

    logger.info("finished")  # record end.

    if isDebugMode is not True:
        yield from after_command_list()  # runs standard after scan scripts.

    # end of the measureFrame


# this will scan the strain (as motor position) and report load (as signal readback)
# if run as main (unlikely)
# def main():
#     # print(f"{strain.read()=} {load.read()=}")
#     RE(bp.scan([load], strain, 0.001, 0.010, 5))
#     print(f"{specwriter.spec_filename=}")

#     # Do it with the class object now
#     #RE(bp.scan([LoadFrame.load], LoadFrame.strain, 0.001, 0.010, 5))


# if __name__ == "__main__":
#     main()
