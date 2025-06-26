'''
This is for load frame from sector 1, the device has two controls - 
motor to extend the sample (strain) and calculation to report the stress

'''
# import needed stuff

from apstools.callbacks import SpecWriterCallback2
from bluesky import RunEngine, plans as bp, plan_stubs as bps
from bluesky.callbacks.best_effort import BestEffortCallback
from ophyd import Component, Device, EpicsSignal, EpicsMotor, EpicsSignalRO

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
    strain = Component(EpicsMotor, "usxLAX:m58:c2:m1", kind="hinted")
    load = Component(EpicsSignalRO, "usxLAX:userCalc2.VAL", kind="hinted")


LoadFrame = LoadFrameDevice("", name="LoadFrame")
# add to oregistry? 

def CalibrateLoadFrame(StrainStart, StrainEnd, StrainStep):
    """
    This function is used to calibrate the load frame.
    It will move the strain motor to 0 and read the load.
    It will then scan the strain motor from StrainStart to StrainEnd
    with a step size of StrainStep, and report the load at each step.
    Then it reports name of spec file in hwich user can find the data. 
    """
    # Move the strain motor to a known position
    strain.move(0.0)
    # Wait for the move to complete
    strain.wait()
    # Read the load value
    load_value = load.get()
    print(f"Load at 0.0 strain: {load_value}")
    RE(bp.scan([LoadFrame.load], LoadFrame.strain, StrainStart, StrainEnd, StrainStep))
    print(f"{specwriter.spec_filename=}")


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
