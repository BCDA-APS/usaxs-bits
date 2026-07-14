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

    # Auto-connect the live document stream when the window opens. If the proxy
    # is not running the SUB socket simply receives nothing (harmless).
    plots_autostart = True

    # One line-plot per tune type. Each run is routed to the first config whose
    # ``plan_names`` contains the run's start-doc ``plan_name``; ``max_runs``
    # keeps the last N scans overlaid (FIFO).
    #
    # IMPORTANT: ``x`` and ``ys`` are event-document FIELD names, not device
    # names. The values below are the expected names for the USAXS tune plans
    # (motor readback = "<stage>_<axis>", detectors "UPD"/"I0"), but they MUST be
    # confirmed against a live document once the Publisher is running — see
    # USAXS-GUI-IMPLEMENTATION.md section 5b for the one-line verification.
    plot_config = [
        {
            "title": "tune_ar",
            "x": "a_stage_r",
            "ys": ["UPD"],
            "plan_names": {"tune_ar", "find_ar"},
            "max_runs": 5,
        },
        {
            "title": "tune_mr",
            "x": "m_stage_r",
            "ys": ["I0"],
            "plan_names": {"tune_mr"},
            "max_runs": 5,
        },
        {
            "title": "tune_a2rp",
            "x": "a_stage_r2p",
            "ys": ["UPD"],
            "plan_names": {"tune_a2rp", "find_a2rp"},
            "max_runs": 5,
        },
        {
            "title": "tune_dx",
            "x": "d_stage_x",
            "ys": ["UPD"],
            "plan_names": {"tune_dx"},
            "max_runs": 5,
        },
        {
            "title": "tune_dy",
            "x": "d_stage_y",
            "ys": ["UPD"],
            "plan_names": {"tune_dy"},
            "max_runs": 5,
        },
    ]


SETTINGS = Settings()
