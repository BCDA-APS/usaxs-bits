"""
derivative of two vectors: y(x), returns y'(x)
"""


from collections import OrderedDict


def makeOrderedDictFromTwoLists(labels, values):
    """return an OrderedDict"""
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
