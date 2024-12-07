# this is a Linkam plan

import logging

logger = logging.getLogger(__name__)

logger.info(__file__)


from instrument.utils.cleanup_text import cleanupText
from instrument.utils import getSampleTitle
from instrument.utils import setSampleTitleFunction
import pathlib


def myNamer(title):
    return f"{pathlib.Path(title).exists()} : {title}"


setSampleTitleFunction(myNamer)
print(getSampleTitle(__file__))
print(getSampleTitle("purple"))
print(cleanupText(getSampleTitle("Merging can be performed automatically")))
