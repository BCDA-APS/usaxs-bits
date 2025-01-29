
"""
general parameters and terms
"""

__all__ = [
    'terms',
    ]

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

from ophyd import Component, Device, Signal
from ophyd import EpicsSignal
import time

from .amplifiers import upd_controls
from ..framework import sd

#TODO :  resolve issues with LAX PV database 

class FlyScanParameters(Device):
    """FlyScan values"""
    number_points = Component(EpicsSignal, "usxLAX:USAXS:FS_NumberOfPoints")
    scan_time = Component(EpicsSignal, "usxLAX:USAXS:FS_ScanTime")
    use_flyscan = Component(EpicsSignal, "usxLAX:USAXS:UseFlyscan")
    #asrp_calc_SCAN = Component(EpicsSignal, "usxLAX:userStringCalc2.SCAN")
    order_number = Component(EpicsSignal, "usxLAX:USAXS:FS_OrderNumber")
    elapsed_time = Component(EpicsSignal, "usxLAX:USAXS:FS_ElapsedTime")

    setpoint_up = Component(Signal, value=6000)     # decrease range
    setpoint_down = Component(Signal, value=850000)    # increase range


class PreUsaxsTuneParameters(Device):
    """preUSAXStune handling"""
    num_scans_last_tune = Component(EpicsSignal, "usxLAX:NumScansFromLastTune")
    epoch_last_tune = Component(EpicsSignal, "usxLAX:EPOCHTimeOfLastTune")
    req_num_scans_between_tune = Component(EpicsSignal, "usxLAX:ReqNumScansBetweenTune")
    req_time_between_tune = Component(EpicsSignal, "usxLAX:ReqTimeBetweenTune")
    run_tune_on_qdo = Component(EpicsSignal, "usxLAX:RunPreUSAXStuneOnQdo")
    run_tune_next = Component(EpicsSignal, "usxLAX:RunPreUSAXStuneNext")
    sx = Component(EpicsSignal, "usxLAX:preUSAXStuneSX")
    sy = Component(EpicsSignal, "usxLAX:preUSAXStuneSY")
    use_specific_location = Component(EpicsSignal, "usxLAX:UseSpecificTuneLocation")

    @property
    def needed(self):
        """
        is a tune needed?

        EXAMPLE::

            if terms.preUSAXStune.needed:
                yield from preUSAXStune()
                # TODO: and then reset terms as approriate

        """
        result = self.run_tune_next.get()
        # TODO: next test if not in SAXS or WAXS mode
        result = result or self.num_scans_last_tune.get()  > self.req_num_scans_between_tune.get()
        time_limit = self.epoch_last_tune.get() + self.req_time_between_tune.get()
        result = result or time.time() > time_limit
        self.run_tune_next.put(0)
        return result


class Parameters_Al_Ti_Filters(Device):
    Al = Component(EpicsSignal,  "Al_Filter")
    Ti = Component(EpicsSignal,  "Ti_Filter")


class Parameters_Al_Ti_Filters_Imaging(Device):
    # because there is one in every crowd!
    Al = Component(EpicsSignal,  "Al_Filters")
    Ti = Component(EpicsSignal,  "Ti_Filters")


class GeneralParametersCCD(Device):
    "part of GeneralParameters Device"
    dx = Component(EpicsSignal, "dx")
    dy = Component(EpicsSignal, "dy")


class GeneralUsaxsParametersBlackfly(Device):
    """part of GeneralParameters Device"""
    dx = Component(EpicsSignal, "dx")
    dy = Component(EpicsSignal, "dy")
    filters = Component(Parameters_Al_Ti_Filters, "")

class GeneralUsaxsParametersDiode(Device):
    "part of GeneralParameters Device"
    dx = Component(EpicsSignal, "Diode_dx")
    dy = Component(EpicsSignal, "Diode_dy")
    upd_size = Component(EpicsSignal, "UPDsize")


class GeneralUsaxsParametersCenters(Device):
    "part of GeneralParameters Device"
    AR = Component(EpicsSignal,  "ARcenter")
    #ASR = Component(EpicsSignal, "ASRcenter")
    MR = Component(EpicsSignal,  "MRcenter")
    #MSR = Component(EpicsSignal, "MSRcenter")


