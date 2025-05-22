# this is a Linkam plan

import logging

logger = logging.getLogger(__name__)

logger.info(__file__)


import pathlib

from instrument.utils import getSampleTitle
from instrument.utils import setSampleTitleFunction
from apstools.utils import cleanupText


def myNamer(title):
    return f"{pathlib.Path(title).exists()} : {title}"


setSampleTitleFunction(myNamer)
print(getSampleTitle(__file__))
print(getSampleTitle("purple"))
print(cleanupText(getSampleTitle("Merging can be performed automatically")))
