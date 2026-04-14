"""Amplifier autoscale and background-measurement plans for USAXS detectors.

This module provides Bluesky plans that drive the Femto current-amplifier
autorange sequence programs.  The main public entry points are:

* ``autoscale_amplifiers`` — iterate each amplifier's gain until the scaler
  count rate is within the acceptable window (``min_count_rate`` to
  ``max_count_rate``).
* ``measure_background`` — sweep every gain setting and record the dark
  current at each one for later baseline subtraction.

Both plans delegate per-scaler work to internal helpers
(``_scaler_autoscale_`` and ``_scaler_background_measurement_``) so that
multiple detectors sharing the same scaler are handled as a group.

Supporting utilities
--------------------
* ``group_controls_by_scaler`` — partition a flat list of
  ``DetectorAmplifierAutorangeDevice`` objects by their common scaler.
* ``OrderedDefaultDict`` — ``defaultdict`` variant that preserves insertion
  order (used to track the last known gain per channel across calls).
* ``_gain_to_str_`` — format an integer gain index as ``"10^n"`` for logging.
* ``UPDRange`` — thin wrapper that reads the current UPD autorange gain index.

Stubs (not yet implemented)
---------------------------
* ``setup_amplifier_count_time``
* ``setup_amplifier_auto_background``
"""

import logging
from collections import OrderedDict
from typing import Optional

import numpy as np

# Get devices from oregistry
from apsbits.core.instrument_init import oregistry

from bluesky import RunEngine
from bluesky import plan_stubs as bps
from bluesky.utils import plan
from ophyd.scaler import ScalerChannel
from ophyd.signal import EpicsSignalRO

from ..devices.amplifiers import AMPLIFIER_MINIMUM_SETTLING_TIME
from ..devices.amplifiers import NUM_AUTORANGE_GAINS
from ..devices.amplifiers import AutorangeSettings
from ..devices.amplifiers import AutoscaleError
from ..devices.amplifiers import DetectorAmplifierAutorangeDevice

# ---------------------------------------------------------------------------
# Module-level device instances.
# NOTE: Many of these (I0, I00, I000, I0_controls, I00_controls, a_stage,
# d_stage, m_stage, monochromator, s_stage, scaler0, terms, usaxs_shutter,
# trd_controls) are loaded here but not referenced by any function in this
# file.  They may be legacy from a prior version or expected to be imported
# by other modules via ``from amplifiers_plan import <device>``.
# ---------------------------------------------------------------------------
I0 = oregistry["I0"]
I00 = oregistry["I00"]
I000 = oregistry["I000"]
I0_controls = oregistry["I0_controls"]
I00_controls = oregistry["I00_controls"]
a_stage = oregistry["a_stage"]
d_stage = oregistry["d_stage"]
m_stage = oregistry["m_stage"]
monochromator = oregistry["monochromator"]
s_stage = oregistry["s_stage"]
scaler0 = oregistry["scaler0"]
terms = oregistry["terms"]
upd_controls = oregistry["upd_controls"]   # used by UPDRange()
usaxs_shutter = oregistry["usaxs_shutter"]
trd_controls = oregistry["trd_controls"]

logger = logging.getLogger(__name__)


def setup_amplifier_count_time():
    """Set up the count time for the amplifier.

    This function configures the count time settings for the amplifier
    and ensures proper synchronization with the scaler.
    """
    raise NotImplementedError("TODO")


def setup_amplifier_auto_background():
    """Set up automatic background measurement for the amplifier.

    This function configures the amplifier for automatic background
    measurement and updates the necessary parameters.
    """
    raise NotImplementedError("TODO")


