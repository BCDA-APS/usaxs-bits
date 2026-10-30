"""Tests for the ``@obsidian_logged`` plan decorator.

These run without EPICS or ``apsbits``: ``obsidian_plan_log`` imports
``appendToMdFile`` lazily, so the module is importable with a bare
``PYTHONPATH=src`` and the write can be monkeypatched away.

    PYTHONPATH=src python -m pytest tests/test_obsidian_plan_log.py -v
"""

import inspect

import pytest

from usaxs.utils import obsidian_plan_log
from usaxs.utils.obsidian_plan_log import obsidian_logged


@pytest.fixture
def entries(monkeypatch):
    """Capture what the decorator would have written to the notebook."""
    captured = []
    monkeypatch.setattr(obsidian_plan_log, "_safe_append", captured.append)
    # a decorated plan that raised earlier must not leave the counter armed
    monkeypatch.setattr(obsidian_plan_log, "_depth", 0)
    return captured


@obsidian_logged
def _scan(pos_X, pos_Y, thickness, title, md=None):
    yield ("scan", title)
    return "done"


@obsidian_logged
def _dispatcher(pos_X, pos_Y, thickness, title, md=None):
    yield from _scan(pos_X, pos_Y, thickness, title, md=md)


@obsidian_logged
def _broken(title, md=None):
    yield ("broken", title)
    raise RuntimeError("boom")


def test_signature_is_preserved():
    """Queueserver validates plan parameters with inspect.signature()."""
    assert list(inspect.signature(_scan).parameters) == [
        "pos_X",
        "pos_Y",
        "thickness",
        "title",
        "md",
    ]


def test_logs_start_and_completion(entries):
    """A scan logs one start block and one completion line."""
    assert list(_scan(1, 2, 0.5, "blank")) == [("scan", "blank")]

    assert len(entries) == 2
    start, end = entries
    assert start.startswith("## Scan started: _scan")
    assert "pos_X=1, pos_Y=2, thickness=0.5, title='blank'" in start
    assert end.startswith("_scan('blank') completed in ")


def test_return_value_is_preserved(entries):
    """The decorator must not swallow the plan's return value."""
    gen = _scan(1, 2, 0.5, "blank")
    with pytest.raises(StopIteration) as excinfo:
        while True:
            next(gen)
    assert excinfo.value.value == "done"


def test_md_is_not_rendered_into_the_call_label(entries):
    """Command-file metadata would swamp the entry."""
    md = {"full_filename": "/share1/a/b.txt", "line_number": 7, "action": "SAXS"}
    list(_scan(1, 2, 0.5, "blank", md=md))

    assert "full_filename" not in entries[0]
    assert "md=" not in entries[0]


def test_nested_plans_log_once(entries):
    """USAXSscan -> Flyscan must produce a single pair of entries."""
    list(_dispatcher(1, 2, 0.5, "blank"))

    assert len(entries) == 2
    assert entries[0].startswith("## Scan started: _dispatcher")
    assert obsidian_plan_log._depth == 0


def test_command_file_launch_source(entries):
    """Entries name the command file and line they came from."""
    md = {"filename": "overnight.txt", "line_number": 7}
    list(_scan(1, 2, 0.5, "blank", md=md))

    assert "[command file overnight.txt:7]" in entries[0]


def test_failure_is_recorded_and_reraised(entries):
    """A failed scan is recorded, and the exception still propagates."""
    with pytest.raises(RuntimeError, match="boom"):
        list(_broken("blank"))

    assert entries[-1].startswith("_broken('blank') failed: RuntimeError: boom in ")
    assert obsidian_plan_log._depth == 0


def test_abort_is_recorded(entries):
    """Closing the generator (RunEngine abort) is recorded as 'aborted'."""
    gen = _scan(1, 2, 0.5, "blank")
    next(gen)
    gen.close()

    assert entries[-1].startswith("_scan('blank') aborted in ")
    assert obsidian_plan_log._depth == 0


def _stub_obsidian(monkeypatch, append):
    """Install a fake ``usaxs.utils.obsidian`` with the given appendToMdFile.

    The real module reads ``oregistry["user_data"]`` at import, so it cannot be
    imported off-instrument.  ``_safe_append`` imports it lazily, which is what
    makes this substitution possible.
    """
    import sys
    import types

    stub = types.ModuleType("usaxs.utils.obsidian")
    stub.appendToMdFile = append
    monkeypatch.setitem(sys.modules, "usaxs.utils.obsidian", stub)


def test_entries_reach_appendToMdFile(monkeypatch):
    """The lazy import in _safe_append resolves to the real writer."""
    monkeypatch.setattr(obsidian_plan_log, "_depth", 0)
    written = []
    _stub_obsidian(monkeypatch, written.append)

    list(_scan(1, 2, 0.5, "blank"))

    assert len(written) == 2
    assert written[0].startswith("## Scan started: _scan  [console]")


def test_notebook_failure_does_not_break_the_scan(monkeypatch):
    """A /share1 outage must never abort a scan."""

    def explode(_text):
        raise OSError("/share1 is gone")

    monkeypatch.setattr(obsidian_plan_log, "_depth", 0)
    _stub_obsidian(monkeypatch, explode)

    assert list(_scan(1, 2, 0.5, "blank")) == [("scan", "blank")]
    assert obsidian_plan_log._depth == 0
