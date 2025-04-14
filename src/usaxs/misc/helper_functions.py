def operations_in_12ide():
    """
    returns True if allowed to use X-ray beam in 12-ID-E station
    """
    # return diagnostics.PSS.b_station_enabled
    return True
    # return False


def operations_on():

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

        a_shutter_autoopen = EpicsSignal("12ida2:AShtr:Enable", name="a_shutter_autoopen")

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
    if isinstance(scaler, ScalerCH):
        return signal.chname.get()
    elif isinstance(scaler, EpicsScaler):
        return signal.name

def ar_pretune_hook():
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
