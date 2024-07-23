
"""
emails
"""
# TODO: this will liekly fail due to network changes. Remove from teh code and live with it. m
__all__ = [
    'email_notices',
    'NOTIFY_ON_RESET',
    'NOTIFY_ON_SCAN_DONE',
    'NOTIFY_ON_BEAM_LOSS',
    'NOTIFY_ON_BAD_FLY_SCAN',
    'NOTIFY_ON_FEEDBACK',
    'NOTIFY_ON_BADTUNE',
    ]

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

from apstools.utils import EmailNotifications

# user will write code to check the corresponding symbol to send EmailNotifications
NOTIFY_ON_RESET = False
NOTIFY_ON_SCAN_DONE = False
NOTIFY_ON_BEAM_LOSS = False
NOTIFY_ON_BAD_FLY_SCAN = False
NOTIFY_ON_FEEDBACK = False
NOTIFY_ON_BADTUNE = False

email_notices = EmailNotifications("usaxs@aps.anl.gov")
email_notices.add_addresses(
    "ilavsky@aps.anl.gov",
    #"kuzmenko@aps.anl.gov",
    # add as FYI for Bluesky support:
    "jemian@anl.gov",
)
