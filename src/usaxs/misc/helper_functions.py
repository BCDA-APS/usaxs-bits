"""Helper functions for the USAXS instrument.

This module provides various utility functions for controlling and managing
the USAXS instrument, including shutter control, temperature control, and
stage movement.
"""

import logging

logger = logging.getLogger(__name__)


def plan_slit_ok():
    def set_size(
        self, *args: Any, h: Optional[float] = None, v: Optional[float] = None
    ) -> Generator[Any, None, None]:
        """move the slits to the specified size"""
        if h is None:
            raise ValueError("must define horizontal size")
        if v is None:
            raise ValueError("must define vertical size")
        # move_motors(self.h_size, h, self.v_size, v)
        yield from bps.mv(
            self.h_size,
            h,
            self.v_size,
            v,
        )

    @property
    def h_gap_ok(self) -> bool:
        """
        Check if the horizontal gap is within tolerance.

        Returns:
            bool: True if the horizontal gap is within tolerance, False otherwise.
        """
        gap = self.outb.position - self.inb.position
        return abs(gap - terms.SAXS.guard_h_size.get()) <= self.gap_tolerance

    @property
    def v_h_gap_ok(self) -> bool:
        """
        Check if the vertical gap is within tolerance.

        Returns:
            bool: True if the vertical gap is within tolerance, False otherwise.
        """
        gap = self.top.position - self.bot.position
        return abs(gap - terms.SAXS.guard_v_size.get()) <= self.gap_tolerance

    @property
    def gap_ok(self) -> bool:
        """
        Check if both horizontal and vertical gaps are within tolerance.

        Returns:
            bool: True if both gaps are within tolerance, False otherwise.
        """
        return self.h_gap_ok and self.v_h_gap_ok

    def process_motor_records(self) -> Generator[Any, None, None]:
        """
        Process motor records to update their status.

        Yields:
            Generator: A generator that yields control flow back to the caller.
        """
        yield from bps.mv(self.top.process_record, 1)
        yield from bps.mv(self.outb.process_record, 1)
        yield from bps.sleep(0.05)
        yield from bps.mv(self.bot.process_record, 1)
        yield from bps.mv(self.inb.process_record, 1)
        yield from bps.sleep(0.05)


def UPDRange(self) -> int:
    """
    Get the UPD range value.

    Returns:
        int: The UPD range value
    """
    return upd_controls.auto.lurange.get()  # TODO: check return value is int


def operations_in_12ide():
    """Check if operations are in 12-ID-E station.

    This function determines whether the current operations are taking place
    in the 12-ID-E station by checking various parameters and settings.

    Returns:
        bool: True if operations are in 12-ID-E, False otherwise
    """
    # return diagnostics.PSS.b_station_enabled
    return True
    # return False


def operations_on():
    """Check if operations are enabled and set up shutters.

    This function checks if APS is in user operations mode and 12-ID-E station
    is operating. Based on the status, it initializes the appropriate shutter
    objects (real or simulated).

    Returns:
        tuple: A tuple containing the initialized shutter objects
    """
    if aps.inUserOperations and operations_in_12ide():
        FE_shutter = My12IdPssShutter(
            # 12id:shutter0_opn and 12id:shutter0_cls
            "A shutter",
            state_pv="PA:12ID:STA_A_FES_OPEN_PL",
            name="FE_shutter",
        )

        mono_shutter = ApsPssShutterWithStatus(
            # 20id:shutter1_opn and 20id:shutter1_cls
            "E shutter",
            state_pv="PA:12ID:STA_C_SCS_OPEN_PL",
            name="mono_shutter",
            open_pv="12ida2:rShtrC:Open",
            close_pv="12ida2:rShtrC:Close",
        )

        # usaxs_shutter = EpicsOnOffShutter(
        #    "usxLAX:userTran3.A",
        #    name="usaxs_shutter")

        usaxs_shutter = ApsPssShutter(
            "Mono beam shutter",
            name="usaxs_shutter",
            open_pv="12idc:uniblitz:shutter:open",
            close_pv="12idc:uniblitz:shutter:close",
        )

        a_shutter_autoopen = EpicsSignal(
            "12ida2:AShtr:Enable", name="a_shutter_autoopen"
        )

    else:
        logger.warning("!" * 30)
        if operations_in_12ide():
            logger.warning("Session started when APS not operating.")
        else:
            logger.warning("Session started when 12ID-E is not operating.")
        logger.warning("Using simulators for all shutters.")
        logger.warning("!" * 30)
        FE_shutter = SimulatedApsPssShutterWithStatus(name="FE_shutter")
        mono_shutter = SimulatedApsPssShutterWithStatus(name="mono_shutter")
        usaxs_shutter = SimulatedApsPssShutterWithStatus(name="usaxs_shutter")
        a_shutter_autoopen = Signal(name="a_shutter_autoopen", value=0)

    ti_filter_shutter = usaxs_shutter  # alias
    ti_filter_shutter.delay_s = 0.2  # shutter needs some recovery time

    # ccd_shutter = EpicsOnOffShutter("usxRIO:Galil2Bo0_CMD", name="ccd_shutter")
    ccd_shutter = usaxs_shutter  # alias

    connect_delay_s = 1
    while not mono_shutter.pss_state.connected:
        logger.info(f"Waiting {connect_delay_s}s for mono shutter PV to connect")
        time.sleep(connect_delay_s)


