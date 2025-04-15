"""Surveillance module for monitoring and logging instrument status.

This module provides functionality for monitoring various aspects of the USAXS
instrument, including detector counts, temperature, and other critical parameters.
"""

def monitor_detector_counts(detector, threshold=1000):
    """Monitor detector counts and log warnings if they exceed a threshold.
    
    Args:
        detector: The detector device to monitor
        threshold (int, optional): Count threshold for warnings. Defaults to 1000.
        
    Returns:
        Generator: A sequence of monitoring messages
    """
    while True:
        counts = yield from detector.read()
        if counts > threshold:
            logger.warning(f"Detector counts ({counts}) exceeded threshold ({threshold})")
        yield

def monitor_temperature(controller, setpoint, tolerance=0.1):
    """Monitor temperature and log warnings if it deviates from setpoint.
    
    Args:
        controller: The temperature controller device
        setpoint (float): Target temperature
        tolerance (float, optional): Acceptable deviation. Defaults to 0.1.
        
    Returns:
        Generator: A sequence of monitoring messages
    """
    while True:
        temp = yield from controller.read()
        if abs(temp - setpoint) > tolerance:
            logger.warning(
                f"Temperature ({temp:.2f}) deviated from setpoint ({setpoint:.2f})"
            )
        yield 