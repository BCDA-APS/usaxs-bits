"""
Expose FX4 detector channels under their USAXS names.

The FX4 counterpart of :mod:`usaxs.utils.scalers_setup`.  That module used to
register the scaler channels as ``UPD``, ``I0``, ``I00``, ``TRD`` and
``I000``; this one claims the same names for the FX4 ``MeanValue`` signals, so
that BestEffortCallback hints, the ``_md["hints"]`` dimensions in ``uascan``,
the NeXus stream keys and the queue-monitor plot configuration
(``usaxs-qmonitor/usaxs_qmonitor/settings.py``) all keep working untouched.

What changes under those stable names is the **unit**: counts per second
becomes picoamps.  Every run therefore carries ``counting_chain = "FX4"`` in
its metadata, and the saved files repeat it, so nothing has to infer the unit
from context.

The two modules cannot both claim the names.  ``startup.py`` calls
``setup_scalers(claim_detector_names=False)`` for that reason.

There is deliberately no ``<NAME>_SIGNAL`` here.  Those were ``ScalerChannel``
objects whose ``.chname`` PV held the channel's label; the FX4 has no such
indirection, so plans that used ``UPD_SIGNAL.chname.get()`` now pass the plain
string ``"UPD"``.
"""

import logging
import sys

logger = logging.getLogger(__name__)


def _find_fx4_controls(oregistry):
    """Return every ``FX4DetectorControls`` the registry knows about.

    Prefers the ``fx4_detector`` label from ``autorange_devices.yml`` and falls
    back to scanning the registry by type, so a registry without label support
    still works.

    Parameters
    ----------
    oregistry : object
        The apsbits/ophyd device registry.

    Returns
    -------
    list
        The detector-control devices, possibly empty.
    """
    from ..devices.fx4_quadem import FX4DetectorControls

    try:
        found = oregistry.findall(label="fx4_detector", allow_none=True) or []
    except Exception:  # noqa: BLE001 - registry API varies; the scan below is the fallback
        found = []
    controls = [d for d in found if isinstance(d, FX4DetectorControls)]
    if controls:
        return controls

    logger.debug("no 'fx4_detector' label found; scanning the registry by type")
    for attr in ("all_devices", "device_names"):
        try:
            candidates = list(getattr(oregistry, attr))
        except Exception:  # noqa: BLE001
            continue
        resolved = [oregistry[c] if isinstance(c, str) else c for c in candidates]
        controls = [d for d in resolved if isinstance(d, FX4DetectorControls)]
        if controls:
            return controls
    return []


def setup_fx4_channels():
    """Name, register and console-expose the FX4 detector channels.

    For each ``FX4DetectorControls`` in the registry, renames its channel's
    ``MeanValue`` signal to the detector nickname (``UPD``, ``I0``, ...),
    registers it, and binds it in the interactive namespace.

    Channels with no detector on them are set to ``omitted`` so they do not
    appear in reads.  Named channels are set to ``normal``: read and tabulated,
    but not plotted.  Nothing is ``hinted`` -- use :func:`select_fx4_plot` to
    choose what a given scan plots, the way ``scaler0.select_channels([...])``
    used to.

    Returns
    -------
    dict
        ``{nickname: signal}`` for everything that was named.

    Raises
    ------
    RuntimeError
        If no FX4 detector controls are registered, which means
        ``autorange_devices.yml`` was not loaded.
    """
    from apsbits.core.instrument_init import oregistry

    main_namespace = sys.modules["__main__"]  # "console"
    controls = _find_fx4_controls(oregistry)
    if not controls:
        raise RuntimeError(
            "no FX4DetectorControls registered -- was autorange_devices.yml"
            " loaded before setup_fx4_channels()?"
        )

    # Start from "nothing is read": QuadFX4._post_connect_setup hints all four
    # channels of every box, which would put eight traces on a tune plot.
    for controls_device in controls:
        for channel in (1, 2, 3, 4):
            controls_device.quadem.channel_stats(channel).mean_value.kind = "omitted"

    named = {}
    for controls_device in controls:
        nickname = controls_device.nickname
        signal = controls_device.signal
        signal.name = nickname
        signal.kind = "normal"
        oregistry.register(signal)
        setattr(main_namespace, nickname, signal)
        named[nickname] = signal
        logger.debug(
            "%s = %s channel %d (%s)",
            nickname,
            controls_device.quadem.name,
            controls_device.channel_number,
            "autoranged" if controls_device.autoranged else "fixed range",
        )

    logger.info("FX4 detector channels: %s", ", ".join(sorted(named)))
    return named


def select_fx4_plot(names=None):
    """Choose which FX4 detectors BestEffortCallback plots.

    The FX4 replacement for ``scaler0.select_channels([...])``.  Named
    detectors not in *names* stay ``normal`` -- still read, still in the
    LiveTable -- so this only controls which signals get their own plot axes.

    Parameters
    ----------
    names : iterable of str or None
        Detector nicknames to plot, e.g. ``["UPD"]``.  ``None`` or an empty
        iterable plots none of them, which is what a plan wants when it is
        plotting something else entirely.

    Returns
    -------
    list of str
        The nicknames that were hinted.
    """
    from apsbits.core.instrument_init import oregistry

    wanted = set(names or ())
    hinted = []
    for controls_device in _find_fx4_controls(oregistry):
        nickname = controls_device.nickname
        if nickname in wanted:
            controls_device.signal.kind = "hinted"
            hinted.append(nickname)
        else:
            controls_device.signal.kind = "normal"

    missing = wanted - set(hinted)
    if missing:
        logger.warning(
            "select_fx4_plot: no FX4 detector named %s", ", ".join(sorted(missing))
        )
    return hinted
