"""
Automatic Obsidian notebook entries for USAXS data-collection plans.

Why this exists
---------------
Obsidian logging used to be attached to the *launcher*, not to the scan:
``run_command_file`` records the parsed command table once
(``recordRunCommandFile``), and agent-written user plans call
``recordFunctionRun()`` by hand.  A scan appended straight onto the
queueserver queue -- or typed at the IPython prompt -- went through neither
path and left no trace in the notebook at all.

``obsidian_logged`` closes that hole by decorating the data-collection plans
at their **definition sites**, the same way ``beam_guarded`` installs the beam
suspenders (see ``usaxs/suspenders/beam_guard.py``).  The wrapper travels with
the function object, so the entry is written no matter how the plan was
reached: the queueserver queue, the IPython prompt, ``%run -im
usaxs.user.<script>``, or a command file.

Usage
-----
In a plan module::

    from usaxs.utils.obsidian_plan_log import obsidian_logged

    @plan
    @beam_guarded
    @obsidian_logged
    def Flyscan(pos_X, pos_Y, thickness, title, md=None):
        ...

Keep ``@plan`` outermost, as ``beam_guard`` requires.  ``@obsidian_logged``
goes innermost so the entry is written as close to the plan body as possible.

What gets written
-----------------
::

    2026-10-20 14:03:11
    ## Scan started: Flyscan  [queueserver]
    - **Call:** Flyscan(pos_X=0, pos_Y=0, thickness=1.0, title='blank')
    2026-10-20 14:07:52 Flyscan('blank') completed in 281 s

Nesting
-------
Only the outermost decorated plan logs.  ``USAXSscan`` dispatches to
``Flyscan``/``USAXSscanStep`` and all three carry the decorator, so a
``USAXSscan`` call produces one entry, not two; queueing ``Flyscan`` directly
still produces one.  ``run_command_file`` is deliberately *not* decorated, so
every scan inside a command file is at depth 0 and logs -- the command table
stays the "what was requested" record, the per-scan entries are the "what
actually ran" record.

Failures
--------
Every write goes through :func:`_safe_append`, which swallows and logs any
exception.  A ``/share1`` outage must never abort a scan.  ``appendToMdFile``
is imported lazily inside that function: ``usaxs.utils.obsidian`` reads
``oregistry["user_data"]`` at module scope, and keeping the import late means
this module can be imported (and unit-tested) without a populated registry.
"""

import functools
import inspect
import logging
import os
import time

logger = logging.getLogger(__name__)

# Nesting depth of currently-running decorated plans.  Plans run sequentially
# in the RunEngine's single thread, so a plain int is enough.
_depth = 0


def _safe_append(text: str) -> None:
    """Append ``text`` to the Obsidian note file, never raising.

    Parameters
    ----------
    text : str
        Markdown to append, as accepted by ``obsidian.appendToMdFile``.
    """
    try:
        from usaxs.utils.obsidian import appendToMdFile

        appendToMdFile(text)
    except Exception as exc:  # noqa: BLE001 - logging must never break a scan
        logger.warning(
            "Could not write Obsidian entry (%s): %s", type(exc).__name__, exc
        )


def _bound_arguments(plan_func, args, kwargs):
    """Return the plan's arguments as an ordered ``{name: value}`` mapping.

    Falls back to positional ``arg0=...`` naming if the signature cannot be
    bound (wrong arity, for example -- the plan itself will raise soon enough
    and the log entry should not be what fails first).
    """
    try:
        bound = inspect.signature(plan_func).bind(*args, **kwargs)
        return dict(bound.arguments)
    except (TypeError, ValueError):
        mapping = {f"arg{i}": value for i, value in enumerate(args)}
        mapping.update(kwargs)
        return mapping


def _call_label(plan_func, arguments) -> str:
    """Render ``name(arg=value, ...)`` for the notebook entry.

    ``md`` is dropped: command files pass a metadata dict carrying
    ``full_filename``, ``line_number`` and friends, which would swamp the line.
    """
    parts = [f"{name}={value!r}" for name, value in arguments.items() if name != "md"]
    return f"{plan_func.__name__}({', '.join(parts)})"


def _short_label(plan_func, arguments) -> str:
    """Render a compact ``name('title')`` label for the completion line."""
    title = arguments.get("title")
    if title is None:
        return plan_func.__name__
    return f"{plan_func.__name__}({title!r})"


def _launch_source(arguments) -> str:
    """Name the path by which this plan was reached, for the entry heading."""
    md = arguments.get("md") or {}
    if isinstance(md, dict) and "filename" in md and "line_number" in md:
        name = os.path.basename(str(md["filename"]))
        return f"command file {name}:{md['line_number']}"
    try:
        from apsbits.utils.helper_functions import running_in_queueserver

        if running_in_queueserver():
            return "queueserver"
    except Exception:  # noqa: BLE001 - never let the tag break the entry
        pass
    return "console"


def obsidian_logged(plan_func):
    """Decorator: record the plan's start and outcome in the Obsidian notebook.

    Writes a ``## Scan started: <name>`` block with the call arguments and the
    launch source when the plan begins, and a single line with the outcome
    (``completed`` / ``failed: <ExcType>: <msg>`` / ``aborted``) and elapsed
    time when it ends.  Nested decorated plans are suppressed so each scan
    produces exactly one pair of entries.

    Parameters
    ----------
    plan_func : callable
        A Bluesky plan (generator function).

    Returns
    -------
    callable
        Generator function with the same signature; the plan's return value is
        preserved.
    """

    @functools.wraps(plan_func)
    def wrapper(*args, **kwargs):
        global _depth

        arguments = _bound_arguments(plan_func, args, kwargs)
        outermost = _depth == 0
        _depth += 1
        t0 = time.time()

        if outermost:
            _safe_append(
                f"## Scan started: {plan_func.__name__}"
                f"  [{_launch_source(arguments)}]\n"
                f"- **Call:** {_call_label(plan_func, arguments)}\n"
            )

        status = "completed"
        try:
            return (yield from plan_func(*args, **kwargs))
        except GeneratorExit:
            status = "aborted"
            raise
        except BaseException as exc:
            status = f"failed: {type(exc).__name__}: {exc}"
            raise
        finally:
            _depth -= 1
            if outermost:
                _safe_append(
                    f"{_short_label(plan_func, arguments)} {status}"
                    f" in {time.time() - t0:.0f} s"
                )

    return wrapper
