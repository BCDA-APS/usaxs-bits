"""
Ophyd device for APS Beamtime Scheduling System (BSS) PVs.

``BssEsafDevice``
    Components for the active ESAF (Experiment Safety Approval Form).

``BssProposalDevice``
    Components for the active proposal.

``BssDevice``
    Top-level device combining ESAF and proposal sub-devices.
    Register in ``devices.yml`` with ``labels: ["baseline"]`` so all
    fields are captured in the bluesky baseline stream at the start of
    every scan.

PVs are expected at the prefix ``usxTerms:bss:`` in the usxTerms IOC.
They are populated by ``usaxs.utils.setup_new_user.matchUserInApsBss()``.
"""

from ophyd import Component, Device, EpicsSignal

__all__ = ["BssDevice"]


class BssEsafDevice(Device):
    """EPICS PVs for the currently active ESAF.

    ``id``               — ESAF ID number (string).
    ``title``            — ESAF title (up to 255 chars).
    ``description``      — Full ESAF description (up to 2048 chars).
    ``sector``           — Sector string (e.g. "12").
    ``status``           — Status string (e.g. "Approved", "Pending").
    ``start``            — Start date-time string.
    ``end``              — End date-time string.
    ``user_count``       — Number of users on the ESAF.
    ``user_last_names``  — Comma-separated user last names.
    ``user_badges``      — Comma-separated user badge numbers.
    ``pi_name``          — PI full name (first last).
    """

    id = Component(EpicsSignal, "id", string=True)
    title = Component(EpicsSignal, "title", string=True)
    description = Component(EpicsSignal, "description", string=True)
    sector = Component(EpicsSignal, "sector", string=True)
    status = Component(EpicsSignal, "status", string=True)
    start = Component(EpicsSignal, "start", string=True)
    end = Component(EpicsSignal, "end", string=True)
    user_count = Component(EpicsSignal, "user_count")
    user_last_names = Component(EpicsSignal, "user_last_names", string=True)
    user_badges = Component(EpicsSignal, "user_badges", string=True)
    pi_name = Component(EpicsSignal, "pi_name", string=True)


class BssProposalDevice(Device):
    """EPICS PVs for the currently active proposal.

    ``id``               — Proposal ID (7-digit string).
    ``title``            — Proposal title (up to 255 chars).
    ``start``            — Start date-time string.
    ``end``              — End date-time string.
    ``duration``         — Duration in hours (float).
    ``mail_in``          — Mail-in flag (0=No, 1=Yes).
    ``proprietary``      — Proprietary flag (0=No, 1=Yes).
    ``user_count``       — Number of users on the proposal.
    ``user_last_names``  — Comma-separated user last names.
    ``user_badges``      — Comma-separated user badge numbers.
    ``pi_name``          — PI full name (first last).
    """

    id = Component(EpicsSignal, "id", string=True)
    title = Component(EpicsSignal, "title", string=True)
    start = Component(EpicsSignal, "start", string=True)
    end = Component(EpicsSignal, "end", string=True)
    duration = Component(EpicsSignal, "duration")
    mail_in = Component(EpicsSignal, "mail_in")
    proprietary = Component(EpicsSignal, "proprietary")
    user_count = Component(EpicsSignal, "user_count")
    user_last_names = Component(EpicsSignal, "user_last_names", string=True)
    user_badges = Component(EpicsSignal, "user_badges", string=True)
    pi_name = Component(EpicsSignal, "pi_name", string=True)


class BssDevice(Device):
    """Top-level BSS device combining ESAF and proposal sub-devices.

    Register in ``devices.yml`` with prefix ``usxTerms:bss:`` and
    ``labels: ["baseline"]``.  Bluesky then reads all components into
    the baseline stream at the start of every scan.

    Baseline stream signal names use ``_`` as separator, so
    ``bss.esaf.id`` becomes ``bss_esaf_id`` in the stream.
    """

    esaf = Component(BssEsafDevice, "esaf:")
    proposal = Component(BssProposalDevice, "proposal:")
