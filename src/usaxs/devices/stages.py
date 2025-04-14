"""
stages
"""

# TODO check, refactor and verify...

from ophyd import Component
from ophyd import Device
from ophyd import EpicsMotor
from ophyd import EpicsSignal
from ophyd import MotorBundle

from ..misc.usaxs_motor_devices import TunableEpicsMotor2
from ..misc.usaxs_motor_devices import TunableEpicsMotor2WTolerance

# this is for tuning part of the code.
# 2024-06-28 we need to merge stages.py with axis_tuning.py since the new tunable motor
# class is defined here.
# use center-of-mass, and not peak value: "com"
TUNE_METHOD_PEAK_CHOICE = "centroid"

USING_MS_STAGE = False
# TUNING_DET_SIGNAL = {True: I00_SIGNAL, False: I0_SIGNAL}[USING_MS_STAGE]


class TuneRanges(Device):
    """
    width of tuning for each axis
    """

    # in order of optical path
    mr = Component(EpicsSignal, "usxLAX:USAXS:tune_mr_range")
    msrp = Component(EpicsSignal, "usxLAX:USAXS:tune_msrp_range")
    m2rp = Component(EpicsSignal, "usxLAX:USAXS:tune_m2rp_range")
    ar = Component(EpicsSignal, "usxLAX:USAXS:tune_ar_range")
    asrp = Component(EpicsSignal, "usxLAX:USAXS:tune_asrp_range")
    a2rp = Component(EpicsSignal, "usxLAX:USAXS:tune_a2rp_range")
    dx = Component(EpicsSignal, "usxLAX:USAXS:tune_dx_range")
    dy = Component(EpicsSignal, "usxLAX:USAXS:tune_dy_range")

    @property
    def display(self):
        return ", ".join(
            [f"{k}={getattr(self, k).get()}" for k in self.component_names]
        )


axis_tune_range = TuneRanges(name="axis_tune_range")

# --------------MR stage-----------------------------

# def mr_pretune_hook():
#     stage = m_stage.r
#     logger.info(f"Tuning axis {stage.name}, current position is {stage.position}")
#     yield from bps.mv(scaler0.preset_time, 0.1,)
#     scaler0.select_channels(["I0_USAXS"])
#     #TODO: this shoudl move to plans for plot handling.
#     #y_name = TUNING_DET_SIGNAL.chname.get()
#     #scaler0.select_channels([y_name])
#     #scaler0.channels.chan01.kind = Kind.config
#     # trim_plot_by_name(n=5)
# #this may be needed if we make plotting again, but lineup2 does not plot by default.
#     # trim_plot_lines(bec, 5, stage, TUNING_DET_SIGNAL)


# def mr_posttune_hook():
#     #msg = "Tuning axis {}, final position is {}"
#     #logger.info(msg.format(m_stage.r.name, m_stage.r.position))
#     # need to plot data in plans
#     scaler0.select_channels(None)
#     yield from bps.null()



class UsaxsCollimatorStageDevice(MotorBundle):
    """USAXS Collimator (Monochromator) stage"""

    r = Component(
        TunableEpicsMotor2WTolerance,
        "usxAERO:m12",
        labels=(
            "collimator",
            "tunable",
        ),
        tune_range=axis_tune_range.mr,
        # defaults everything else
    )
    x = Component(EpicsMotor, "usxAERO:m10", labels=("collimator",))
    y = Component(EpicsMotor, "usxAERO:m11", labels=("collimator",))
    r2p = Component(
        TunableEpicsMotor2,
        "usxLAX:pi:c0:m2",
        labels=(
            "collimator",
            "tunable",
        ),
        tune_range=axis_tune_range.m2rp,
        # defaults everything else
    )
    isChannelCut = True


# ----- end of MR ------
# -------M2RP - not needed for single crystal channelcut M stage--------------------


