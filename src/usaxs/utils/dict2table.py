"""
format a dictionary as a table
"""

__all__ = [
    "dictionary_table",
]


from typing import Optional

import pyRestTable


def dictionary_table(
    dictionary: dict,
    fmt: str = "simple",
    printing: bool = True,
) -> Optional[pyRestTable.Table]:
    """Return a table object from ``dictionary``.

    Parameters
    ----------
    dictionary : dict
        Python dictionary
    fmt : str
        Any of the format names provided by `spec2nexus
        <https://pyresttable.readthedocs.io/en/latest/examples/index.html#examples>`_
        One of these: ``simple | plain | grid | complex | markdown | list-table | html``
        Default: ``simple``
    printing : bool
        Should this function print to stdout?
        Default: ``True``

    Returns
    -------
    pyRestTable.Table or None
        multiline text table (pyRestTable object) with dictionary contents
        in chosen format or ``None`` if dictionary has no contents

    Example
    -------
    >>> from usaxs.utils.dict2table import dictionary_table
    >>> md = {
    ...     "purpose": "testing",
    ...     "versions": {
    ...         "bluesky": "1.5.2",
    ...         "ophyd": "1.3.3",
    ...         "apstools": "1.1.5",
    ...         "epics": "3.3.3"
    ...     }
    ... }
    >>> tbl = dictionary_table(md)
    =========== ================
    key         value
    =========== ================
    purpose     testing
    versions    {'bluesky': '1.5.2',
                'ophyd': '1.3.3',
                'apstools': '1.1.5',
                'epics': '3.3.3'}
    =========== ================
    """
    if len(dictionary) == 0:
        return None
    _t = pyRestTable.Table()
    _t.addLabel("key")
    _t.addLabel("value")
    for k, v in sorted(dictionary.items()):
        _t.addRow((k, str(v)))
    if printing:
        print(_t.reST(fmt=fmt))
    return _t
