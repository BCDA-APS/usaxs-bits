"""Support the scaler devices."""

from ..startup import oregistry


def setup_scalers():
    """Make specific scaler channels available."""
    scaler0 = oregistry["scaler0"]  # See scalers.yml

    channels = {
        "I0": scaler0.channels.chan02,
        "I00": scaler0.channels.chan03,
        "UPD": scaler0.channels.chan04,
        "TRD": scaler0.channels.chan05,
        "I000": scaler0.channels.chan06,
    }
    for key, channel in channels.items():
        channel.name = f"{key}_SIGNAL"  # ... UPD_SIGNAL ...
        oregistry.register(channel)
        channel.s.name = key
        oregistry.register(channel.s)  # ... UPD ...
