'''
Sector 1 loadframe (small Instron) for USAXS
'''


from ophyd import EpicsSignalRO
from ophyd import EpicsMotor
from ophyd import Component
from ophyd import Device



# define device. Only motor position and readback on strain needed.
class loadFrameDevice(Device):
    Extension = Component(EpicsMotor, "usxLAX:m58:c2:m1")
    StrainRBV = Component(EpicsSignalRO, "usxLAX:userCalc2.VAL")



# create the Python object:
#loadFrame = loadFrameDevice("", name="loadFrame")
