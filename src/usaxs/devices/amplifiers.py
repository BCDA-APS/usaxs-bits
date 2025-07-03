"""
Detectors, scaler channels, amplifiers, and related support

========  =================  ====================  ===================  ===========
detector  scaler channel     amplifier             autorange sequence   Femto model
========  =================  ====================  ===================  ===========
UPD       usxLAX:vsc:c0.S4   usxLAX:fem01:seq01:   usxLAX:pd01:seq01:   DLPCA200
UPD       usxLAX:vsc:c0.S4   usxLAX:fem09:seq02:   usxLAX:pd01:seq02:   DDPCA300
I0        usxLAX:vsc:c0.S2   usxRIO:fem02:seq01:   usxLAX:pd02:seq01:
I00       usxLAX:vsc:c0.S3   usxRIO:fem03:seq01:   usxLAX:pd03:seq01:
I000      usxLAX:vsc:c0.S6   usxRIO:fem04:seq01:   None
TRD       usxLAX:vsc:c0.S5   usxRIO:fem05:seq01:   usxLAX:pd05:seq01:
========  =================  ====================  ===================  ===========

Edit the `configs/scalers_and_amplifiers.yml` file to select the proper devices
with the UPD Femto amplifier currently being used.  A read-only PV
(``usxLAX:femto:model``) tells which UPD amplifier and sequence programs we're
using now.  This PV is read-only since it is set when IOC boots, based on a soft
link that configures the IOC.
"""

import logging
from collections import OrderedDict

from apsbits.core.instrument_init import oregistry
from apstools.synApps import SwaitRecord
from bluesky import plan_stubs as bps
from bluesky.utils import plan
from ophyd import Component
from ophyd import Device
from ophyd import DynamicDeviceComponent
from ophyd import EpicsSignal
from ophyd import EpicsSignalRO
from ophyd import FormattedComponent
from ophyd import Signal
from ophyd.scaler import ScalerCH
from ophyd.scaler import ScalerChannel

logger = logging.getLogger(__name__)


NUM_AUTORANGE_GAINS = 5  # common to all autorange sequence programs
AMPLIFIER_MINIMUM_SETTLING_TIME = 0.01  # reasonable?


class ModifiedSwaitRecord(SwaitRecord):
    """Modified SwaitRecord with enable component removed."""

    enable = None  # remove this Component


def _gain_to_str_(gain):  # convenience function
    return ("%.0e" % gain).replace("+", "").replace("e0", "e")


class AutoscaleError(RuntimeError):
    """Raised when autoscale fails to converge."""


class AutorangeSettings:
    """Values allowed for sequence program's ``reqrange`` PV."""

    automatic = "automatic"
    auto_background = "auto+background"
    manual = "manual"


class CurrentAmplifierDevice(Device):
    """Base device for current amplifiers."""

    gain = Component(EpicsSignalRO, "gain", kind="omitted")