def linkam_setup():
    """Set up the Linkam temperature controller.

    This function initializes the Linkam temperature controller, sets up
    tolerances, and configures engineering units.
    """
    try:
        linkam_tc1.wait_for_connection()
    except Exception:
        warnings.warn(f"Linkam controller {linkam_tc1.name} not connected.")

    if linkam_tc1.connected:
        # set tolerance for "in position" (Python term, not an EPICS PV)
        # note: done = |readback - setpoint| <= tolerance
        linkam_tc1.temperature.tolerance.put(1.0)

        # sync the "inposition" computation
        linkam_tc1.temperature.cb_readback()

        # easy access to the engineering units
        linkam_tc1.units.put(linkam_tc1.temperature.readback.metadata["units"])
        linkam_tc1.ramp = linkam_tc1.ramprate


def _getScalerSignalName_(scaler, signal):
    """Get the name of a scaler signal.

    Args:
        scaler: The scaler device (ScalerCH or EpicsScaler)
        signal: The signal to get the name for

    Returns:
        str: The name of the signal
    """
    if isinstance(scaler, ScalerCH):
        return signal.chname.get()
    elif isinstance(scaler, EpicsScaler):
        return signal.name


def ar_pretune_hook():
    """Prepare for tuning the AR axis.

    This function sets up the scaler and other parameters before
    tuning the AR axis.

    Yields:
        Generator: A sequence of plan messages
    """
    stage = a_stage.r
    logger.info(f"Tuning axis {stage.name}, current position is {stage.position}")
    yield from bps.mv(scaler0.preset_time, 0.1)
    # scaler0.select_channels(["PD_USAXS"])
    y_name = UPD_SIGNAL.chname.get()
    scaler0.select_channels([y_name])
    scaler0.channels.chan01.kind = Kind.config
    # trim_plot_by_name(n=5)
    # trim_plot_lines(bec, 5, stage, UPD_SIGNAL)


def ar_posttune_hook():
    """Clean up after tuning the AR axis.

    This function updates parameters and performs cleanup after
    tuning the AR axis is complete.

    Yields:
        Generator: A sequence of plan messages
    """
    msg = "Tuning axis {}, final position is {}"
    logger.info(msg.format(a_stage.r.name, a_stage.r.position))
    # TODO need to verify how to get tube_ok signal from new tuning
    if a_stage.r.tuner.tune_ok:
        yield from bps.mv(terms.USAXS.ar_val_center, a_stage.r.position)
        # remember the Q calculation needs a new 2theta0
        # use the current AR encoder position
        yield from bps.mv(
            usaxs_q_calc.channels.B.input_value,
            terms.USAXS.ar_val_center.get(),
            a_stage.r,
            terms.USAXS.ar_val_center.get(),
        )
    scaler0.select_channels(None)
    scaler0.select_channels(None)


def setup_shutter_callbacks():
    """Set up callbacks for the shutter control system.

    This function initializes the shutter control system and sets up
    the necessary callbacks for monitoring shutter status.

    Returns:
        tuple: A tuple containing the initialized shutter objects
    """


def linkam_tc1_wait_for_stability():
    """Wait for the Linkam temperature controller to stabilize.

    This function monitors the Linkam TC1 temperature controller and waits
    until the temperature has stabilized at the target value.

    Returns:
        bool: True if temperature stabilized, False if timed out
    """


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
    controls: List[DetectorAmplifierAutorangeDevice],
    shutter: Optional[Any] = None,
    count_time: float = 0.05,
    max_iterations: int = 9,
) -> Generator[Any, None, Any]:
    """Bluesky plan: autoscale detector amplifiers simultaneously.

    Parameters
    ----------
    controls : List[DetectorAmplifierAutorangeDevice]
        List (or tuple) of ``DetectorAmplifierAutorangeDevice``
    shutter : Optional[Any], optional
        Shutter device to control, by default None
    count_time : float, optional
        Time to count for each measurement, by default 0.05
    max_iterations : int, optional
        Maximum number of iterations to try, by default 9

    Returns
    -------
    Generator[Any, None, Any]
        Bluesky plan
    """
    assert isinstance(controls, (tuple, list)), "controls must be a list"
    scaler_dict = group_controls_by_scaler(controls)

    if shutter is not None:
        yield from bps.mv(shutter, "open")

    for control_list in scaler_dict.values():
        # do amplifiers in sequence, in case same hardware used multiple times
        if len(control_list) > 0:
            # logger.info(
            #    "Autoscaling amplifier for: %s",
            #    control_list[0].nickname
            # )
            try:
                yield from _scaler_autoscale_(
                    control_list,
                    count_time=count_time,
                    max_iterations=max_iterations,
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


def _scaler_autoscale_(controls, count_time=0.05, max_iterations=9):
    """plan: internal: autoscale amplifiers for signals sharing a common scaler"""
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


_last_autorange_gain_ = OrderedDefaultDict(dict)