# def m2rp_pretune_hook():
#     stage = m_stage.r2p
#     logger.info(f"Tuning axis {stage.name}, current position is {stage.position}")
#     yield from bps.mv(scaler0.preset_time, 0.1)
#     yield from bps.mv(scaler0.delay, 0.02)
#     #scaler0.select_channels(["I0_USAXS"])
#     y_name = TUNING_DET_SIGNAL.chname.get()
#     scaler0.select_channels([y_name])
#     scaler0.channels.chan01.kind = Kind.config
#     #trim_plot_by_name(n=5)
#     # trim_plot_lines(bec, 5, stage, TUNING_DET_SIGNAL)


# def m2rp_posttune_hook():
#     msg = "Tuning axis {}, final position is {}"
#     logger.info(msg.format(m_stage.r2p.name, m_stage.r2p.position))
#     yield from bps.mv(scaler0.delay, 0.05)
#     #if m_stage.r2p.tuner.tune_ok:
#     #    pass    # #165: update center when/if we get a PV for that
#     scaler0.select_channels(None)


# -----END OF MSRP--------------------------------------
# -------D stage ------------------------------------


# def dx_pretune_hook():
#     stage = d_stage.x
#     logger.info(f"Tuning axis {stage.name}, current position is {stage.position}")
#     yield from bps.mv(scaler0.preset_time, 0.1)
#     #scaler0.select_channels(["PD_USAXS"])
#     y_name = UPD_SIGNAL.chname.get()
#     scaler0.select_channels([y_name])
#     scaler0.channels.chan01.kind = Kind.config
#     #trim_plot_by_name(n=5)
#     # trim_plot_lines(bec, 5, stage, UPD_SIGNAL)


# def dx_posttune_hook():
#     stage = d_stage.x
#     logger.info(f"Tuning axis {stage.name}, final position is {stage.position}")
#     #TODO  need to find out how to get tune_ok from the lineup2
#     #if stage.tuner.tune_ok:
#     yield from bps.mv(terms.USAXS.DX0, stage.position)
#     scaler0.select_channels(None)


# d_stage.x.tuner = TuneAxis(
#     [scaler0],
#     d_stage.x,
#     signal_name=_getScalerSignalName_(scaler0, UPD_SIGNAL),
#     width_signal=axis_tune_range.dx,
# )
# d_stage.x.tuner.peak_choice = TUNE_METHOD_PEAK_CHOICE
# d_stage.x.tuner.num = 35
# d_stage.x.tuner.width = axis_tune_range.dx.get()     # 10

# -------------------------------------------


# def dy_pretune_hook():
#     stage = d_stage.y
#     logger.info(f"Tuning axis {stage.name}, current position is {stage.position}")
#     yield from bps.mv(scaler0.preset_time, 0.1)
#     #scaler0.select_channels(["PD_USAXS"])
#     y_name = UPD_SIGNAL.chname.get()
#     scaler0.select_channels([y_name])
#     scaler0.channels.chan01.kind = Kind.config
#     #trim_plot_by_name(n=5)
#     # trim_plot_lines(bec, 5, stage, UPD_SIGNAL)


# def dy_posttune_hook():
#     stage = d_stage.y
#     logger.info(f"Tuning axis {stage.name}, final position is {stage.position}")
#     #TODO figure out how to get tune_ok back
#     #if stage.tuner.tune_ok:
#     yield from bps.mv(terms.SAXS.dy_in, stage.position)
#     scaler0.select_channels(None)


# d_stage.y.tuner = TuneAxis(
#     [scaler0],
#     d_stage.y,
#     signal_name=_getScalerSignalName_(scaler0, UPD_SIGNAL),
#     width_signal=axis_tune_range.dy,
# )
# d_stage.y.tuner.peak_choice = TUNE_METHOD_PEAK_CHOICE
# d_stage.y.tuner.num = 35
# d_stage.y.tuner.width = axis_tune_range.dy.get()     # 10