@plan
def autoscale_amplifiers(controls: list[DetectorAmplifierAutorangeDevice], shutter=None, count_time: float = 0.05, max_iterations: int = 9, RE: Optional[RunEngine] = None):
    """Bluesky plan: autoscale detector amplifiers simultaneously.

    Groups the supplied controls by scaler (so devices sharing hardware are
    handled together), then calls ``_scaler_autoscale_`` for each group in
    sequence.  Autoscale errors are caught and logged as warnings rather than
    aborting the scan so that a single bad channel does not block the others.

    Parameters
    ----------
    controls : list[DetectorAmplifierAutorangeDevice]
        List (or tuple) of amplifier control devices to autoscale.
    shutter : optional
        If supplied, opened before autoscaling begins (left open afterwards).
    count_time : float
        Integration time per trial count, seconds.  Default 0.05.
    max_iterations : int
        Maximum gain-adjustment cycles before giving up.  Default 9.
    RE : RunEngine, optional
        RunEngine instance; passed through to ``_scaler_autoscale_`` where it
        is used to suppress the ``AutoscaleError`` raise during dry-runs
        (``summarize_plan``).

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """

    assert isinstance(controls, (tuple, list)), "controls must be a list"
    scaler_dict = group_controls_by_scaler(controls)

    if shutter is not None:
        yield from bps.mv(shutter, "open")

    for control_list in scaler_dict.values():
        # Process each scaler group sequentially in case the same physical
        # hardware appears more than once in the controls list.
        if len(control_list) > 0:
            try:
                yield from _scaler_autoscale_(
                    control_list,
                    count_time=count_time,
                    max_iterations=max_iterations,
                    RE=RE,
                )
            except AutoscaleError as exc:
                # Gain convergence failed — warn and continue, do not abort.
                logger.warning(
                    "%s: %s - will continue despite warning",
                    control_list[0].nickname,
                    exc,
                )
            except Exception as exc:
                logger.error(
                    "%s: %s - will continue anyway",
                    control_list[0].nickname,
                    exc,
                )


