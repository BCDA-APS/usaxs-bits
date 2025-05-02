"""
detectors, amplifiers, and related support

#            Define local PD address:
 if(Use_DLPCA300){
     PDstring = "pd01:seq02"
     UPD_PV    =    "usxUSX:pd01:seq02"
  }else{
     PDstring = "pd01:seq01"
     UPD_PV    =    "usxUSX:pd01:seq01"
  }

========  =================  ====================  ===================  ===========
detector  scaler             amplifier             autorange sequence   Femto model
========  =================  ====================  ===================  ===========
UPD       usxLAX:vsc:c0.S4  usxLAX:fem01:seq01:  usxLAX:pd01:seq01:  DLPCA200
UPD       usxLAX:vsc:c0.S4  usxLAX:fem09:seq02:  usxLAX:pd01:seq02:  DDPCA300
I0        usxLAX:vsc:c0.S2  usxRIO:fem02:seq01:  usxLAX:pd02:seq01:
I00       usxLAX:vsc:c0.S3  usxRIO:fem03:seq01:  usxLAX:pd03:seq01:
I000      usxLAX:vsc:c0.S6  usxRIO:fem04:seq01:  None
TRD       usxLAX:vsc:c0.S5  usxRIO:fem05:seq01:  usxLAX:pd05:seq01:
========  =================  ====================  ===================  ===========

A PV (``usxLAX:femto:model``) tells which UPD amplifier and sequence
programs we're using now.  This PV is read-only since it is set when
IOC boots, based on a soft link that configures the IOC.  The soft
link may be changed using the ``use200pd``  or  ``use300pd`` script.

We only need to get this once, get it via one-time call with PyEpics
and then use it with inline dictionaries to pick the right PVs.
"""

__all__ = """
    AutorangeSettings

    upd_femto_amplifier
    trd_femto_amplifier
    I0_femto_amplifier
    I00_femto_amplifier
    I000_femto_amplifier

    upd_autorange_controls
    trd_autorange_controls
    I0_autorange_controls
    I00_autorange_controls

    upd_controls
    upd_photocurrent

    trd_controls
    trd_photocurrent

    I0_controls
    I0_photocurrent

    I00_controls
    I00_photocurrent

    I000_photocurrent_calc
    I000_photocurrent

    controls_list_I0_I00_TRD
    controls_list_UPD_I0_I00_TRD

    autoscale_amplifiers
    measure_background
    """.split()


import logging
from collections import OrderedDict

import epics
from apsbits.utils.config_loaders import get_config
from apstools.synApps import SwaitRecord
from bluesky import plan_stubs as bps
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
logger.info(__file__)

iconfig = get_config()
scaler0_name = iconfig.get("SCALER_PV_NAMES", {}).get("SCALER0_NAME")

NUM_AUTORANGE_GAINS = 5  # common to all autorange sequence programs
AMPLIFIER_MINIMUM_SETTLING_TIME = 0.01  # reasonable?

scaler0 = ScalerCH(scaler0_name, name="scaler0")
scaler0.stage_sigs["count_mode"] = "OneShot"
scaler0.select_channels()

I00_SIGNAL = scaler0.channels.chan03
I0 = scaler0.channels.chan02.s
I00 = scaler0.channels.chan03.s
UPD_SIGNAL = scaler0.channels.chan04
TRD_SIGNAL = scaler0.channels.chan05
I0_SIGNAL = scaler0.channels.chan02


class ModifiedSwaitRecord(SwaitRecord):
    enable = None  # remove this Component


def _gain_to_str_(gain):  # convenience function
    return ("%.0e" % gain).replace("+", "").replace("e0", "e")


class AutoscaleError(RuntimeError):
    "raised when autoscale fails to converge"


class AutorangeSettings(object):
    """values allowed for sequence program's ``reqrange`` PV"""

    automatic = "automatic"
    auto_background = "auto+background"
    manual = "manual"


