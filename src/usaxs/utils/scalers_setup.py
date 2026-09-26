"""Support the scaler devices.

Called once during instrument startup to configure ``scaler0``.

Historically this also claimed the detector names ``I0``, ``I00``, ``UPD``,
``TRD`` and ``I000`` in the ``oregistry`` and the console namespace, pointing
them at scaler channels.  Those names now belong to the FX4 electrometers
(:mod:`usaxs.utils.fx4_channels`), so ``startup.py`` passes
``claim_detector_names=False`` and this module only configures the scaler.

``scaler0`` and ``scaler1`` are still declared so that reverting to the Femto /
V-F / scaler counting chain is an uncomment in ``autorange_devices.yml`` plus
``claim_detector_names=True`` here, rather than a device-configuration change.
Nothing feeds their detector channels once the diodes are wired to the FX4.
"""

import logging
import sys

logger = logging.getLogger(__name__)


def release_scaler_detector_names():
    """Rename scaler channels that collide with an already-registered device.

    ``ScalerCH.select_channels`` calls ``match_names``, which renames every
    channel signal from the scaler's EPICS ``.NM`` records.  Those records
    still read ``I0``, ``I00``, ``UPD`` and ``TRD`` at 12-ID-E, so the scaler
    channels take names the FX4 electrometers own and ``oregistry["UPD"]``
    then raises ``MultipleComponentsFound``.

    Rather than hard-code the FX4 name list, rename only where a *real*
    conflict exists, suffixing with ``_scaler``.  Re-registering moves the
    signal to the new key: ``Registry.register`` drops a component from any
    stale name bucket before adding it under its current name.

    Changing the ``.NM`` records in EPICS would fix this too, but they are
    shared with the MEDM screens and the Femto-era rollback path, so the
    rename is kept on the ophyd side.

    .. important::
       Call this **after** :func:`usaxs.utils.fx4_channels.setup_fx4_channels`,
       which is what gives the FX4 signals those names.  Called any earlier --
       for example from :func:`setup_scalers`, which runs before
       ``autorange_devices.yml`` -- there is no conflict yet and this is a
       no-op.
    """
    from apsbits.core.instrument_init import oregistry

    scaler = oregistry["scaler0"]
    renamed = []
    for attr in scaler.channels.component_names:
        signal = getattr(scaler.channels, attr).s
        name = signal.name
        if not name:
            continue
        others = [
            dev
            for dev in oregistry.findall(name=name, allow_none=True)
            if dev is not signal
        ]
        if not others:
            continue
        signal.name = f"{name}_scaler"
        oregistry.register(signal)
        renamed.append(f"{name} -> {signal.name}")

    if renamed:
        logger.info(
            "scaler0: renamed channels that collide with FX4 detector names"
            " (%s)",
            ", ".join(renamed),
        )


def setup_scalers(claim_detector_names=False):
    """Configure ``scaler0``, and optionally claim the detector names.

    Parameters
    ----------
    claim_detector_names : bool
        When True, register the scaler channels as ``I0``, ``I00``, ``UPD``,
        ``TRD`` and ``I000`` (plus the ``*_SIGNAL`` channel objects), as the
        Femto-era counting chain required.  Leave False while the FX4 owns
        those names -- registering both would collide, and the scaler channels
        read nothing once the diodes are rewired.
    """
    from apsbits.core.instrument_init import oregistry

    main_namespace = sys.modules["__main__"]  # "console"
    scaler0 = oregistry["scaler0"]  # See scalers.yml

    scaler0.stage_sigs["count_mode"] = "OneShot"
    # scaler0.wait_for_connection()
    scaler0.select_channels()

    if not claim_detector_names:
        # The FX4 has not claimed its names yet at this point in startup --
        # release_scaler_detector_names() runs after setup_fx4_channels().
        logger.debug(
            "scaler0 configured; detector names left to the FX4"
            " (see usaxs.utils.fx4_channels)"
        )
        return

    channels = {
        "I0": scaler0.channels.chan02,
        "I00": scaler0.channels.chan03,
        "UPD": scaler0.channels.chan04,
        "TRD": scaler0.channels.chan05,
    }
    for key, channel in channels.items():
        channel.s.name = key  # channel counts
        oregistry.register(channel.s)  # ... UPD ...
        setattr(main_namespace, key, channel.s)
        # item=oregistry[key]
        # item._ophyd_labels_ = set(["channel", "counter",])
        # item._auto_monitor = False

        label = f"{key}_SIGNAL"
        channel.name = label  # ... UPD_SIGNAL ...
        oregistry.register(channel)
        setattr(main_namespace, label, channel)