@plan
def _scaler_autoscale_(controls: list[DetectorAmplifierAutorangeDevice], count_time: float = 0.05, max_iterations: int = 9, RE: Optional[RunEngine] = None):
    """Plan (internal): autoscale amplifiers for signals sharing a common scaler.

    Algorithm
    ---------
    1. Save and override scaler timing settings (preset_time, delay, count_mode).
    2. Set all controls to ``automatic`` gain mode, seeding from the last known
       good gain to reduce convergence time.
    3. Repeatedly trigger the scaler and check whether any gains changed AND
       whether all count rates fall within [min_count_rate, max_count_rate].
    4. Once all convergence flags are True, switch controls back to ``manual``
       mode and restore the scaler settings.
    5. If the loop exhausts ``max_iterations`` without converging and the APS
       is in user-operations mode, raise ``AutoscaleError``.

    The ``_last_autorange_gain_`` module-level dict persists the last known gain
    between calls so successive autoscales converge faster.

    Parameters
    ----------
    controls : list[DetectorAmplifierAutorangeDevice]
        All controls must share the same scaler (``controls[0].scaler``).
    count_time : float
        Scaler integration time per trial count, seconds.
    max_iterations : int
        Maximum gain-adjustment loop iterations.
    RE : RunEngine, optional
        Used at the end to suppress ``AutoscaleError`` during ``summarize_plan``
        (when RE.state == "idle").

    Yields
    ------
    Bluesky messages consumed by the RunEngine.

    Raises
    ------
    AutoscaleError
        If convergence fails during live user operations.
    RuntimeError
        If signal type is ``EpicsSignalRO`` (divide-by-time path not implemented).
    ValueError
        If ``control.signal`` is an unexpected type.
    """

    aps = oregistry["aps"]
    global _last_autorange_gain_   # accesses module-level OrderedDefaultDict; global is not strictly needed since we only mutate, not rebind — but kept for clarity

    scaler = controls[0].scaler
    originals = {}

    # Save current scaler configuration so it can be restored afterwards.
    originals["preset_time"] = scaler.preset_time.get()
    originals["delay"] = scaler.delay.get()
    originals["count_mode"] = scaler.count_mode.get()
    yield from bps.mv(
        scaler.preset_time,
        count_time,
        scaler.delay,
        0.02,  # this was 0.2 seconds, which is VERY slow.
        scaler.count_mode,
        "OneShot",
    )

    last_gain_dict = _last_autorange_gain_[scaler.name]

    # ------------------------------------------------------------------
    # Seed each amplifier from the previously converged gain so the loop
    # starts close to the correct value, then record the starting gain.
    # ------------------------------------------------------------------
    settling_time = AMPLIFIER_MINIMUM_SETTLING_TIME
    for control in controls:
        yield from bps.mv(control.auto.mode, AutorangeSettings.automatic)
        # faster if we start from last known autoscale gain
        gain = last_gain_dict.get(control.auto.gain.name)
        if gain is not None:  # be cautious, might be unknown
            yield from control.auto.setGain(gain)
        last_gain_dict[control.auto.gain.name] = control.auto.gain.get()
        settling_time = max(settling_time, control.femto.settling_time.get())

    yield from bps.sleep(settling_time)

    # ------------------------------------------------------------------
    # Convergence loop.
    # ``converged`` is rebuilt each iteration and must be all-True to exit.
    # Convergence requires:
    #   (a) no gain changed since the last iteration, AND
    #   (b) actual count rate <= max_count_rate (not saturated), AND
    #   (c) if the gain *did* change, actual rate >= min_count_rate (not too low).
    # ------------------------------------------------------------------
    # Autoscale has converged if no gains change
    # Also, make sure no detector count rates are stuck at max
    complete = False
    for _ in range(max_iterations):
        converged = []  # append True is convergence criteria is satisfied
        yield from bps.trigger(scaler, wait=True)  # timeout=count_time+1.0)
        # amplifier sequence program (in IOC) will adjust the gain now
        yield from bps.sleep(settling_time)
        # check if any gains changed
        for control in controls:
            # any gains changed?
            gain_now = control.auto.gain.get()
            gain_previous = last_gain_dict[control.auto.gain.name]
            converged.append(gain_now == gain_previous)
            changed = gain_now != gain_previous
            last_gain_dict[control.auto.gain.name] = gain_now

            # are we topped up on any detector?
            # also, if we changed are we still too low?
            # This helps increase gain if needed.
            max_rate = control.auto.max_count_rate.get()
            min_rate = control.auto.min_count_rate.get()
            if isinstance(control.signal, ScalerChannel):  # ophyd.ScalerCH
                actual_rate = control.signal.s.get() / control.scaler.time.get()
            elif isinstance(control.signal, EpicsSignalRO):  # ophyd.EpicsScaler
                raise RuntimeError("This scaler needs to divide by time")
            else:
                raise ValueError(f"unexpected control.signal: {control.signal}")
            converged.append(actual_rate <= max_rate)
            if changed:
                converged.append(actual_rate >= min_rate)

        if False not in converged:  # all True?
            complete = True
            for control in controls:
                yield from bps.mv(control.auto.mode, "manual")
            break  # no changes

    # ------------------------------------------------------------------
    # Always restore the scaler to its original timing configuration.
    # ------------------------------------------------------------------
    yield from bps.mv(
        scaler.preset_time,
        originals["preset_time"],
        scaler.delay,
        originals["delay"],
        scaler.count_mode,
        originals["count_mode"],
    )

    if not complete and aps.inUserOperations:  # bailed out early from loop
        logger.warning(f"converged={converged}")
        msg = f"FAILED TO FIND CORRECT GAIN IN {max_iterations} AUTOSCALE ITERATIONS"
        if RE is not None and RE.state != "idle":  # don't raise if in summarize_plan()
            raise AutoscaleError(msg)


