
"""
scaler
"""

__all__ = """
    scaler0
    scaler1
    clock  I0  I00  upd2  trd  I000
    scaler2_I000_counts
    scaler2_I000_cps

    I0_SIGNAL
    I00_SIGNAL
    UPD_SIGNAL
    TRD_SIGNAL
    """.split()

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

from apstools.devices import use_EPICS_scaler_channels
from ophyd import Component, EpicsSignal, EpicsScaler, EpicsSignalRO
from ophyd.scaler import ScalerCH

# TODO : watch for use of display_rate in plans, repalce with update_rate]
#class myScalerCH(ScalerCH): - use ScalerCH
#    display_rate = Component(EpicsSignal, ".RATE", kind="omitted")
# now called update_rate 

scaler0 = ScalerCH('usxLAX:vsc:c0', name='scaler0')
scaler0.stage_sigs["count_mode"] = "OneShot"
scaler1 = ScalerCH('usxLAX:vsc:c1', name='scaler1')     # used by softGlue for SAXS transmission
# scaler2 = ScalerCH('9idcLAX:vsc:c2', name='scaler2')     # used by upstream feedback
scaler2_I000_counts = EpicsSignalRO("usxLAX:vsc:c2.S2", name="scaler2_I000_counts")
scaler2_I000_cps = EpicsSignalRO("usxLAX:vsc:c2_cts1.B", name="scaler2_I000_counts")

scaler0.select_channels()
scaler1.select_channels()

I0_SIGNAL = scaler0.channels.chan02
I00_SIGNAL = scaler0.channels.chan03
UPD_SIGNAL = scaler0.channels.chan04
TRD_SIGNAL = scaler0.channels.chan05

clock = scaler0.channels.chan01.s
I0 = scaler0.channels.chan02.s
I00 = scaler0.channels.chan03.s
upd2 = scaler0.channels.chan04.s
trd = scaler0.channels.chan05.s
I000 = scaler0.channels.chan06.s

for item in (clock, I0, I00, upd2, trd, I000):
    item._ophyd_labels_ = set(["channel", "counter",])
    item._auto_monitor = False

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

"""
REFERENCE

usaxs@usaxscontrol ~/.../startup/spec $ caget usxLAX:vsc:c{0,1,2}.NM{1,2,3,4,5,6,7,8}
usxLAX:vsc:c0.NM1              seconds
usxLAX:vsc:c0.NM2              I0_USAXS
usxLAX:vsc:c0.NM3              I00_USAXS
usxLAX:vsc:c0.NM4              PD_USAXS
usxLAX:vsc:c0.NM5              TR diode
usxLAX:vsc:c0.NM6              I000
usxLAX:vsc:c0.NM7              
usxLAX:vsc:c0.NM8              
usxLAX:vsc:c1.NM1              10MHz_ref
usxLAX:vsc:c1.NM2              I0
usxLAX:vsc:c1.NM3              TR diode
usxLAX:vsc:c1.NM4              
usxLAX:vsc:c1.NM5              
usxLAX:vsc:c1.NM6              
usxLAX:vsc:c1.NM7              
usxLAX:vsc:c1.NM8              
usxLAX:vsc:c2.NM1              time
usxLAX:vsc:c2.NM2              I000
usxLAX:vsc:c2.NM3              
usxLAX:vsc:c2.NM4              
usxLAX:vsc:c2.NM5              
usxLAX:vsc:c2.NM6              
usxLAX:vsc:c2.NM7              
usxLAX:vsc:c2.NM8              
"""
