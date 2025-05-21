"""
report how much time remains in flyscan
"""

__all__ = [
    "remaining_time_reporter",
]


import datetime
import logging
import time

from apstools.utils import run_in_thread

logger = logging.getLogger(__name__)


@run_in_thread
def remaining_time_reporter(
    title: str, duration_s: float, interval_s: float = 5, poll_s: float = 0.05
) -> None:
    """Report remaining time periodically in a separate thread.

    This function runs in a separate thread and periodically reports the
    remaining time for a long-running operation.

    Args:
        title (str): Title to display in the progress messages
        duration_s (float): Total duration in seconds
        interval_s (float): Interval between progress updates in seconds
        poll_s (float): Sleep time between checks in seconds
    """
    if duration_s < interval_s:
        return
    t = time.time()
    expires = t + duration_s
    update = t + interval_s
    # print()
    while time.time() < expires:
        remaining = expires - t
        if t > update:
            update += interval_s
            logger.info(f"{title}: {remaining:.1f}s remaining")
        time.sleep(poll_s)
        t = time.time()


def generate_status_report(instrument):
    """Generate a comprehensive status report for the instrument.

    Args:
        instrument: The instrument device to report on

    Returns:
        dict: A dictionary containing the status report data
    """
    return {
        "timestamp": datetime.now().isoformat(),
        "instrument_state": instrument.state,
        "detector_status": instrument.detector.status,
        "temperature": instrument.temperature.read(),
        "pressure": instrument.pressure.read(),
    }


def format_report(report_data):
    """Format report data into a human-readable string.

    Args:
        report_data (dict): The report data to format

    Returns:
        str: A formatted string representation of the report
    """
    return f"""
Instrument Status Report
=======================
Time: {report_data['timestamp']}
State: {report_data['instrument_state']}
Detector: {report_data['detector_status']}
Temperature: {report_data['temperature']:.2f}°C
Pressure: {report_data['pressure']:.2f} mbar
"""