def group_controls_by_scaler(controls):
    """Return a dict of control lists keyed by their common scaler name.

    Used to batch amplifiers that share a scaler so they can be handled
    together in a single set of scaler trigger/read operations.

    Parameters
    ----------
    controls : list or tuple of DetectorAmplifierAutorangeDevice
        Flat list of amplifier control objects to partition.

    Returns
    -------
    OrderedDefaultDict
        ``{scaler.name: [control, ...]}`` preserving insertion order.
    """
    assert isinstance(controls, (tuple, list)), "controls must be a list"
    scaler_dict = OrderedDefaultDict(list)  # sort the list of controls by scaler
    for i, control in enumerate(controls):
        # each item in list MUST be instance of DetectorAmplifierAutorangeDevice
        msg = (
            f"controls[{i}] must be"
            " instance of 'DetectorAmplifierAutorangeDevice'"
            f", provided: {control}"
        )
        assert isinstance(control, DetectorAmplifierAutorangeDevice), msg

        k = control.scaler.name  # key by scaler's ophyd device name
        scaler_dict[k].append(control)  # group controls by scaler
    return scaler_dict


@plan
def _scaler_background_measurement_(control_list, count_time=0.5, num_readings=8):
    """Plan (internal): measure amplifier dark currents for one scaler group.

    For every gain setting (from highest to lowest index), triggers the scaler
    ``num_readings`` times and records the mean and standard deviation of the
    count rate into the corresponding ``AmplfierGainDevice`` background PVs.

    Parameters
    ----------
    control_list : list of DetectorAmplifierAutorangeDevice
        Controls must all share the same scaler (``control_list[0].scaler``).
    count_time : float
        Scaler integration time per reading, seconds.
    num_readings : int
        Number of scaler triggers per gain setting used to compute statistics.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.

    Notes
    -----
    All controls are put into ``manual`` mode before sweeping gains so that
    the autorange IOC sequence program does not override the set gain during
    measurement.
    """
    scaler = control_list[0].scaler
    signals = [c.signal for c in control_list]

    stage_sigs = {}
    stage_sigs["scaler"] = scaler.stage_sigs  # benign
    original = {}
    original["scaler.preset_time"] = scaler.preset_time.get()
    original["scaler.auto_count_delay"] = scaler.auto_count_delay.get()
    yield from bps.mv(scaler.preset_time, count_time, scaler.auto_count_delay, 0)

    # Put all controls into manual mode so the IOC does not change gain mid-sweep.
    for control in control_list:
        yield from bps.mv(control.auto.mode, AutorangeSettings.manual)

    # Sweep gains in reverse order (highest index = lowest gain first).
    for n in range(NUM_AUTORANGE_GAINS - 1, -1, -1):  # reverse order
        # set gains
        settling_time = AMPLIFIER_MINIMUM_SETTLING_TIME
        for control in control_list:
            yield from control.auto.setGain(n)
            settling_time = max(settling_time, control.femto.settling_time.get())
        yield from bps.sleep(settling_time)

        def getScalerChannelPvname(scaler_channel):
            """Return the PV name for a scaler channel, handling both ScalerCH and EpicsScaler variants."""
            try:
                return scaler_channel.pvname  # EpicsScaler channel
            except AttributeError:
                return scaler_channel.chname.get()  # ScalerCH channel

        # readings is a PV-keyed dictionary
        readings = {getScalerChannelPvname(s): [] for s in signals}

        for _ in range(num_readings):
            yield from bps.sleep(0.05)  # allow amplifier to stabilize on gain
            # count and wait to complete
            yield from bps.trigger(scaler, wait=True)  # timeout=count_time+1.0)

            for s in signals:
                pvname = getScalerChannelPvname(s)
                value = (
                    s.get()
                )  # EpicsScaler channel value or ScalerCH ScalerChannelTuple
                if not isinstance(value, float):
                    value = s.s.get()  # ScalerCH channel value
                value = value / count_time  # looks like we did not read value/sec here?
                readings[pvname].append(value)

        # Write mean ± std of count rate to the background PVs for this gain range.
        s_range_name = f"gain{n}"
        for control in control_list:
            g = getattr(control.auto.ranges, s_range_name)
            pvname = getScalerChannelPvname(control.signal)
            yield from bps.mv(
                g.background,
                np.mean(readings[pvname]),
                g.background_error,
                np.std(readings[pvname]),
            )
            msg = f"{control.nickname}"
            msg += f" range={n}"
            msg += f" gain={_gain_to_str_(control.auto.gain.get())}"
            msg += f" bkg={g.background.get()}"
            msg += f" +/- {g.background_error.get()}"

            logger.debug(msg)

    scaler.stage_sigs = stage_sigs["scaler"]
    yield from bps.mv(
        scaler.preset_time,
        original["scaler.preset_time"],
        scaler.auto_count_delay,
        original["scaler.auto_count_delay"],
    )


