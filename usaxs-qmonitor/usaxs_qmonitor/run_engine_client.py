"""
USAXS-specific RunEngineClient.

Subclasses the bluesky-widgets model and exposes queueserver API capabilities
that the stock GUI model does not surface: script upload (Phase 1) and function
execution (Phase 2). The base class already holds ``self._client``, a full
``bluesky_queueserver_api.REManagerAPI`` instance.
"""

from bluesky_queueserver_api import BFunc
from bluesky_widgets.models.run_engine_client import RunEngineClient


class UsaxsRunEngineClient(RunEngineClient):
    """RunEngineClient with USAXS additions."""

    # --- Phase 1: script upload ("qserver script upload" equivalent) ---
    def script_upload(self, file_path, run_in_background=False):
        """Upload a Python file into the live RE Worker namespace.

        Executes the script in the worker (like ``%run``); it may define or
        replace plans/functions. By default the allowed-plans/-devices lists
        refresh afterwards, so new plans appear in the GUI. Returns the API
        response dict (contains ``task_uid``); poll ``task_result(uid)`` for the
        outcome (e.g. a traceback if the script raised).
        """
        with open(file_path) as f:
            script = f.read()
        return self._client.script_upload(
            script, run_in_background=run_in_background
        )

    def task_result(self, task_uid):
        """Return the result dict for a task started by script_upload / function_execute."""
        return self._client.task_result(task_uid)

    # --- Phase 2: function execution ("do it now", not queued) ---
    def function_execute(self, name, *args, run_in_background=False, **kwargs):
        """Execute a function in the RE Worker namespace immediately.

        The function must exist in the worker namespace and be permitted under
        ``allowed_functions`` for this user group. ``run_in_background=True``
        runs even while a plan executes (only safe for functions that do not
        move hardware). Returns the API response dict (contains ``task_uid``).
        """
        return self._client.function_execute(
            BFunc(name, *args, **kwargs), run_in_background=run_in_background
        )
