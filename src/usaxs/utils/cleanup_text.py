"""
return a clean version of input text
"""

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)

import re

def cleanupText(text):
    """
    given some input text string, return a clean version

    remove troublesome characters, perhaps other cleanup as well

    this is best done with regular expression pattern matching
    """
    pattern = "[a-zA-Z0-9_]"

    def mapper(c):
        if re.match(pattern, c) is not None:
            return c
        return "_"

    return "".join([mapper(c) for c in text])
