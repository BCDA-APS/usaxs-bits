"""
Runtime settings for the USAXS queue-monitor GUI.

Addresses left as ``None`` fall back to the bluesky-queueserver defaults
(``tcp://localhost:60615`` control, ``tcp://localhost:60625`` info), which match
the beamline ``qs-config.yml``. CLI args / environment variables in ``main.py``
override these.
"""

import os


class Settings:
    """Runtime configuration for the USAXS queue-monitor GUI."""

    # --- Queueserver transport (ZMQ only for now) ---
    http_server_uri = None
    http_server_api_key = None
    zmq_re_manager_control_addr = None  # None -> tcp://localhost:60615
    zmq_re_manager_info_addr = None  # None -> tcp://localhost:60625

    # --- USAXS user identity (permissions) ---
    # Group "primary" already allows newUser/newSample in user_group_permissions.yaml.
    user_name = "usaxs"
    user_group = "primary"

    # --- Script upload ("Load plan file...") ---
    # Directory the file dialog opens in; the agent-generated / user plan files.
    plans_dir = os.path.expanduser("~/GitHub/bluesky-bits/src/usaxs/user")

    # --- Live document stream (Phase 3) ---
    # GUI subscribes here; the beamline runs `bluesky-0MQ-proxy 5567 5568` and the
    # RE Worker publishes to 5567. Override with QSERVER_ZMQ_PROXY_INFO_ADDRESS.
    zmq_proxy_info_addr = os.environ.get(
        "QSERVER_ZMQ_PROXY_INFO_ADDRESS", "localhost:5568"
    )


SETTINGS = Settings()