class Parameters_transmission(Device):
    # measure transmission in USAXS using pin diode
    measure = Component(EpicsSignal, "usxLAX:USAXS:TR_MeasurePinTrans")

    # Ay to hit pin diode
    ax = Component(EpicsSignal, "usxLAX:USAXS:TR_AxPosition")
    count_time = Component(EpicsSignal, "usxLAX:USAXS:TR_MeasurementTime")
    diode_counts = Component(EpicsSignal, "usxLAX:USAXS:TR_pinCounts")
    diode_gain = Component(EpicsSignal, "usxLAX:USAXS:TR_pinGain") # I00 amplifier
    I0_counts = Component(EpicsSignal, "usxLAX:USAXS:TR_I0Counts")
    I0_gain = Component(EpicsSignal, "usxLAX:USAXS:TR_I0Gain")


class Parameters_USAXS(Device):
    """internal values shared with EPICS"""
    AX0 = Component(EpicsSignal,                      "usxLAX:ax_in")
    DX0 = Component(EpicsSignal,                      "usxLAX:USAXS:Diode_dx")
    ASRP0 = Component(EpicsSignal,                    "usxLAX:USAXS:ASRcenter")
    SAD = Component(EpicsSignal,                      "usxLAX:USAXS:SAD")
    SDD = Component(EpicsSignal,                      "usxLAX:USAXS:SDD")
    ar_val_center = Component(EpicsSignal,            "usxLAX:USAXS:ARcenter")
    #asr_val_center = Component(EpicsSignal,           "usxLAX:USAXS:ASRcenter")

    #	ASRP_DEGREES_PER_VDC = 0.0059721     # measured by JI October 9, 2006 during setup at 32ID. Std Dev 4e-5
    #  	ASRP_DEGREES_PER_VDC = 0.00059721     # changed by factor of 10 to accomodate new PIUU controller, where we drive directly in V of high voltage.
    # Measured by JIL on 6/4/2016, average of two measured numbers
    #asrp_degrees_per_VDC = Component(Signal,          value=(0.000570223 + 0.000585857)/2)

    blackfly = Component(GeneralUsaxsParametersBlackfly, "usxLAX:USAXS:BlackFly_")

    center = Component(GeneralUsaxsParametersCenters, "usxLAX:USAXS:")
    ccd = Component(GeneralParametersCCD,             "usxLAX:USAXS:CCD_")
    diode = Component(GeneralUsaxsParametersDiode,    "usxLAX:USAXS:")
    img_filters = Component(Parameters_Al_Ti_Filters, "usxLAX:USAXS:Img_")
    finish = Component(EpicsSignal,                   "usxLAX:USAXS:Finish")
    is2DUSAXSscan = Component(EpicsSignal,            "usxLAX:USAXS:is2DUSAXSscan")
    motor_prescaler_wait = Component(EpicsSignal,     "usxLAX:USAXS:Prescaler_Wait")
    mr_val_center = Component(EpicsSignal,            "usxLAX:USAXS:MRcenter")
    #msr_val_center = Component(EpicsSignal,           "usxLAX:USAXS:MSRcenter")
    num_points = Component(EpicsSignal,               "usxLAX:USAXS:NumPoints")
    sample_y_step = Component(EpicsSignal,            "usxLAX:USAXS:Sample_Y_Step")
    scan_filters = Component(Parameters_Al_Ti_Filters, "usxLAX:USAXS:Scan_")
    scanning = Component(EpicsSignal,                 "usxLAX:USAXS:scanning")
    start_offset = Component(EpicsSignal,             "usxLAX:USAXS:StartOffset")
    uaterm = Component(EpicsSignal,                   "usxLAX:USAXS:UATerm")
    usaxs_minstep = Component(EpicsSignal,            "usxLAX:USAXS:MinStep")
    usaxs_time = Component(EpicsSignal,               "usxLAX:USAXS:CountTime")
    useDynamicTime = Component(Signal,                value=True)
    useMSstage = Component(Signal,                    value=False)
    useSBUSAXS = Component(Signal,                    value=False)

    retune_needed = Component(Signal, value=False)     # does not *need* an EPICS PV

    # TODO: these are particular to the amplifier
    setpoint_up = Component(Signal, value=4000)     # decrease range
    setpoint_down = Component(Signal, value=650000)    # increase range

    transmission = Component(Parameters_transmission)

    def UPDRange(self):
        return upd_controls.auto.lurange.get()  # TODO: check return value is int


