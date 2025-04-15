"""
format a dictionary as a table
"""

__all__ = [
    "dictionary_table",
]


import pyRestTable


def dictionary_table(dictionary, fmt="simple", printing=True):
    """
    return a table object from ``dictionary``

    PARAMETERS

    dictionary : dict
        Python dictionary
    fmt : str
        Any of the format names provided by
        `spec2nexus <https://pyresttable.readthedocs.io/en/latest/examples/index.html#examples>`_
        One of these: ``simple | plain | grid | complex | markdown | list-table | html``

        default: ``simple``
    fmt : bool
        Should this function print to stdout?

        default: ``True``

    RETURNS

    table : obj or `None`
        multiline text table (pyRestTable object) with dictionary contents
        in chosen format or ``None`` if dictionary has no contents

    EXAMPLE::

        In [8]: RE.md
        Out[8]: {'login_id': 'jemian:wow.aps.anl.gov', 'beamline_id': 'developer', 'proposal_id': None, 'pid': 19072, 'scan_id': 10, 'version': {'bluesky': '1.5.2', 'ophyd': '1.3.3', 'apstools': '1.1.5', 'epics': '3.3.3'}}
        In [9]: print(dictionary_table(RE.md, printing=False))
        =========== =============================================================================
        key         value
        =========== =============================================================================
        beamline_id developer
        login_id    jemian:wow.aps.anl.gov
        pid         19072
        proposal_id None
        scan_id     10
        version     {'bluesky': '1.5.2', 'ophyd': '1.3.3', 'apstools': '1.1.5', 'epics': '3.3.3'}
        =========== =============================================================================
    """
    if len(dictionary) == 0:
        return
    _t = pyRestTable.Table()
    _t.addLabel("key")
    _t.addLabel("value")
    for k, v in sorted(dictionary.items()):
        _t.addRow((k, str(v)))
    if printing:
        print(_t.reST(fmt=fmt))
    return _t
