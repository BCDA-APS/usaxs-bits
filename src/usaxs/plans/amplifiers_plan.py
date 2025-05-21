"""
Amplifier support
"""

import logging
from collections import OrderedDict
from typing import Any
from typing import Optional

import numpy as np

# Get devices from oregistry
from apsbits.core.instrument_init import oregistry

# Add missing imports at the top
from bluesky import RunEngine
from bluesky import plan_stubs as bps
from ophyd.signal import EpicsSignalRO

from src.usaxs.devices.amplifier_device import AMPLIFIER_MINIMUM_SETTLING_TIME
from src.usaxs.devices.amplifier_device import NUM_AUTORANGE_GAINS
from src.usaxs.devices.amplifier_device import AutorangeSettings
from src.usaxs.devices.amplifier_device import AutoscaleError
from src.usaxs.devices.amplifier_device import DetectorAmplifierAutorangeDevice
from src.usaxs.devices.scaler_device import ScalerChannel

# Add these imports at the top of the file
# Imports from local plans

# Device instances
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
upd_controls = oregistry["upd_controls"]
usaxs_shutter = oregistry["usaxs_shutter"]
trd_controls = oregistry["trd_controls"]
trd = oregistry["trd"]
user_data = oregistry["user_data"]

logger = logging.getLogger(__name__)


def setup_amplifier_count_time():
    """Set up the count time for the amplifier.

    This function configures the count time settings for the amplifier
    and ensures proper synchronization with the scaler.
    """


def setup_amplifier_auto_background():
    """Set up automatic background measurement for the amplifier.

    This function configures the amplifier for automatic background
    measurement and updates the necessary parameters.
    """


def autoscale_amplifiers(
    controls: list[DetectorAmplifierAutorangeDevice],
    shutter: Optional[Any] = None,
    count_time: float = 0.05,
    max_iterations: int = 9,
    RE: Optional[RunEngine] = None,
):
    """Bluesky plan: autoscale detector amplifiers simultaneously.

    Parameters
    ----------
    controls : list[DetectorAmplifierAutorangeDevice]
        list (or tuple) of ``DetectorAmplifierAutorangeDevice``
    shutter : Optional[Any], optional
        Shutter device to control, by default None
    count_time : float, optional
        Time to count for each measurement, by default 0.05
    max_iterations : int, optional
        Maximum number of iterations to try, by default 9
    RE : Optional[RunEngine], optional
        RunEngine instance to use, by default None

    Returns
    -------
    Generator[Any, None, Any]
        Bluesky plan
    """
    if RE is None:
        raise ValueError("RunEngine instance must be provided")

    assert isinstance(controls, (tuple, list)), "controls must be a list"
    scaler_dict = group_controls_by_scaler(controls)

    if shutter is not None:
        yield from bps.mv(shutter, "open")

    for control_list in scaler_dict.values():
        # do amplifiers in sequence, in case same hardware used multiple times
        if len(control_list) > 0:
            try:
                yield from _scaler_autoscale_(
                    control_list,
                    count_time=count_time,
                    max_iterations=max_iterations,
                    RE=RE,
                )
            except AutoscaleError as exc:
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


def _scaler_autoscale_(
    controls: list[DetectorAmplifierAutorangeDevice],
    count_time: float = 0.05,
    max_iterations: int = 9,
    RE: Optional[RunEngine] = None,
):
    """Plan: internal: autoscale amplifiers for signals sharing a common scaler.

    Args:
        controls: list of DetectorAmplifierAutorangeDevice instances
        count_time: Time to count for each measurement
        max_iterations: Maximum number of iterations to try
        RE: RunEngine instance to use

    Yields:
        Generator: Control flow for the autoscale operation
    """
    if RE is None:
        raise ValueError("RunEngine instance must be provided")

    aps = oregistry["aps"]
    global _last_autorange_gain_

    scaler = controls[0].scaler
    originals = {}

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

    # Autoscale has converged if no gains change
    # Also, make sure no detector count rates are stuck at max

    complete = False
    for _ in range(max_iterations):
        converged = []  # append True is convergence criteria is satisfied
        yield from bps.trigger(scaler, wait=True)  # timeout=count_time+1.0)

        # amplifier sequence program (in IOC) will adjust the gain now

        for control in controls:
            # any gains changed?
            gain_now = control.auto.gain.get()
            gain_previous = last_gain_dict[control.auto.gain.name]
            converged.append(gain_now == gain_previous)
            last_gain_dict[control.auto.gain.name] = gain_now

            # are we topped up on any detector?
            max_rate = control.auto.max_count_rate.get()
            if isinstance(control.signal, ScalerChannel):  # ophyd.ScalerCH
                actual_rate = control.signal.s.get() / control.scaler.time.get()
            elif isinstance(control.signal, EpicsSignalRO):  # ophyd.EpicsScaler
                # actual_rate = control.signal.get()      # FIXME
                raise RuntimeError("This scaler needs to divide by time")
            else:
                raise ValueError(f"unexpected control.signal: {control.signal}")
            converged.append(actual_rate <= max_rate)
            # logger.debug(
            #     "gain={gain_now}  rate: {actual_rate}  "
            #     "max: {max_rate}  converged={converged}"
            # )

        if False not in converged:  # all True?
            complete = True
            for control in controls:
                yield from bps.mv(control.auto.mode, "manual")
            # logger.debug(f"converged: {converged}")
            break  # no changes

    # scaler.stage_sigs = stage_sigs["scaler"]
    # restore starting conditions
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
        msg = "FAILED TO FIND CORRECT GAIN IN " f"{max_iterations} AUTOSCALE ITERATIONS"
        if RE.state != "idle":  # don't raise if in summarize_plan()
            raise AutoscaleError(msg)