class FemtoAmplifierDevice(CurrentAmplifierDevice):
    """Device for Femto amplifier with gain and description components."""

    gainindex = Component(EpicsSignal, "gainidx", kind="omitted")
    description = Component(EpicsSignal, "femtodesc", kind="omitted")

    # gain settling time for the device is <150ms
    settling_time = Component(Signal, value=0.08)

    def __init__(self, *args, **kwargs):
        """
        Initialize the FemtoAmplifierDevice.

        Parameters
        ----------
        *args: Variable length argument list.
        **kwargs: Arbitrary keyword arguments.
        """
        super().__init__(*args, **kwargs)

        self._gain_info_known = False
        self.num_gains = 0
        self.acceptable_gain_values = ()

    def __init_gains__(self, enum_strs):
        """
        learn range (gain) values from EPICS database

        provide a list of acceptable gain values for later use
        """
        acceptable = [s for s in enum_strs if s != "UNDEF"]
        num_gains = len(acceptable)
        # assume labels are ALWAYS formatted: "{float} V/A"
        acceptable += [float(s.split()[0]) for s in acceptable]
        acceptable += range(num_gains)
        self.num_gains = num_gains
        self.acceptable_range_values = acceptable

        # assume gain labels are formatted "{float} {other_text}"
        s = acceptable[0]
        self.gain_suffix = s[s.find(" ") :]
        for i, s in enumerate(acceptable[:num_gains]):
            # verify all gains use same suffix text
            msg = f"gainindex[{i}] = {s}, expected ending '{self.gain_suffix}'"
            assert s[s.find(" ") :] == self.gain_suffix, msg

        self._gain_info_known = True

    def setGain(self, target):
        """
        set the gain on the amplifier

        Since the gain values are available from EPICS,
        we use that to provide a method that can set the
        gain by any of these values:

        * gain text value (from EPICS)
        * integer index number
        * desired gain floating-point value

        Assumptions:

        * gain label (from EPICS) is ALWAYS: "{float} V/A"
        * float mantissa is always one digit
        """
        if not self._gain_info_known:
            self.__init_gains__(self.gainindex.enum_strs)
        if target in self.acceptable_gain_values:
            if isinstance(target, (int, float)) and target > self.num_gains:
                # gain value specified, rewrite as str
                # assume mantissa is only 1 digit
                target = _gain_to_str_(target) + self.gain_suffix
            yield from bps.mv(self.gainindex, target)
        else:
            msg = f"could not set gain to {target}, "
            msg += f"must be one of these: {self.acceptable_gain_values}"
            raise ValueError(msg)


class AmplfierGainDevice(Device):
    """Device for amplifier gain, background, and error channels."""

    _default_configuration_attrs = ()
    _default_read_attrs = ("gain", "background", "background_error")

    gain = FormattedComponent(EpicsSignal, "{self.prefix}gain{self._ch_num}")
    background = FormattedComponent(EpicsSignal, "{self.prefix}bkg{self._ch_num}")
    background_error = FormattedComponent(
        EpicsSignal, "{self.prefix}bkgErr{self._ch_num}"
    )

    def __init__(self, prefix, ch_num=None, **kwargs):
        """
        Initialize the AmplfierGainDevice.

        Parameters
        ----------
        prefix : str
            The prefix for the device.
        ch_num : int, optional
            The channel number.
        **kwargs: Arbitrary keyword arguments.
        """
        assert ch_num is not None, "Must provide `ch_num=` keyword argument."
        self._ch_num = ch_num
        super().__init__(prefix, **kwargs)


def _gains_subgroup_(cls, nm, gains, **kwargs):
    """internal: used in AmplifierAutoDevice"""
    defn = OrderedDict()
    for i in gains:
        key = f"{nm}{i}"
        defn[key] = (cls, "", dict(ch_num=i))

    return defn


