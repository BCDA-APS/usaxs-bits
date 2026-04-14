"""
Check whether the 12-ID-E station is in user operations mode.

The operations flag is read from a userCalc EPICS PV that is set by beamline
staff via the PSS/operations interlock chain.
"""

from ophyd import EpicsSignalRO


def operations_in_12ide():
    """Return an EpicsSignalRO connected to the 12-ID-E BlueSky-enable PV.

    The PV ``usxLAX:blCalc:userCalc2`` is non-zero when Bluesky operation is
    permitted at 12-ID-E.

    NOTE: This function creates a *new* Channel Access connection on every call
    and returns the signal *object* (not its value).  Callers must call
    ``.get()`` on the returned signal to retrieve the boolean-like value.
    Consider calling this once at startup and caching the result, or replacing
    with a module-level signal — see open issue.

    Returns
    -------
    EpicsSignalRO
        Connected to ``usxLAX:blCalc:userCalc2``.
    """
    BlueSkyEnabled = EpicsSignalRO(
        "usxLAX:blCalc:userCalc2",
        name="BlueSkyEnable",
        auto_monitor=False,
    )
    # return diagnostics.PSS.b_station_enabled
    return BlueSkyEnabled
