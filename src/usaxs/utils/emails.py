"""
Email notifications for USAXS operations.

This module provides email notification functionality for the USAXS instrument,
using apstools.utils.EmailNotifications as the underlying implementation.
"""

# TODO: this will liekly fail due to network changes.
# Remove from teh code and live with it. m
__all__ = [
    "email_notices",
    "NOTIFY_ON_RESET",
    "NOTIFY_ON_SCAN_DONE",
    "NOTIFY_ON_BEAM_LOSS",
    "NOTIFY_ON_BAD_FLY_SCAN",
    "NOTIFY_ON_FEEDBACK",
    "NOTIFY_ON_BADTUNE",
    "send_notification",
]

import logging
from typing import List, Optional

from apstools.utils import EmailNotifications

logger = logging.getLogger(__name__)
logger.info(__file__)

# Notification flags - these control when emails are sent
NOTIFY_ON_RESET = False
NOTIFY_ON_SCAN_DONE = False
NOTIFY_ON_BEAM_LOSS = False
NOTIFY_ON_BAD_FLY_SCAN = False
NOTIFY_ON_FEEDBACK = False
NOTIFY_ON_BADTUNE = False

# Initialize email notifications with default configuration
email_notices = EmailNotifications("usaxs@aps.anl.gov")
email_notices.add_addresses(
    "ilavsky@aps.anl.gov",
    # "kuzmenko@aps.anl.gov",
    # add as FYI for Bluesky support:
    "jemian@anl.gov",
)

def send_notification(
    subject: str, 
    message: str, 
    addresses: Optional[List[str]] = None,
    notify_flag: bool = True
) -> None:
    """Send an email notification.
    
    This is a wrapper around apstools.utils.EmailNotifications.send() that
    adds support for additional addresses and notification flags.
    
    Args:
        subject: Email subject line
        message: Email message body
        addresses: Optional list of additional email addresses
        notify_flag: Whether to send the notification (default: True)
    """
    if not notify_flag:
        logger.debug(f"Notification suppressed: {subject}")
        return
        
    if addresses:
        email_notices.add_addresses(*addresses)
    
    try:
        email_notices.send(subject, message)
        logger.info(f"Email notification sent: {subject}")
    except Exception as e:
        logger.error(f"Failed to send email notification: {e}")
