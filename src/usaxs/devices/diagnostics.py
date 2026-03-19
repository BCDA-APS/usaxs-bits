"""
PSS diagnostics and beam-in-hutch check for the 12-ID-E USAXS instrument.

``PSS_Parameters``
    Read-only EPICS PVs from the Personnel Safety System (PSS) for the A and C
    stations of sector 12-ID.
``DiagnosticsParameters``
    Composite device grouping the PSS sub-device with a swait-record that
    calculates the beam-in-hutch status.
"""

import apstools.synApps
from ophyd import Component
from ophyd import Device
from ophyd import EpicsSignalRO


class PSS_Parameters(Device):
    """Read-only PSS (Personnel Safety System) PVs for APS sector 12-ID.

    ``a_beam_active``
        True when the A-station (FE) beam is active.
    ``a_shutter_open_chain_A_led``
        Front-End shutter open status (chain A LED), sector 12-ID.
    ``e_beam_active``
        True when the C-station (experimental) has no-access interlock active.
    ``e_beam_ready``
        True when the C-station beam-ready PL is asserted.
    ``e_shutter_closed_chain_B``
        C-station secondary safety shutter closed (chain B).
    ``e_shutter_open_chain_A``
        Front-End shutter open (chain A) — same hardware signal as
        ``a_shutter_open_chain_A_led`` but named from the C-station perspective.
    """

    a_beam_active = Component(EpicsSignalRO, "PA:12ID:A_BEAM_ACTIVE.VAL", string=True)
    a_shutter_open_chain_A_led = Component(
        EpicsSignalRO, "PA:12ID:STA_A_FES_OPEN_PL", string=True
    )
    e_beam_active = Component(
        EpicsSignalRO, "PA:12ID:STA_C_NO_ACCESS.VAL", string=True
    )
    e_beam_ready = Component(
        EpicsSignalRO, "PA:12ID:STA_C_BEAMREADY_PL.VAL", string=True
    )
    e_shutter_closed_chain_B = Component(
        EpicsSignalRO, "PB:12ID:STA_C_SCS_CLSD_PL", string=True
    )
    e_shutter_open_chain_A = Component(
        EpicsSignalRO, "PA:12ID:STA_A_FES_OPEN_PL", string=True
    )

    @property
    def c_station_enabled(self) -> int:
        """Return 1 — C-station operations at 12-ID are always permitted.

        At 9-ID (former beamline) this checked interlock switches because
        hutches were arranged in series and only one could run at a time.
        At 12-ID both stations operate in parallel so no interlock check is
        needed; this property is kept for API compatibility and always returns 1.
        """
        return 1


class DiagnosticsParameters(Device):
    """Beam-line diagnostics grouping PSS status and beam-in-hutch check.

    ``beam_in_hutch_swait``
        A synApps swait record (``usxLAX:blCalc:userCalc1``) whose calculated
        value is non-zero when beam is present in the hutch.
    ``PSS``
        Nested :class:`PSS_Parameters` device exposing raw PSS PVs.
    """

    beam_in_hutch_swait = Component(
        apstools.synApps.SwaitRecord, "usxLAX:blCalc:userCalc1"
    )
    PSS = Component(PSS_Parameters)

    @property
    def beam_in_hutch(self):
        """Return the calculated beam-in-hutch value from the swait record."""
        return self.beam_in_hutch_swait.calculated_value.get()
