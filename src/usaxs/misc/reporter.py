"""Reporting module for generating instrument status and data reports.

This module provides functionality for generating various types of reports
about the USAXS instrument's status, data collection, and analysis results.
"""

def generate_status_report(instrument):
    """Generate a comprehensive status report for the instrument.
    
    Args:
        instrument: The instrument device to report on
        
    Returns:
        dict: A dictionary containing the status report data
    """
    return {
        'timestamp': datetime.now().isoformat(),
        'instrument_state': instrument.state,
        'detector_status': instrument.detector.status,
        'temperature': instrument.temperature.read(),
        'pressure': instrument.pressure.read()
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