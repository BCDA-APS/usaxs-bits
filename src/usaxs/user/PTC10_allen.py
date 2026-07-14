"""
PTC10 plan for user Allen.

Collects data at 5 positions on sample, cycling through all positions repeatedly
for a specified hold time at a fixed temperature. Gas parameter is included in the
sample name.

Reload by:
    %run -im usaxs.user.PTC10_allen

Debug mode:
    ptc10_debug.put(True)   # test without data collection
    ptc10_debug.put(False)  # real run
"""

import logging
import time

import logging
import time

from bluesky import plan_stubs as bps
from apsbits.core.instrument_init import oregistry
from ophyd import Signal

from usaxs.plans.plans_user_facing import saxsExp, waxsExp
from usaxs.plans.plans_usaxs import USAXSscan
from usaxs.plans.command_list import after_command_list, before_command_list, sync_order_numbers
from usaxs.utils.obsidian import appendToMdFile

logger = logging.getLogger(__name__)
logger.info(__file__)

ptc10 = oregistry["ptc10"]
ptc10_debug = Signal(name="ptc10_debug", value=False)

# List of 5 positions: [pos_X_mm, pos_Y_mm, thickness_mm, "position_name"]
PositionList = [
import time

    [0.0, 0.0, 1.3, "PLCN1"],
    [0.5, 0.0, 1.3, "PLCN2"],
    [1.0, 0.0, 1.3, "PLCN3"],
    [1.5, 0.0, 1.3, "PLCN4"],
    [2.0, 0.0, 1.3, "PLCN5"],
]

import time