class CurrentAmplifierDevice(Device):
    gain = Component(EpicsSignalRO, "gain", kind="omitted")


class FemtoAmplifierDevice(CurrentAmplifierDevice):
    gainindex = Component(EpicsSignal, "gainidx", kind="omitted")
    description = Component(EpicsSignal, "femtodesc", kind="omitted")

    # gain settling time for the device is <150ms
    settling_time = Component(Signal, value=0.08)

    def __init__(self, *args, **kwargs):
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
    _default_configuration_attrs = ()
    _default_read_attrs = ("gain", "background", "background_error")

    gain = FormattedComponent(EpicsSignal, "{self.prefix}gain{self._ch_num}")
    background = FormattedComponent(EpicsSignal, "{self.prefix}bkg{self._ch_num}")
    background_error = FormattedComponent(
        EpicsSignal, "{self.prefix}bkgErr{self._ch_num}"
    )

    def __init__(self, prefix, ch_num=None, **kwargs):
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
    Ophyd support for amplifier sequence program
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

    def __init__(self, prefix, **kwargs):
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
        v = self.mode.get() in (1, AutorangeSettings.auto_background)
        if v:
            v = self.updating.get() in (1, "Updating")
        return v


# class ComputedScalerAmplifierSignal(SynSignal):
#    """
#    Scales signal from counter by amplifier gain.
#    """
#
#    def __init__(self, name, parent, **kwargs):
#
#        def func():		# runs only when Device is triggered
#            counts = parent.signal.s.get()
#            volts = counts / parent.auto.counts_per_volt.get()
#            volts_per_amp = parent.femto.gain.get()
#            return volts / volts_per_amp
#
#        super().__init__(func=func, name=name, **kwargs)


class DetectorAmplifierAutorangeDevice(Device):
    """
    Coordinate the different objects that control a diode or ion chamber

    This is a convenience intended to simplify tasks such
    as measuring simultaneously the backgrounds of all channels.
    """

    def __init__(self, nickname, scaler, signal, amplifier, auto, **kwargs):
        if not isinstance(nickname, str):
            raise ValueError(
                "'nickname' should be of 'str' type,"
                f" received type: {type(nickname)}"
            )
        if not isinstance(scaler, ScalerCH):
            raise ValueError(
                "'scaler' should be of 'ScalerCH' type,"
                f" received type: {type(scaler)}"
            )
        if not isinstance(signal, ScalerChannel):
            raise ValueError(
                "'signal' should be of 'ScalerChannel' type,"
                f" received type: {type(signal)}"
            )
        if not isinstance(amplifier, FemtoAmplifierDevice):
            raise ValueError(
                "'amplifier' should be of 'FemtoAmplifierDevice' type,"
                f" received type: {type(amplifier)}"
            )
        if not isinstance(auto, AmplifierAutoDevice):
            raise ValueError(
                "'auto' should be of 'AmplifierAutoDevice' type,"
                f" received type: {type(auto)}"
            )
        self.nickname = nickname
        self.scaler = scaler
        self.signal = signal
        self.femto = amplifier
        self.auto = auto
        super().__init__("", **kwargs)


# ------------

_amplifier_id_upd = epics.caget("usxLAX:femto:model", as_string=True)

if _amplifier_id_upd == "DLCPA200":
    _upd_femto_prefix = "usxLAX:fem01:seq01:"
    _upd_auto_prefix = "usxLAX:pd01:seq01:"
elif _amplifier_id_upd == "DDPCA300":
    _upd_femto_prefix = "usxLAX:fem09:seq02:"
    _upd_auto_prefix = "usxLAX:pd01:seq02:"