class AmplifierAutoDevice(CurrentAmplifierDevice):
    """
    Ophyd support for amplifier sequence program.
    """

    reqrange = Component(EpicsSignal, "reqrange")
    mode = Component(EpicsSignal, "mode")
    selected = Component(EpicsSignal, "selected")
    gainU = Component(EpicsSignal, "gainU")
    gainD = Component(EpicsSignal, "gainD")
    ranges = DynamicDeviceComponent(
        _gains_subgroup_(AmplfierGainDevice, "gain", range(NUM_AUTORANGE_GAINS))
    )
    counts_per_volt = Component(EpicsSignal, "vfc")
    status = Component(EpicsSignalRO, "updating")
    lurange = Component(EpicsSignalRO, "lurange")
    lucounts = Component(EpicsSignalRO, "lucounts")
    lurate = Component(EpicsSignalRO, "lurate")
    lucurrent = Component(EpicsSignalRO, "lucurrent")
    updating = Component(EpicsSignalRO, "updating")

    max_count_rate = Component(Signal, value=950000)
    min_count_rate = Component(Signal, value=500)

    def __init__(self, prefix, **kwargs):
        """
        Initialize the AmplifierAutoDevice.

        Parameters
        ----------
        prefix : str
            The prefix for the device.
        **kwargs: Arbitrary keyword arguments.
        """
        self.scaler = None
        super().__init__(prefix, **kwargs)

        self._gain_info_known = False
        self.num_gains = 0
        self.acceptable_gain_values = ()

    def __init_gains__(self, enum_strs):
        """
        learn range (gain) values from EPICS database

        provide a list of acceptable gain values for later use
        """
        acceptable = list(enum_strs)
        num_gains = len(acceptable)
        # assume labels are ALWAYS formatted: "{float} V/A"
        acceptable += [float(s.split()[0]) for s in acceptable]
        acceptable += range(num_gains)
        self.num_gains = num_gains
        self.acceptable_gain_values = acceptable

        # assume gain labels are formatted "{float} {other_text}"
        s = acceptable[0]
        self.gain_suffix = s[s.find(" ") :]
        for i, s in enumerate(acceptable[:num_gains]):
            # verify all gains use same suffix text
            msg = f"reqrange[{i}] = {s}, expected ending: '{self.gain_suffix}'"
            assert s[s.find(" ") :] == self.gain_suffix, msg

        self._gain_info_known = True

    @plan
    def setGain(self, target):
        """
        plan: set the gain on the autorange controls

        Since the gain values are available from EPICS,
        we use that to provide a method that can request the
        gain by any of these values:

        * gain text value (from EPICS)
        * integer index number
        * desired gain floating-point value

        Assumptions:

        * gain label (from EPICS) is ALWAYS: "{float} {self.gain_suffix}"
        * float mantissa is always one digit
        """
        if not self._gain_info_known:
            self.__init_gains__(self.reqrange.enum_strs)
        if target in self.acceptable_gain_values:
            if isinstance(target, (int, float)) and target > self.num_gains:
                # gain value specified, rewrite as str
                # assume mantissa is only 1 digit
                target = _gain_to_str_(target) + self.gain_suffix
            if isinstance(target, str) and str(target) in self.reqrange.enum_strs:
                # must set reqrange by index number, rewrite as int
                target = self.reqrange.enum_strs.index(target)
            yield from bps.mv(self.reqrange, target)
        else:
            msg = f"could not set gain to {target}, "
            msg += f"must be one of these: {self.acceptable_gain_values}"
            raise ValueError(msg)

    @property
    def isUpdating(self):
        """
        Return True if the autorange device is updating.

        Returns
        -------
        bool
            True if updating, False otherwise.
        """
        v = self.mode.get() in (1, AutorangeSettings.auto_background)
        if v:
            v = self.updating.get() in (1, "Updating")
        return v


class DetectorAmplifierAutorangeDevice(Device):
    """
    Coordinate the different objects that control a diode or ion chamber.

    This is a convenience intended to simplify tasks such as measuring the
    backgrounds of all channels simultaneously.
    """

    def __init__(self, nickname, scaler, det, **kwargs):
        """
        Initialize DetectorAmplifierAutorangeDevice.

        Parameters
        ----------
        nickname : str
            Nickname for the device.
        scaler : str
            Name of the ScalerCH.
        det : str
            Name of the detector.
        **kwargs: Arbitrary keyword arguments.
        """
        if not isinstance(nickname, str):
            raise ValueError(
                "'nickname' should be of 'str' type,"
                f" received type: {type(nickname)}"
            )
        self.nickname = nickname
        self.scaler = oregistry[scaler]
        self.signal = oregistry[f"{det.upper()}_SIGNAL"]
        self.femto = oregistry[
            f"{det}_femto_amplifier"
        ]  # changed from .femto, I assume amplfier is correct?
        self.auto = oregistry[f"{det}_autorange_controls"]

        if not isinstance(self.scaler, ScalerCH):
            raise ValueError(
                "'scaler' should name a 'ScalerCH' type,"
                f" received type: {type(self.scaler)}"
            )
        if not isinstance(self.signal, ScalerChannel):
            raise ValueError(
                "'signal' should name a 'ScalerChannel' type,"
                f" received type: {type(self.signal)}"
            )
        if not isinstance(self.femto, FemtoAmplifierDevice):
            raise ValueError(
                "'amplifier' should name a 'FemtoAmplifierDevice' type,"
                f" received type: {type(self.femto)}"
            )
        if not isinstance(self.auto, AmplifierAutoDevice):  # this fails to for I0
            raise ValueError(
                "'auto' should name a 'AmplifierAutoDevice' type,"
                f" received type: {type(self.auto)}"
            )

        super().__init__("", **kwargs)