@plan
def measure_background(controls, shutter=None, count_time=0.2, num_readings=5):
    """Plan: measure detector dark currents simultaneously for all controls.

    Closes the shutter (if supplied), then calls
    ``_scaler_background_measurement_`` for each scaler group so that all
    gain settings are swept and the background PVs are populated.

    Parameters
    ----------
    controls : list or tuple of DetectorAmplifierAutorangeDevice
        Amplifier controls whose backgrounds should be measured.
    shutter : optional
        If supplied, closed before measurements begin.
    count_time : float
        Scaler integration time per reading, seconds.  Default 0.2.
    num_readings : int
        Readings per gain setting used to compute mean/std.  Default 5.

    Yields
    ------
    Bluesky messages consumed by the RunEngine.
    """
    assert isinstance(controls, (tuple, list)), "controls must be a list"
    scaler_dict = group_controls_by_scaler(controls)

    logger.info("Measuring dark currents")

    if shutter is not None:
        yield from bps.mv(shutter, "close")

    for control_list in scaler_dict.values():
        # do these in sequence, just in case same hardware used multiple times
        if len(control_list) > 0:
            msg = "Measuring background for: " + control_list[0].nickname
            logger.debug(msg)
            yield from _scaler_background_measurement_(
                control_list, count_time, num_readings
            )


def UPDRange() -> int:
    """Get the current UPD autorange gain index.

    Returns
    -------
    int
        The UPD last-used range index from the autorange sequence program.

    """
    return upd_controls.auto.lurange.get()  # TODO: check return value is int


def _gain_to_str_(gain: int) -> str:
    """Format a gain index as a human-readable power-of-ten string.

    Used for log messages in ``_scaler_background_measurement_``.

    Parameters
    ----------
    gain : int
        Integer gain index (e.g. 3).

    Returns
    -------
    str
        e.g. ``"10^3"``.

    Notes
    -----
    This is a *different* function from ``_gain_to_str_`` in
    ``devices/amplifiers.py``.  That version converts a float gain value to
    scientific notation (``"1e5"``); this one formats an integer index as
    ``"10^n"``.  The two functions are not interchangeable.
    """
    return f"10^{gain}"


class OrderedDefaultDict(OrderedDict):
    """``defaultdict`` that preserves insertion order.

    Combines the missing-key auto-creation of ``collections.defaultdict``
    with the deterministic iteration order of ``collections.OrderedDict``.
    Used by ``_last_autorange_gain_`` to track the most recently converged
    gain per scaler/channel across successive autoscale calls.
    """

    def __init__(self, default_factory=None, *args, **kwargs):
        """Initialise with an optional factory callable.

        Parameters
        ----------
        default_factory : callable or None
            Called with no arguments to supply a default value for missing
            keys, exactly as with ``collections.defaultdict``.
        *args, **kwargs
            Forwarded to ``OrderedDict.__init__``.
        """
        super().__init__(*args, **kwargs)
        self.default_factory = default_factory

    def __missing__(self, key):
        """Create and return a default value for an absent key.

        Parameters
        ----------
        key : hashable
            The key that was not found.

        Returns
        -------
        object
            The new default value (also stored under ``key``).

        Raises
        ------
        KeyError
            If ``default_factory`` is None (matching ``dict`` behaviour).
        """
        if self.default_factory is None:
            raise KeyError(key)
        self[key] = value = self.default_factory()
        return value


# Module-level cache: maps scaler name → {gain_signal_name → last gain value}.
# Persists across plan calls so autoscale starts from a warm initial gain.
_last_autorange_gain_ = OrderedDefaultDict(dict)
