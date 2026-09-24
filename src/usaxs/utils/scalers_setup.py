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