class Parameters_SBUSAXS(Device):
    pass


class Parameters_SAXS(Device):
    z_in = Component(EpicsSignal, "usxLAX:SAXS_z_in")
    z_out = Component(EpicsSignal, "usxLAX:SAXS_z_out")
    z_limit_offset = Component(EpicsSignal, "usxLAX:SAXS_z_limit_offset")

    x_in = Component(EpicsSignal, "usxLAX:SAXS_x_in")
 
    y_in = Component(EpicsSignal, "usxLAX:SAXS_y_in")
    y_out = Component(EpicsSignal, "usxLAX:SAXS_y_out")
    y_limit_offset = Component(EpicsSignal, "usxLAX:SAXS_y_limit_offset")

    ay_in = Component(EpicsSignal, "usxLAX:ay_in")

    ax_in = Component(EpicsSignal, "usxLAX:ax_in")
    ax_out = Component(EpicsSignal, "usxLAX:ax_out")
    ax_limit_offset = Component(EpicsSignal, "usxLAX:ax_limit_offset")

    dy_in = Component(EpicsSignal, "usxLAX:USAXS:Diode_dy")

    dx_in = Component(EpicsSignal, "usxLAX:USAXS:Diode_dx")     #deprecated, do not use, use USAXS:Diode.dx
    dx_out = Component(EpicsSignal, "usxLAX:USAXS:Diode_dx_out")
    dx_limit_offset = Component(EpicsSignal, "usxLAX:USAXS:Diode_dx_limit_offset")

    usaxs_h_size = Component(EpicsSignal, "usxLAX:USAXS_hslit_ap")
    usaxs_v_size = Component(EpicsSignal, "usxLAX:USAXS_vslit_ap")
    v_size = Component(EpicsSignal, "usxLAX:SAXS_vslit_ap")
    h_size = Component(EpicsSignal, "usxLAX:SAXS_hslit_ap")

    usaxs_guard_h_size = Component(EpicsSignal, "usxLAX:USAXS_hgslit_ap")
    usaxs_guard_v_size = Component(EpicsSignal, "usxLAX:USAXS_vgslit_ap")
    guard_v_size = Component(EpicsSignal, "usxLAX:SAXS_vgslit_ap")
    guard_h_size = Component(EpicsSignal, "usxLAX:SAXS_hgslit_ap")

    filters = Component(Parameters_Al_Ti_Filters, "usxLAX:SAXS:Exp_")

    base_dir = Component(EpicsSignal, "usxLAX:SAXS:directory", string=True)

    UsaxsSaxsMode = Component(EpicsSignal, "usxLAX:SAXS:USAXSSAXSMode", put_complete=True)
    num_images = Component(EpicsSignal, "usxLAX:SAXS:NumImages")
    acquire_time = Component(EpicsSignal, "usxLAX:SAXS:AcquireTime")
    collecting = Component(EpicsSignal, "usxLAX:collectingSAXS")


class Parameters_SAXS_WAXS(Device):
    """
    terms used by both SAXS & WAXS
    """
    start_exposure_time = Component(EpicsSignal, "usxLAX:SAXS:StartExposureTime")
    end_exposure_time = Component(EpicsSignal, "usxLAX:SAXS:EndExposureTime")

    diode_gain = Component(EpicsSignal, "usxLAX:SAXS:SAXS_TrPDgain")
    diode_transmission = Component(EpicsSignal, "usxLAX:SAXS:SAXS_TrPD")
    I0_gain = Component(EpicsSignal, "usxLAX:SAXS:SAXS_TrI0gain")
    I0_transmission = Component(EpicsSignal, "usxLAX:SAXS:SAXS_TrI0")

    # this is Io value from gates scalar in LAX for Nexus file
    I0 = Component(EpicsSignal, "usxLAX:SAXS:I0")