def group_controls_by_scaler(controls):
    """
    return dictionary of [controls] keyed by common scaler support

    controls [obj]
        list (or tuple) of ``DetectorAmplifierAutorangeDevice``
    """
    assert isinstance(controls, (tuple, list)), "controls must be a list"
    scaler_dict = OrderedDefaultDict(list)  # sort the list of controls by scaler
    for i, control in enumerate(controls):
        # each item in list MUST be instance of DetectorAmplifierAutorangeDevice
        msg = f"controls[{i}] must be"
        msg += " instance of 'DetectorAmplifierAutorangeDevice'"
        msg += f", provided: {control}"
        assert isinstance(control, DetectorAmplifierAutorangeDevice), msg

        k = control.scaler.name  # key by scaler's ophyd device name
        scaler_dict[k].append(control)  # group controls by scaler
    return scaler_dict


def _scaler_background_measurement_(control_list, count_time=0.5, num_readings=8):
    """
    plan: internal: measure amplifier backgrounds for signals
    sharing a common scaler
    """
    scaler = control_list[0].scaler
    signals = [c.signal for c in control_list]

    stage_sigs = {}
    stage_sigs["scaler"] = scaler.stage_sigs  # benign
    original = {}
    original["scaler.preset_time"] = scaler.preset_time.get()
    original["scaler.auto_count_delay"] = scaler.auto_count_delay.get()
    yield from bps.mv(scaler.preset_time, count_time, scaler.auto_count_delay, 0)

    for control in control_list:
        yield from bps.mv(control.auto.mode, AutorangeSettings.manual)

    for n in range(NUM_AUTORANGE_GAINS - 1, -1, -1):  # reverse order
        # set gains
        settling_time = AMPLIFIER_MINIMUM_SETTLING_TIME
        for control in control_list:
            yield from control.auto.setGain(n)
            settling_time = max(settling_time, control.femto.settling_time.get())
        yield from bps.sleep(settling_time)

        def getScalerChannelPvname(scaler_channel):
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
                # logger.debug(f"scaler reading {m+1}: value: {value}")
                value = value / count_time  # looks like we did not read value/sec here?
                readings[pvname].append(value)

        s_range_name = f"gain{n}"
        for control in control_list:
            g = getattr(control.auto.ranges, s_range_name)
            pvname = getScalerChannelPvname(control.signal)
            # logger.debug(f"gain: {s_range_name} readings:{readings[pvname]}")
            yield from bps.mv(
                g.background,
                np.mean(readings[pvname]),
                g.background_error,
                np.std(readings[pvname]),
            )
            msg = f"{control.nickname}"
            msg += f" range={n}"
            msg += f" gain={ _gain_to_str_(control.auto.gain.get())}"
            msg += f" bkg={g.background.get()}"
            msg += f" +/- {g.background_error.get()}"

            # logger.info(msg)

    scaler.stage_sigs = stage_sigs["scaler"]
    yield from bps.mv(
        scaler.preset_time,
        original["scaler.preset_time"],
        scaler.auto_count_delay,
        original["scaler.auto_count_delay"],
    )


def measure_background(controls, shutter=None, count_time=0.2, num_readings=5):
    """
    plan: measure detector backgrounds simultaneously

    controls [obj]
        list (or tuple) of ``DetectorAmplifierAutorangeDevice``
    """
    assert isinstance(controls, (tuple, list)), "controls must be a list"
    scaler_dict = group_controls_by_scaler(controls)

    if shutter is not None:
        yield from bps.mv(shutter, "close")

    for control_list in scaler_dict.values():
        # do these in sequence, just in case same hardware used multiple times
        if len(control_list) > 0:
            msg = "Measuring background for: " + control_list[0].nickname
            # logger.info(msg)
            yield from _scaler_background_measurement_(
                control_list, count_time, num_readings
            )


def UPDRange(self) -> int:
    """
    Get the UPD range value.

    Returns:
        int: The UPD range value
    """
    return upd_controls.auto.lurange.get()  # TODO: check return value is int


def _gain_to_str_(gain: int) -> str:
    """Convert a gain value to a string representation.

    Args:
        gain: The gain value to convert

    Returns:
        str: String representation of the gain
    """
    return f"10^{gain}"


class OrderedDefaultDict(OrderedDict):
    """A defaultdict that maintains insertion order."""

    def __init__(self, default_factory=None, *args, **kwargs):
        """Initialize the OrderedDefaultDict.

        Args:
            default_factory: Factory function to create default values
            *args: Additional positional arguments for OrderedDict
            **kwargs: Additional keyword arguments for OrderedDict
        """
        super().__init__(*args, **kwargs)
        self.default_factory = default_factory

    def __missing__(self, key):
        """Handle missing keys by creating a default value.

        Args:
            key: The missing key

        Returns:
            The default value for the key
        """
        if self.default_factory is None:
            raise KeyError(key)
        self[key] = value = self.default_factory()
        return value


_last_autorange_gain_ = OrderedDefaultDict(dict)
