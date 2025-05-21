"""
user-customizable sample title function
"""


_sample_title_function = None


def plainSampleTitle(sample_title):
    """
    Just the given sample title.

    Users can write their own function, like this one, that
    returns a string to be used as the sample title for
    all USAXS, SAXS, WAXS, and other data collection scans.

    Once you have a function, call ``setSampleTitleFunction()``
    with the function object.  Call ``resetSampleTitleFunction()``
    to use the default function.

    EXAMPLE::

        def myTitleFunction(title):
            return f"{title} scan={RE.md['scan_id']}"

        setSampleTitleFunction(myTitleFunction)

    Then::

        >>> getSampleTitle("blank")
        'blank scan=36'
    """
    return sample_title


def setSampleTitleFunction(func_object):
    """Allow the user to supply a sampleTitleFunction."""
    global _sample_title_function
    _sample_title_function = func_object


def resetSampleTitleFunction():
    """Set the sample to the default setting."""
    global _sample_title_function
    _sample_title_function = plainSampleTitle


def getSampleTitle(sample_title):
    """
    This is the function called from the data collection scans.

    DO NOT MODIFY OR REPLACE THIS FUNCTION!
    """
    return _sample_title_function(sample_title)


resetSampleTitleFunction()
