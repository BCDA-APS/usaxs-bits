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
from usaxs.plans.command_list import after_command_list
from usaxs.plans.command_list import before_command_list
from ophyd import Signal


# define what we need to use
RE = RunEngine()
bec = BestEffortCallback()
RE.subscribe(bec)
specwriter = SpecWriterCallback2()
RE.subscribe(specwriter.receiver)

# # this is using simply adding strain and load as EpicsMotor and EpicsSignal
# strain = EpicsMotor("usxLAX:m58:c2:m1", name="strain", kind="hinted")
# load = EpicsSignal("usxLAX:userCalc2.VAL", name="load", kind="hinted")
# strain.wait_for_connection()
# load.wait_for_connection()


class LoadFrameDevice(Device):
    """Group these together."""

    strain = Component(EpicsMotor, "usxLAX:m58:c0:m1", kind="hinted")   #extension, microns
    load = Component(EpicsSignalRO, "usxLAX:userCalc2.VAL", kind="hinted")  #force, N
    y = Component(EpicsMotor, "usxLAX:mxv:c0:m1", kind="hinted")     #mm
    x = Component(EpicsMotor, "usxLAX:mxv:c0:m2", kind="hinted")     #mm


LoadFrame = LoadFrameDevice("", name="LoadFrame")
# automatically added to oregistry


def CalibrateLoadFrame(StrainStart, StrainEnd, StrainStep):
    """
    This function is used to calibrate the load frame.
    run this as function, not as bluesky plan. Therefore 
    DONOT! run this as RE(CalbrateLoadFrame(0,100,20)), 
    but simply as CalibrateLoadFrame(0,100,20)

    It will move the strain motor to 0 and read the load.
    It will then scan the strain motor from StrainStart to StrainEnd
    with a step size of StrainStep, and report the load at each step.
    Then it reports name of spec file in which user can find the data.
    """
    # Move the strain motor to a known position
    LoadFrame.strain.move(0.0)
    #yield from bps.mv(LoadFrame.strain,0)
    # Wait for the move to complete
    #LoadFrame.strain.wait() - this does not excist. ABove command waits oon its own. 
    # Read the load value
    load_value = LoadFrame.load.get()
    print(f"Load at 0.0 strain: {load_value}")
    RE(bp.scan([LoadFrame.load], LoadFrame.strain, StrainStart, StrainEnd, StrainStep))
    print(f"{specwriter.spec_filename=}")



def measureFrame(frame_x, frame_y, thickness, scan_title, StrainStart, StrainEnd, StrainStep, md={}):
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
    RE(measureFrame(0, 0, 1,"Samplename", 0, 100, 20))
    would scan frame positioned at 0,0 from 0 to 100 um strain at 20 steps 
    Sample thickness is 1mm and "Samplename" is sample name. 
    """

    def setSampleName():
        return f"{scan_title}" f"_{(LoadFrame.load):.0f}N" f"_{(time.time()-t0)/60:.0f}min"

    def collectAllThree(debug=False):
        if debug:
            # for testing purposes, set debug=True
            print(sampleMod)
            yield from bps.sleep(20)
        else:
            sampleMod = setSampleName()
            md["title"] = sampleMod
            yield from USAXSscan(0, 0, thickness, sampleMod, md={})
            sampleMod = setSampleName()
            md["title"]=sampleMod
            yield from saxsExp(0, 0, thickness, sampleMod, md={})
            sampleMod = setSampleName()
            md["title"]=sampleMod
            yield from waxsExp(0, 0, thickness, sampleMod, md={})

    isDebugMode = False
    # isDebugMode = False

    if isDebugMode is not True:
        yield from before_command_list()  # this will run usual startup scripts for scans

    t0 = time.time()  # mark start time of data collection.

    #move sample in place, make sure we are at start strain
    yield from bps.mv(LoadFrame.x, frame_x,
                      LoadFrame.y, frame_y,
                      LoadFrame.strain, StrainStart,
                      )
    #now do the loop. 
    logger.info("Starting Frame collection")

    for StrainPos in range (StrainStart, StrainEnd, StrainStep):

        # first is move to vertically to correct for extension by half distance 
        # sample is pulled up, so we need to go 1/2 distacne down and also, strain is in micron, 
        #  LoadFrame.y, frame_y are in mm  
        #  this should be what we need as change    frame_y-(StrainPos-StrainStart)/(2*1000)     
        # basically, is we extend the sample by 1000um = 1mm (StrainPos-StrainStart), dividng by 2000 will give 0.5mm
        # and we need to mvoe by 0.5mm down, so frame_y - 0.5 
        yield from bps.mv(LoadFrame.y, frame_y-((StrainPos-StrainStart)/(2*1000)))
        
        # move frame strain position, in example above, this extends the sample up by 1000um, 1mm up.         
        yield from bps.mv(LoadFrame.strain, StrainPos)
        # reset time to know we started measurement at this strain. This is convenience information. 
        t0 = time.time() 
        # collect 4 data sets = about 8 minutes
        # this is to observe any relaxation at each strain. 
        yield from collectAllThree(isDebugMode)
        yield from collectAllThree(isDebugMode)
        yield from collectAllThree(isDebugMode)
        yield from collectAllThree(isDebugMode)

    logger.info("finished")  # record end.

    if isDebugMode is not True:
        yield from after_command_list()  # runs standard after scan scripts.
    
    #end of the measureFrame



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
