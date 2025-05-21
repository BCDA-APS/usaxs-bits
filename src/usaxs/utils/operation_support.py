'''
This module provides functions to check if 12ID is in user operations mode
'''
from ophyd import EpicsSignalRO


def operations_in_12ide():
    """
    returns True if allowed to use BlueSky in 12ide
    """
    BlueSkyEnabled = EpicsSignalRO(
        "usxLAX:blCalc:userCalc2",
        name="BlueSkyEnable",
        auto_monitor=False,
    )
    # return diagnostics.PSS.b_station_enabled
    return BlueSkyEnabled
    # return False