class Parameters_WAXS(Device):
    x_in = Component(EpicsSignal, "usxLAX:WAXS_x_in")
    x_out = Component(EpicsSignal, "usxLAX:WAXS_x_out")
    x_limit_offset = Component(EpicsSignal, "usxLAX:WAXS_x_limit_offset")
    filters = Component(Parameters_Al_Ti_Filters, "usxLAX:WAXS:Exp_")
    base_dir = Component(EpicsSignal, "usxLAX:WAXS:directory", string=True)
    num_images = Component(EpicsSignal, "usxLAX:WAXS:NumImages")
    acquire_time = Component(EpicsSignal, "usxLAX:WAXS:AcquireTime")
    collecting = Component(EpicsSignal, "usxLAX:collectingWAXS")


class Parameters_Radiography(Device):
    pass


class Parameters_Imaging(Device):
    image_key = Component(EpicsSignal, "usxLAX:USAXS_Img:ImageKey")
    # 0=image, 1=flat field, 2=dark field

    exposure_time = Component(EpicsSignal, "usxLAX:USAXS_Img:ExposureTime")

    tomo_rotation_angle = Component(EpicsSignal, "usxLAX:USAXS_Img:Tomo_Rot_Angle")
    I0 = Component(EpicsSignal, "usxLAX:USAXS_Img:Img_I0_value")
    I0_gain = Component(EpicsSignal, "usxLAX:USAXS_Img:Img_I0_gain")

    ax_in = Component(EpicsSignal, "usxLAX:USAXS_Img:ax_in")
    waxs_x_in = Component(EpicsSignal, "usxLAX:USAXS_Img:waxs_x_in")

    flat_field = Component(EpicsSignal, "usxLAX:USAXS_Img:FlatFieldImage")
    dark_field = Component(EpicsSignal, "usxLAX:USAXS_Img:DarkFieldImage")
    title = Component(EpicsSignal, "usxLAX:USAXS_Img:ExperimentTitle", string=True)

    h_size = Component(EpicsSignal, "usxLAX:USAXS_Img:ImgHorApperture")
    v_size = Component(EpicsSignal, "usxLAX:USAXS_Img:ImgVertApperture")
    guard_h_size = Component(EpicsSignal, "usxLAX:USAXS_Img:ImgGuardHorApperture")
    guard_v_size = Component(EpicsSignal, "usxLAX:USAXS_Img:ImgGuardVertApperture")

    filters = Component(Parameters_Al_Ti_Filters_Imaging, "usxLAX:USAXS_Img:Img_")
    filter_transmission = Component(EpicsSignal, "usxLAX:USAXS_Img:Img_FilterTransmission")


class Parameters_OutOfBeam(Device):
    pass


# keep in sync with usaxs_support.heater_profile_process
class Parameters_HeaterProcess(Device):
    # tell heater process to exit
    linkam_exit = Component(EpicsSignal, "usxLAX:bit14")

    # heater process increments at 10 Hz
    linkam_pulse = Component(EpicsSignal, "usxLAX:long16")

    # heater process is ready
    linkam_ready = Component(EpicsSignal, "usxLAX:bit15")

    # heater process should start
    linkam_trigger = Component(EpicsSignal, "usxLAX:bit16")


class GeneralParameters(Device):
    """
    cache of parameters to share with/from EPICS
    """
    USAXS = Component(Parameters_USAXS)
    SBUSAXS = Component(Parameters_SBUSAXS)
    SAXS = Component(Parameters_SAXS)
    SAXS_WAXS = Component(Parameters_SAXS_WAXS)
    WAXS = Component(Parameters_WAXS)
    Radiography = Component(Parameters_Radiography)
    Imaging = Component(Parameters_Imaging)
    OutOfBeam = Component(Parameters_OutOfBeam)

    PauseBeforeNextScan = Component(EpicsSignal, "usxLAX:PauseBeforeNextScan")
    StopBeforeNextScan = Component(EpicsSignal,  "usxLAX:StopBeforeNextScan")

    # consider refactoring
    FlyScan = Component(FlyScanParameters)
    preUSAXStune = Component(PreUsaxsTuneParameters)

    HeaterProcess = Component(Parameters_HeaterProcess)


# NOTE: ALL referenced PVs **MUST** exist or get() operations will fail!
terms = GeneralParameters(name="terms")
sd.baseline.append(terms)
