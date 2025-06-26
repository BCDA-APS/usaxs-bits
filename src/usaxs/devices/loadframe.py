'''
Sector 1 loadframe (small Instron) for USAXS
'''


from ophyd import EpicsSignalRO
from ophyd import EpicsMotor
from ophyd import Component
from ophyd import Device



# define device. Only motor position and readback on strain needed.
class LoadFrameDevice(Device):
     extension = Component(EpicsMotor, "usxLAX:m58:c2:m1", kind="hinted")
     strain= Component(EpicsSignalRO, "usxLAX:userCalc2.VAL", kind="hinted")


# create the Python object:
#loadFrame = loadFrameDevice("", name="loadFrame")
