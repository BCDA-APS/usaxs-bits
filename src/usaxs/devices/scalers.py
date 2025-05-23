"""Support the scaler devices."""

import sys

from ..startup import oregistry


def setup_scalers():
    """Make specific scaler channels available in oregistry & console."""
    main_namespace = sys.modules["__main__"]  # "console"
    scaler0 = oregistry["scaler0"]  # See scalers.yml

    channels = {
        "I0": scaler0.channels.chan02,
        "I00": scaler0.channels.chan03,
        "UPD": scaler0.channels.chan04,
        "TRD": scaler0.channels.chan05,
        "I000": scaler0.channels.chan06,
    }
    for key, channel in channels.items():
        channel.s.name = key  # channel counts
        oregistry.register(channel.s)  # ... UPD ...
        setattr(main_namespace, key, channel.s)

        label = f"{key}_SIGNAL"
        channel.name = label  # ... UPD_SIGNAL ...
        oregistry.register(channel)
        setattr(main_namespace, label, channel)
