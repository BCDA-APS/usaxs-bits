"""Repair devices that guarneri left behind in ``unconnected_devices``.

Why this exists
---------------

``apsbits.core.instrument_init.make_devices`` calls
:meth:`guarneri.Instrument.connect`, which polls ``device.connected`` until a
deadline and then gives up.  Two things make that give-up permanent and
expensive:

* **ophyd needs more than a live channel.**
  ``EpicsSignalBase._ensure_connected`` only reports ``connected`` once the CA
  channel, the *access-rights callback* and the *first metadata* have all
  arrived.  Startup creates several hundred signals at once and, in ophyd's own
  words, "utility threads can get backed up in cases of PV connection storms".
  A signal whose metadata callback is dropped stays ``connected is False``
  forever even though ``caget`` on its PV answers instantly, and anything that
  calls ``Signal.read()`` on it — notably the baseline stream — then raises
  ``DisconnectedError``.

* **guarneri never retries in a way that fixes it.**
  Its poll loop only *reads* ``device.connected``; when the deadline expires it
  calls ``device.wait_for_connection(timeout=0)`` purely to harvest an error
  string.  ``timeout=0`` skips the ``get_all_metadata_blocking`` call that would
  have unstuck the signal.  The device stays in ``Instrument.unconnected_devices``
  and is re-polled — for the full timeout, and with the same traceback — on
  *every* later ``make_devices`` call, including ones for unrelated YAML files.

Observed 2026-10-25: ``user_data.scanning`` (``usxLAX:USAXS:scanning``) missed
the window during ``devices.yml``, then cost ~10 s and an identical
``NotConnectedError`` traceback on each of ``devices_aps_only.yml``,
``ad_devices.yml`` and ``autorange_devices.yml``.

What the sweep does
-------------------

:func:`sweep_unconnected_devices` walks the leftovers and calls
``wait_for_connection`` on each still-disconnected *signal* with a short,
nonzero timeout.  That takes the branch guarneri skips: ophyd fetches the
metadata synchronously in the calling thread, which both repairs the stuck flag
and costs only milliseconds when the channel is in fact up.  A genuinely absent
PV costs ``signal_timeout`` instead, so the whole sweep is capped by *budget* —
an IOC being down must not add minutes to startup.

Devices that come good are removed from ``unconnected_devices`` and
re-registered, so they stop poisoning later ``make_devices`` calls.  Devices
that do not are reported once, by PV, and left alone: the sweep repairs races,
it does not hide dead hardware.
"""

import logging
import time

logger = logging.getLogger(__name__)

__all__ = ["sweep_unconnected_devices"]

DEFAULT_SIGNAL_TIMEOUT = 2.0
"""Seconds to block per disconnected signal.  A live channel answers in ms;
this is really the price of giving up on a dead one."""

DEFAULT_BUDGET = 30.0
"""Ceiling on the whole sweep.  Keeps a dead IOC from stalling startup."""


def _disconnected_signals(device):
    """Return the signals of *device* that ophyd still reports as disconnected.

    Bare ``Signal`` objects (``ophyd.EpicsSignalRO`` entries in the device YAML)
    have no ``walk_signals``; treat such a device as its own single signal.
    Lazy components are skipped — they have no channel yet by design, and
    touching them here would create one.
    """
    if not hasattr(device, "walk_signals"):
        return [] if device.connected else [device]
    return [
        walk.item
        for walk in device.walk_signals(include_lazy=False)
        if not walk.item.connected
    ]


def sweep_unconnected_devices(
    instrument,
    signal_timeout: float = DEFAULT_SIGNAL_TIMEOUT,
    budget: float = DEFAULT_BUDGET,
) -> tuple[list, list]:
    """Give guarneri's leftover devices one blocking chance to connect.

    Parameters
    ----------
    instrument : guarneri.Instrument
        The device manager built by ``init_instrument("guarneri")``.
    signal_timeout : float
        Per-signal deadline handed to ``wait_for_connection``.  Must be > 0:
        that is the entire point of the sweep.
    budget : float
        Upper bound on the sweep's wall-clock time.  Devices not reached before
        the budget runs out are reported as unresolved, not as failures.

    Returns
    -------
    (repaired, still_unconnected)
        Lists of device objects.  Both are empty on a clean startup, which is
        the common case.
    """
    leftovers = list(getattr(instrument, "unconnected_devices", []))
    if not leftovers:
        return [], []

    logger.info(
        "Connection sweep: %d device(s) left unconnected by make_devices: %s",
        len(leftovers),
        ", ".join(sorted(dev.name for dev in leftovers)),
    )

    deadline = time.monotonic() + budget
    repaired, still_unconnected = [], []

    for device in leftovers:
        if time.monotonic() >= deadline:
            logger.warning(
                "Connection sweep: %.0f s budget spent; %s and any devices after "
                "it were not retried",
                budget,
                device.name,
            )
            still_unconnected.append(device)
            continue

        bad = []
        for signal in _disconnected_signals(device):
            try:
                # Nonzero timeout is what makes this different from guarneri's
                # own give-up call: ophyd fetches the metadata in this thread.
                signal.wait_for_connection(timeout=signal_timeout)
            except Exception as exc:  # TimeoutError, DestroyedError, ...
                bad.append((signal, exc))

        if bad:
            still_unconnected.append(device)
            for signal, exc in bad:
                logger.error(
                    "Connection sweep: %s (%s) did not connect: %s",
                    signal.name,
                    getattr(signal, "pvname", "no pvname"),
                    exc,
                )
            continue

        repaired.append(device)
        # Mirror what guarneri.Instrument.connect does for a device that makes
        # it: drop it from the retry list so later make_devices calls stop
        # paying the timeout, and re-register in case its name or labels moved.
        try:
            instrument.unconnected_devices.remove(device)
        except ValueError:  # pragma: no cover - already removed
            pass
        instrument.devices.register(device)
        logger.info(
            "Connection sweep: repaired %s (ophyd had not received its "
            "metadata/access-rights callbacks)",
            device.name,
        )

    if still_unconnected:
        logger.warning(
            "Connection sweep: %d device(s) still unconnected: %s",
            len(still_unconnected),
            ", ".join(sorted(dev.name for dev in still_unconnected)),
        )
    return repaired, still_unconnected
