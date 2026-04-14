"""
Build an OrderedDict from a labels list and a values list.

Provides a convenience wrapper around ``zip`` + ``OrderedDict`` that also
validates that there are not more values than labels.
"""

from collections import OrderedDict


def makeOrderedDictFromTwoLists(labels, values):
    """Return an OrderedDict pairing labels with values.

    If *values* is shorter than *labels*, only the first ``len(values)``
    labels are used and the remaining labels are silently ignored.

    Parameters
    ----------
    labels : sequence
        Ordered sequence of key names.
    values : sequence
        Ordered sequence of values to pair with labels.
        Must not be longer than *labels*.

    Returns
    -------
    OrderedDict

    Raises
    ------
    ValueError
        If len(values) > len(labels).
    """
    if len(values) > len(labels):
        raise ValueError(
            (
                "Too many values for known labels."
                f"  labels={labels}"
                f"  values={values}"
            )
        )
    # only the first len(values) labels will be used!
    return OrderedDict(zip(labels, values, strict=False))