upd_femto_amplifier = FemtoAmplifierDevice(
    _upd_femto_prefix, name="upd_femto_amplifier"
)
trd_femto_amplifier = FemtoAmplifierDevice(
    "usxRIO:fem05:seq01:", name="trd_femto_amplifier"
)
I0_femto_amplifier = FemtoAmplifierDevice(
    "usxRIO:fem02:seq01:", name="I0_femto_amplifier"
)
I00_femto_amplifier = FemtoAmplifierDevice(
    "usxRIO:fem03:seq01:", name="I00_femto_amplifier"
)
I000_femto_amplifier = FemtoAmplifierDevice(
    "usxRIO:fem04:seq01:", name="I000_femto_amplifier"
)

upd_autorange_controls = AmplifierAutoDevice(
    _upd_auto_prefix, name="upd_autorange_controls"
)
trd_autorange_controls = AmplifierAutoDevice(
    "usxLAX:pd05:seq01:", name="trd_autorange_controls"
)
I0_autorange_controls = AmplifierAutoDevice(
    "usxLAX:pd02:seq01:", name="I0_autorange_controls"
)
I00_autorange_controls = AmplifierAutoDevice(
    "usxLAX:pd03:seq01:", name="I00_autorange_controls"
)

# # record at start and end of each scan
# sd.baseline.append(upd_autorange_controls)
# sd.baseline.append(trd_autorange_controls)
# sd.baseline.append(I0_autorange_controls)
# sd.baseline.append(I00_autorange_controls)

upd_controls = DetectorAmplifierAutorangeDevice(
    "PD_USAXS",
    scaler0,
    UPD_SIGNAL,
    upd_femto_amplifier,
    upd_autorange_controls,
    name="upd_controls",
)
# upd_photocurrent = ComputedScalerAmplifierSignal(
#    name="upd_photocurrent", parent=upd_controls)
upd_photocurrent_calc = ModifiedSwaitRecord(
    "usxLAX:USAXS:upd", name="upd_photocurrent_calc"
)
upd_photocurrent = upd_photocurrent_calc.get()

trd_controls = DetectorAmplifierAutorangeDevice(
    "TR diode",
    scaler0,
    TRD_SIGNAL,
    trd_femto_amplifier,
    trd_autorange_controls,
    name="trd_controls",
)
# trd_photocurrent = ComputedScalerAmplifierSignal(
#    name="trd_photocurrent", parent=trd_controls)
trd_photocurrent_calc = ModifiedSwaitRecord(
    "usxLAX:USAXS:trd", name="trd_photocurrent_calc"
)
trd_photocurrent = trd_photocurrent_calc.get()

I0_controls = DetectorAmplifierAutorangeDevice(
    "I0_USAXS",
    scaler0,
    I0_SIGNAL,
    I0_femto_amplifier,
    I0_autorange_controls,
    name="I0_controls",
)
# I0_photocurrent = ComputedScalerAmplifierSignal(
#    name="I0_photocurrent", parent=I0_controls)
I0_photocurrent_calc = ModifiedSwaitRecord(
    "usxLAX:USAXS:I0", name="I0_photocurrent_calc"
)
I0_photocurrent = I0_photocurrent_calc.get()

I00_controls = DetectorAmplifierAutorangeDevice(
    "I00_USAXS",
    scaler0,
    I00_SIGNAL,
    I00_femto_amplifier,
    I00_autorange_controls,
    name="I00_controls",
)
# I00_photocurrent = ComputedScalerAmplifierSignal(
#    name="I00_photocurrent", parent=I00_controls)
I00_photocurrent_calc = ModifiedSwaitRecord(
    "usxLAX:USAXS:I00", name="I00_photocurrent_calc"
)
I00_photocurrent = I00_photocurrent_calc.get()


I000_photocurrent_calc = ModifiedSwaitRecord(
    "usxLAX:USAXS:I000", name="I000_photocurrent_calc"
)
I000_photocurrent = I000_photocurrent_calc.get()


controls_list_I0_I00_TRD = [I0_controls, I00_controls, trd_controls]
controls_list_UPD_I0_I00_TRD = [upd_controls] + controls_list_I0_I00_TRD