def setheaterOn():
    """Switch heater on."""
    yield from bps.mv(
        ptc10.enable, "On",
        ptc10.pid.pidmode, "On",
    )
    """Switch heater on."""
    yield from bps.mv(
    """Switch heater on."""
    yield from bps.mv(


def setheaterOff():
    """Switch heater off."""

def setheaterOn():
    yield from bps.mv(
        ptc10.enable, "Off",
        ptc10.pid.pidmode, "Off",
    )


def PTC10_allen_holdtime(temp1, time1_min, gas, md={}):
    """
    Cycle through 5 sample positions at fixed temperature for specified time.

    Collects USAXS/SAXS/WAXS at each position, checks elapsed time after each
    complete cycle (all 5 positions), and stops when time1_min is exceeded.

    Sample name format: {sampleName}_{gas}_{temp}C_{elapsed_min}min

    Parameters
    ----------
    temp1 : float
        Target temperature in °C (e.g., 300)
    time1_min : float
        Total time to collect data at this temperature (in minutes)
    gas : str
        Gas atmosphere identifier for sample name (e.g., "N2", "air", "vacuum")
    md : dict, optional
        Additional metadata to include in scans

    Example
    -------
    RE(PTC10_allen_holdtime(300, 60, "N2"))
        Ramp to 300 C, cycle 5 positions for 1 hour, names: OPCC1_N2_300C_0min, etc.
    """

    def getSampleName(pos_name, elapsed_min):
        """Construct sample name with gas, temperature, and elapsed time."""
        return f"{pos_name}_{gas}_{ptc10.position:.0f}C_{elapsed_min:.0f}min"

    def collectAllThree(pos_X, pos_Y, thickness, pos_name, isDebugMode):
        """Collect USAXS/SAXS/WAXS at this position."""
        if not isDebugMode:
            yield from sync_order_numbers()
            elapsed_min = (time.time() - t0) / 60
            sample_mod = getSampleName(pos_name, elapsed_min)
            md["title"] = sample_mod
            yield from USAXSscan(pos_X, pos_Y, thickness, sample_mod, md={})

            elapsed_min = (time.time() - t0) / 60
            sample_mod = getSampleName(pos_name, elapsed_min)
            md["title"] = sample_mod
            yield from saxsExp(pos_X, pos_Y, thickness, sample_mod, md={})

            elapsed_min = (time.time() - t0) / 60
            sample_mod = getSampleName(pos_name, elapsed_min)
            md["title"] = sample_mod
            yield from waxsExp(pos_X, pos_Y, thickness, sample_mod, md={})
        else:
            elapsed_min = (time.time() - t0) / 60
            sample_mod = getSampleName(pos_name, elapsed_min)
            logger.info(f"[DEBUG] {sample_mod}")
            yield from bps.sleep(20)

    # Check debug mode
    isDebugMode = ptc10_debug.get()

    # Startup
    if not isDebugMode:
        yield from before_command_list()
    else:
        logger.info("DEBUG: Skipping before_command_list()")
        yield from bps.sleep(5)

    # Log experiment
    appendToMdFile("  ***  ")
    appendToMdFile(f"PTC10_allen_holdtime: {temp1} C for {time1_min} min (gas: {gas})")
    logger.info(f"Ramping to {temp1} C")

    # Ramp to target temperature
    yield from bps.mv(ptc10.temperature.setpoint, temp1)
    yield from setheaterOn()

    # Wait for temperature to stabilize
    while not ptc10.temperature.inposition:
        yield from bps.sleep(5)
        logger.info(f"Still ramping to {temp1} C...")

    logger.info(f"Reached {temp1} C, starting {time1_min} min collection cycle")
    appendToMdFile(f"Reached {temp1} C, starting {time1_min} min collection cycle")

    # Reset timer for hold period
    t0 = time.time()

    # Main data collection loop — cycle through positions, check time after each cycle
    while time.time() - t0 < time1_min * 60:
        for pos_X, pos_Y, thickness, pos_name in PositionList:
            elapsed_min = (time.time() - t0) / 60
            if elapsed_min >= time1_min:
                logger.info(f"Time limit reached ({elapsed_min:.1f} min ≥ {time1_min} min), stopping")
                break
            yield from collectAllThree(pos_X, pos_Y, thickness, pos_name, isDebugMode)

        elapsed_min = (time.time() - t0) / 60
        logger.info(f"Completed cycle, elapsed time: {elapsed_min:.1f} / {time1_min} min")

    # Shutdown
    yield from setheaterOff()

    if not isDebugMode:
        yield from after_command_list()
    else:
        logger.info("DEBUG: Skipping after_command_list()")

    appendToMdFile(f"Finished PTC10_allen_holdtime")
    appendToMdFile("  ***  ")
    logger.info("Plan complete")


def PTC10_allen_holdtime_heater_on(temp1, time1_min, gas, md={}):
    """
    PART A: Cycle through 5 sample positions at fixed temperature, leave heater ON.

    Same as PTC10_allen_holdtime but does NOT turn off the heater at the end.
    User will manually enter the hutch and change the gas while PTC10 maintains
    the set temperature. Then run PTC10_allen_cooling_and_collect for part B.

    Collects USAXS/SAXS/WAXS at each position, checks elapsed time after each
    complete cycle (all 5 positions), and stops when time1_min is exceeded.

    Sample name format: {pos_name}_{gas}_{temp}C_{elapsed_min}min

    Parameters
    ----------
    temp1 : float
        Target temperature in °C (e.g., 300)
    time1_min : float
        Total time to collect data at this temperature (in minutes)
    gas : str
        Gas atmosphere identifier for sample name (e.g., "N2", "air", "vacuum")
    md : dict, optional
        Additional metadata to include in scans

    Example
    -------
    RE(PTC10_allen_holdtime_heater_on(300, 60, "N2"))
        Ramp to 300 C, cycle 5 positions for 1 hour, leave heater on.
        User then manually changes gas in hutch, then runs part B plan.
    """

    def getSampleName(pos_name, elapsed_min):
        """Construct sample name with gas, temperature, and elapsed time."""
        return f"{pos_name}_{gas}_{ptc10.position:.0f}C_{elapsed_min:.0f}min"

    def collectAllThree(pos_X, pos_Y, thickness, pos_name, isDebugMode):
        """Collect USAXS/SAXS/WAXS at this position."""
        if not isDebugMode:
            yield from sync_order_numbers()
            elapsed_min = (time.time() - t0) / 60
            sample_mod = getSampleName(pos_name, elapsed_min)
            md["title"] = sample_mod
            yield from USAXSscan(pos_X, pos_Y, thickness, sample_mod, md={})

            elapsed_min = (time.time() - t0) / 60
            sample_mod = getSampleName(pos_name, elapsed_min)
            md["title"] = sample_mod
            yield from saxsExp(pos_X, pos_Y, thickness, sample_mod, md={})

            elapsed_min = (time.time() - t0) / 60
            sample_mod = getSampleName(pos_name, elapsed_min)
            md["title"] = sample_mod
            yield from waxsExp(pos_X, pos_Y, thickness, sample_mod, md={})
        else:
            elapsed_min = (time.time() - t0) / 60
            sample_mod = getSampleName(pos_name, elapsed_min)
            logger.info(f"[DEBUG] {sample_mod}")
            yield from bps.sleep(20)

    # Check debug mode
    isDebugMode = ptc10_debug.get()

    # Startup
    if not isDebugMode:
        yield from before_command_list()
    else:
        logger.info("DEBUG: Skipping before_command_list()")
        yield from bps.sleep(5)

    # Log experiment
    appendToMdFile("  ***  ")
    appendToMdFile(f"PTC10_allen_holdtime_heater_on (PART A): {temp1} C for {time1_min} min (gas: {gas})")
    logger.info(f"Ramping to {temp1} C")

    # Ramp to target temperature
    yield from bps.mv(ptc10.temperature.setpoint, temp1)
    yield from setheaterOn()

    # Wait for temperature to stabilize
    while not ptc10.temperature.inposition:
        yield from bps.sleep(5)
        logger.info(f"Still ramping to {temp1} C...")

    logger.info(f"Reached {temp1} C, starting {time1_min} min collection cycle")
    appendToMdFile(f"Reached {temp1} C, starting {time1_min} min collection cycle")

    # Reset timer for hold period
    t0 = time.time()

    # Main data collection loop — cycle through positions, check time after each cycle
    while time.time() - t0 < time1_min * 60:
        for pos_X, pos_Y, thickness, pos_name in PositionList:
            elapsed_min = (time.time() - t0) / 60
            if elapsed_min >= time1_min:
                logger.info(f"Time limit reached ({elapsed_min:.1f} min ≥ {time1_min} min), stopping")
                break
            yield from collectAllThree(pos_X, pos_Y, thickness, pos_name, isDebugMode)

        elapsed_min = (time.time() - t0) / 60
        logger.info(f"Completed cycle, elapsed time: {elapsed_min:.1f} / {time1_min} min")

    # NOTE: Heater is LEFT ON for manual gas change in hutch
    logger.info(f"Part A complete. Heater still ON at {ptc10.position:.0f} C. Ready for gas change.")
    appendToMdFile(f"Part A complete. PTC10 left ON at {ptc10.position:.0f} C for manual gas change.")

    if not isDebugMode:
        yield from after_command_list()
    else:
        logger.info("DEBUG: Skipping after_command_list()")

    appendToMdFile("  ***  ")


def PTC10_allen_cooling_and_collect(gas, cool_time_min, start_temp=None, md={}):
    """
    PART B: Slowly cool from current temperature to 30C while collecting data.

    Reads current PTC10 setpoint temperature (or use start_temp if provided),
    sets cooling ramp rate to reach 30 C in cool_time_min minutes, then collects
    USAXS/SAXS/WAXS at all 5 positions repeatedly while cooling until reaching 30 C.

    Sample name format: {pos_name}_{gas}_{temp}C_cooling

    Parameters
    ----------
    gas : str
        Gas atmosphere identifier for sample name (e.g., "N2", "air", "vacuum")
    cool_time_min : float
        Time to cool from current temperature to 30 C (in minutes)
    start_temp : float, optional
        Starting temperature in °C. If None, reads from ptc10.temperature.setpoint
    md : dict, optional
        Additional metadata to include in scans

    Example
    -------
    RE(PTC10_allen_cooling_and_collect("air", 45))
        Cools from current PTC10 setpoint to 30 C over 45 min, collecting all the way.

    RE(PTC10_allen_cooling_and_collect("air", 45, start_temp=300))
        Same but assumes starting from 300 C instead of reading setpoint.
    """

    def getSampleName(pos_name, current_temp):
        """Construct sample name with gas, temperature, and cooling phase."""
        return f"{pos_name}_{gas}_{current_temp:.0f}C_cooling"

    def collectAllThree(pos_X, pos_Y, thickness, pos_name, isDebugMode):
        """Collect USAXS/SAXS/WAXS at this position."""
        if not isDebugMode:
            yield from sync_order_numbers()
            current_temp = ptc10.position
            sample_mod = getSampleName(pos_name, current_temp)
            md["title"] = sample_mod
            yield from USAXSscan(pos_X, pos_Y, thickness, sample_mod, md={})

            current_temp = ptc10.position
            sample_mod = getSampleName(pos_name, current_temp)
            md["title"] = sample_mod
            yield from saxsExp(pos_X, pos_Y, thickness, sample_mod, md={})

            current_temp = ptc10.position
            sample_mod = getSampleName(pos_name, current_temp)
            md["title"] = sample_mod
            yield from waxsExp(pos_X, pos_Y, thickness, sample_mod, md={})
        else:
            current_temp = ptc10.position
            sample_mod = getSampleName(pos_name, current_temp)
            logger.info(f"[DEBUG] {sample_mod}")
            yield from bps.sleep(20)

    # Check debug mode
    isDebugMode = ptc10_debug.get()

    # Determine starting temperature
    if start_temp is None:
        start_temp = ptc10.temperature.setpoint.get()

    logger.info(f"Part B starting at {start_temp} C, cooling to 30 C over {cool_time_min} min (gas: {gas})")
    appendToMdFile("  ***  ")
    appendToMdFile(f"PTC10_allen_cooling_and_collect (PART B): Cool from {start_temp} C to 30 C in {cool_time_min} min, collect data (gas: {gas})")

    # Startup (no before_command_list — instrument already running from Part A)
    if not isDebugMode:
        logger.info("Skipping before_command_list() — already running from Part A")
    else:
        logger.info("DEBUG: Part B startup")
        yield from bps.sleep(5)

    # Calculate ramp rate: °C/min → divide by 60 for °C/s
    temp_change = start_temp - 30
    ramp_rate_C_per_min = temp_change / cool_time_min
    ramp_rate_C_per_sec = ramp_rate_C_per_min / 60.0

    logger.info(f"Starting cool ramp: {ramp_rate_C_per_min:.2f} °C/min ({ramp_rate_C_per_sec:.4f} °C/s)")
    appendToMdFile(f"Starting cool ramp at {ramp_rate_C_per_min:.2f} °C/min")

    # Set ramp rate and target temperature
    yield from bps.mv(ptc10.ramp, ramp_rate_C_per_sec)
    yield from bps.mv(ptc10.temperature.setpoint, 30)

    # Collect data while cooling until reaching 30 C
    logger.info(f"Collecting data while cooling from {start_temp} C to 30 C")
    appendToMdFile(f"Collecting USAXS/SAXS/WAXS at all positions while cooling")

    while ptc10.position > 35:  # Stop when approaching 30 C
        for pos_X, pos_Y, thickness, pos_name in PositionList:
            if ptc10.position <= 35:  # Check temp again before each position
                logger.info(f"Temperature reached ~30 C, stopping collection")
                break
            yield from collectAllThree(pos_X, pos_Y, thickness, pos_name, isDebugMode)

        current_temp = ptc10.position
        logger.info(f"Completed position cycle, currently at {current_temp:.1f} C")

    logger.info(f"Cooling complete, temperature at {ptc10.position:.1f} C")
    appendToMdFile(f"Cooling complete, reached {ptc10.position:.1f} C")

    # Turn off heater
    yield from setheaterOff()

    if not isDebugMode:
        yield from after_command_list()
    else:
        logger.info("DEBUG: Skipping after_command_list()")

    appendToMdFile(f"Part B complete. Cooling and data collection finished.")
    appendToMdFile("  ***  ")
    logger.info("Plan complete")