class UsaxsDetectorStageDevice(MotorBundle):
    """USAXS detector stage"""

    x = Component(
        TunableEpicsMotor2,
        "usxAERO:m1",
        labels=(
            "detector",
            "tunable",
        ),
        tune_range=axis_tune_range.dx,
    )
    y = Component(
        TunableEpicsMotor2,
        "usxAERO:m2",
        labels=(
            "detector",
            "tunable",
        ),
        tune_range=axis_tune_range.dy,
    )


class UsaxsSampleStageDevice(MotorBundle):
    """USAXS sample stage"""

    x = Component(EpicsMotor, "usxAERO:m8", labels=("sample",))
    y = Component(EpicsMotor, "usxAERO:m9", labels=("sample",))


# class UsaxsCollimatorSideReflectionStageDevice(MotorBundle):
#    """USAXS Collimator (Monochromator) side-reflection stage  (unused)"""
#    #r = Component(EpicsMotor, 'usxLAX:xps:c0:m5', labels=("side_collimator",))
#    #t = Component(EpicsMotor, 'usxLAX:xps:c0:m3', labels=("side_collimator",))
#    x = Component(EpicsMotor, 'usxLAX:m58:c1:m1', labels=("side_collimator",))
#    y = Component(EpicsMotor, 'usxLAX:m58:c1:m2')
#    rp = Component(UsaxsMotorTunable, 'usxLAX:pi:c0:m3', labels=("side_collimator", "tunable",))
#  -------------------------------------------
# def msrp_pretune_hook():
#     stage = ms_stage.rp
#     logger.info(f"Tuning axis {stage.name}, current position is {stage.position}")
#     yield from bps.mv(scaler0.preset_time, 0.1)
#     y_name = TUNING_DET_SIGNAL.chname.get()
#     scaler0.select_channels([y_name])
#     scaler0.channels.chan01.kind = Kind.config
#     trim_plot_by_name(n=5)
#     # trim_plot_lines(bec, 5, stage, TUNING_DET_SIGNAL)


# def msrp_posttune_hook():
#     msg = "Tuning axis {}, final position is {}"
#     logger.info(msg.format(ms_stage.rp.name, ms_stage.rp.position))

#     if ms_stage.rp.tuner.tune_ok:
#         yield from bps.mv(terms.USAXS.msr_val_center, ms_stage.rp.position)

#     scaler0.select_channels(None)
#
# ms_stage.rp.pre_tune_method = msrp_pretune_hook
# ms_stage.rp.post_tune_method = msrp_posttune_hook

# -------------------------------------------

# ----A stage ---------------------------------------




    # a_stage.r.tuner = TuneAxis(
    #         [scaler0],
    #         a_stage.r,
    #         signal_name=_getScalerSignalName_(scaler0, UPD_SIGNAL),
    #         width_signal=axis_tune_range.ar,
    # )
    # a_stage.r.tuner.peak_choice = TUNE_METHOD_PEAK_CHOICE
    # a_stage.r.tuner.num = 35
    # a_stage.r.tuner.width = axis_tune_range.ar.get()     # -0.004

    # --ASRP-----------------------------------------

    # def asrp_pretune_hook():
    #     stage = as_stage.rp
    #     logger.info(f"Tuning axis {stage.name}, current position is {stage.position}")
    #     yield from bps.mv(scaler0.preset_time, 0.1)
    #     y_name = UPD_SIGNAL.chname.get()
    #     scaler0.select_channels([y_name])
    #     scaler0.channels.chan01.kind = Kind.config
    #     trim_plot_by_name(n=5)
    #     # trim_plot_lines(bec, 5, stage, UPD_SIGNAL)

    # def asrp_posttune_hook():
    #     msg = "Tuning axis {}, final position is {}"
    #     logger.info(msg.format(as_stage.rp.name, as_stage.rp.position))
    #     yield from bps.mv(terms.USAXS.asr_val_center, as_stage.rp.position)

    #     if as_stage.rp.tuner.tune_ok:
    #         pass    # #165: update center when/if we get a PV for that

    #     scaler0.select_channels(None)

    # # use I00 (if MS stage is used, use I0)
    # as_stage.rp.tuner = TuneAxis(
    #     [scaler0],
    #     as_stage.rp,
    #     signal_name=_getScalerSignalName_(scaler0, UPD_SIGNAL),
    #     width_signal=axis_tune_range.asrp,
    # )
    # as_stage.rp.tuner.peak_choice = TUNE_METHOD_PEAK_CHOICE
    # as_stage.rp.tuner.num = 21
    # as_stage.rp.tuner.width = axis_tune_range.asrp.get()     # 6

    # as_stage.rp.pre_tune_method = asrp_pretune_hook
    # as_stage.rp.post_tune_method = asrp_posttune_hook

    # # --A2RP-----------------------------------------

    # def a2rp_pretune_hook():
    #     stage = a_stage.r2p
    #     logger.info(f"Tuning axis {stage.name}, current position is {stage.position}")
    #     yield from bps.mv(scaler0.preset_time, 0.1)
    #     yield from bps.mv(scaler0.delay, 0.02)
    #     #scaler0.select_channels(["PD_USAXS"])
    #     y_name = UPD_SIGNAL.chname.get()
    #     scaler0.select_channels([y_name])
    #     scaler0.channels.chan01.kind = Kind.config
    #     #trim_plot_by_name(n=5)
    #     # trim_plot_lines(bec, 5, stage, UPD_SIGNAL)

    # def a2rp_posttune_hook():
    #     #
    #     # TODO: first, re-position piezo considering hysteresis?
    #     #
    #     msg = "Tuning axis {}, final position is {}"
    #     logger.info(msg.format(a_stage.r2p.name, a_stage.r2p.position))
    #     yield from bps.mv(scaler0.delay, 0.05)

    #     # if a_stage.r2p.tuner.tune_ok:
    #     #    pass    # #165: update center when/if we get a PV for that



class UsaxsAnalyzerStageDevice(MotorBundle):
    """USAXS Analyzer stage"""

    r = Component(
        TunableEpicsMotor2WTolerance,
        "usxAERO:m6",
        labels=("analyzer", "tunable"),
        tune_range=axis_tune_range.ar,
    )
    x = Component(EpicsMotor, "usxAERO:m4", labels=("analyzer",))
    y = Component(EpicsMotor, "usxAERO:m5", labels=("analyzer",))
    # z = Component(EpicsMotor, 'usxLAX:m58:c0:m7', labels=("analyzer",))
    r2p = Component(
        TunableEpicsMotor2,
        "usxLAX:pi:c0:m1",
        labels=("analyzer", "tunable"),
        tune_range=axis_tune_range.a2rp,
    )
    # rt = Component(EpicsMotor, 'usxLAX:m58:c1:m3', labels=("analyzer",))


# ------end of A stage-------------------------------------


# class UsaxsAnalyzerSideReflectionStageDevice(MotorBundle):
#    """USAXS Analyzer side-reflection stage (unused)"""
#    #r = Component(EpicsMotor, 'usxLAX:xps:c0:m6', labels=("analyzer",))
#    #t = Component(EpicsMotor, 'usxLAX:xps:c0:m4', labels=("analyzer",))
#    y = Component(EpicsMotor, 'usxLAX:m58:c1:m4', labels=("analyzer",))
#    rp = Component(TunableEpicsMotor2, 'usxLAX:pi:c0:m4', labels=("analyzer", "tunable"))


class SaxsDetectorStageDevice(MotorBundle):
    """SAXS detector stage"""

    x = Component(EpicsMotor, "usxAERO:m13", labels=("saxs",))
    y = Component(EpicsMotor, "usxAERO:m15", labels=("saxs",))
    z = Component(EpicsMotor, "usxAERO:m14", labels=("saxs",))


class GuardSlitsStageDevice(MotorBundle):
    """Guqard Slits stage"""

    x = Component(EpicsMotor, "usxLAX:m58:c0:m7", labels=("guard_slits",))
    y = Component(EpicsMotor, "usxLAX:m58:c0:m6", labels=("guard_slits",))




