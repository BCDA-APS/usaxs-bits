#!/bin/bash
# file: qs_host.sh
# Manage the bluesky queueserver host process.
# Could be in a screen session or run as a direct process.

SHELL_SCRIPT_NAME=${BASH_SOURCE:-${0}}
SCRIPT_DIR="$(dirname $(readlink -f  "${SHELL_SCRIPT_NAME}"))"
CONFIGS_DIR=$(readlink -f "${SCRIPT_DIR}/../src/usaxs/configs")
QSERVER_DIR=$(readlink -f "${SCRIPT_DIR}/../src/usaxs/qserver")
HTTP_PORT="${QSERVER_HTTP_SERVER_PORT:-60610}"
HTTP_HOST="${QSERVER_HTTP_SERVER_HOST:-0.0.0.0}"
HTTP_API_KEY="${QSERVER_HTTP_SERVER_SINGLE_USER_API_KEY:-test}"
ZMQ_CONTROL_PORT="${QSERVER_ZMQ_CONTROL_PORT:-60615}"
# Session names and startup commands are built further below, once
# DATABROKER_CATALOG and the conda environment have been resolved.
###-----------------------------
### Change program defaults here

# Instrument configuration YAML file with databroker catalog name.
ICONFIG_YML="${CONFIGS_DIR}/iconfig.yml"

# Bluesky queueserver configuration YAML file.
# This file contains the definition of 'redis_addr'.  (default: localhost:6379)
# "export" is for BITS to identify when QS is running.
export QS_CONFIG_YML="${QSERVER_DIR}/qs-config.yml"

# Host name (from $hostname) where the queueserver host process runs.
# QS_HOSTNAME=amber.xray.aps.anl.gov  # if a specific host is required
QS_HOSTNAME="$(hostname)"

PROCESS=start-re-manager  # from the conda environment
# STARTUP_COMMAND is built further below, once the conda environment is known.

# 0MQ document-stream proxy for the queue-monitor GUI live plots (Phase 3).
# The RE Worker publishes documents to PROXY_IN; the GUI subscribes to PROXY_OUT.
# Must match iconfig.yml DOC_STREAM.PUBLISH_ADDR (in) and the GUI settings (out).
PROXY_IN_PORT="${QSERVER_ZMQ_PROXY_IN_PORT:-5567}"
PROXY_OUT_PORT="${QSERVER_ZMQ_PROXY_OUT_PORT:-5568}"

#--------------------
# internal configuration below

# Resolve the conda environment that provides the queueserver, then address every
# executable by absolute path from *that* environment.
#
# Do NOT use bare command names here.  On this host ~/.local/bin and other conda
# envs sit ahead of ${CONDA_PREFIX}/bin in $PATH, so a bare "uvicorn" or "python"
# silently resolves to the wrong environment even with bits_usaxs activated.
# That is what kept the HTTP server (port ${HTTP_PORT}) from ever starting: it
# died instantly with "ModuleNotFoundError: No module named 'bluesky_httpserver'".
QS_PROCESS_PATH="$(command -v "${PROCESS}")"
if [ -z "${QS_PROCESS_PATH}" ] || [ ! -x "${QS_PROCESS_PATH}" ]; then
    echo "PROCESS '${PROCESS}': file not found. CONDA_PREFIX='${CONDA_PREFIX}'"
    exit 1
fi
QS_PROCESS_PATH="$(readlink -f "${QS_PROCESS_PATH}")"
QS_ENV_BIN="$(dirname "${QS_PROCESS_PATH}")"
QS_PYTHON="${QS_ENV_BIN}/python"
if [ ! -x "${QS_PYTHON}" ]; then
    echo "No 'python' in '${QS_ENV_BIN}'; cannot start the queueserver."
    exit 1
fi

if [ -z "$STARTUP_DIR" ] ; then
    # If no startup dir is specified, use the directory with this script
    STARTUP_DIR="${SCRIPT_DIR}"
fi

if [ "${DATABROKER_CATALOG}" == "" ]; then
    if [ -f "${ICONFIG_YML}" ]; then
        DATABROKER_CATALOG=$(grep DATABROKER_CATALOG "${ICONFIG_YML}" | awk '{print $NF}')
        # echo "Using catalog ${DATABROKER_CATALOG}"
    fi
fi
DEFAULT_SESSION_NAME="bluesky_queueserver-${DATABROKER_CATALOG}"
HTTP_SESSION_NAME="bluesky-httpserver-${DATABROKER_CATALOG}"
PROXY_SESSION_NAME="bluesky-0MQ-proxy-${DATABROKER_CATALOG}"

# Startup commands, all by absolute path (see the $PATH note above).
STARTUP_COMMAND="${QS_PROCESS_PATH} --config=${QS_CONFIG_YML} --user-group-permissions=${QSERVER_DIR}/user_group_permissions.yaml --existing-plans-devices=${QSERVER_DIR}/existing_plans_and_devices.yaml"
HTTP_STARTUP_COMMAND="${QS_PYTHON} -m uvicorn bluesky_httpserver.server:app --host ${HTTP_HOST} --port ${HTTP_PORT}"
PROXY_STARTUP_COMMAND="${QS_ENV_BIN}/bluesky-0MQ-proxy ${PROXY_IN_PORT} ${PROXY_OUT_PORT}"

#--------------------

SELECTION=${1:-usage}
SESSION_NAME=${2:-"${DEFAULT_SESSION_NAME}"}

# But other management commands will fail if mismatch
if [ "$(hostname)" != "${QS_HOSTNAME}" ]; then
    echo "Must manage queueserver process on ${QS_HOSTNAME}.  This is $(hostname)."
    exit 1
fi

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

# echo "SESSION_NAME = ${SESSION_NAME}"
# echo "SHELL_SCRIPT_NAME = ${SHELL_SCRIPT_NAME}"
# echo "STARTUP_COMMAND = ${STARTUP_COMMAND}"
# echo "STARTUP_DIR = ${STARTUP_DIR}"

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

function checkpid() {
    # Assume the process is down until proven otherwise
    PROCESS_DOWN=1

    MY_UID=$(id -u)
    # The '\$' is needed in the pgrep pattern to select vm7, but not vm7.sh
    MY_PID=$(ps -u | grep "${PROCESS}")
    #!echo "MY_PID=${MY_PID}"
    SCREEN_SESSION="${MY_PID}.${SESSION_NAME}"

    if [ "${MY_PID}" != "" ] ; then
        SCREEN_PID="${MY_PID}"

        # At least one instance of the process is running;
        # Find the binary that is associated with this process
        for pid in ${MY_PID}; do
            # compare directories
            BIN_CWD=$(readlink "/proc/${pid}/cwd")
            START_CWD=$(readlink -f "${STARTUP_DIR}")

            if [ "$BIN_CWD" = "$START_CWD" ] ; then
                # The process is running with PID=$pid from $STARTUP_DIR
                P_PID=$(ps -p "${pid}" -o ppid=)
                # strip leading (and trailing) whitespace
                arr=($P_PID)
                P_PID=${arr[0]}
                SCREEN_SESSION="${P_PID}.${SESSION_NAME}"
                SCREEN_MATCH=$(screen -ls "${SCREEN_SESSION}" | grep "${SESSION_NAME}")
                if [ "${SCREEN_MATCH}" != "" ] ; then
                    # process is running in screen
                    PROCESS_DOWN=0
                    MY_PID=${pid}
                    SCREEN_PID=${P_PID}
                    break
                fi
            fi
        done
    else
        # process is not running
        PROCESS_DOWN=1
    fi

    return ${PROCESS_DOWN}
}

function checkup () {
    if ! checkpid; then
        restart
    fi
}

function console () {
    if checkpid; then
        echo "Connecting to ${SCREEN_SESSION}'s screen session"
        # The -r flag will only connect if no one is attached to the session
        #!screen -r "${SESSION_NAME}"
        # The -x flag will connect even if someone is attached to the session
        screen -x "${SCREEN_SESSION}"
    else
        echo "${SCREEN_NAME} is not running"
    fi
}

function exit_if_running() {
    # ensure that multiple, simultaneous processes are not started by this user ID
    MY_UID=$(id -u)
    MY_PID=$(pgrep "${SESSION_NAME}"\$ -u "${MY_UID}")

    if [ "" != "${MY_PID}" ] ; then
        echo "${SESSION_NAME} is already running (PID=${MY_PID}), won't start a new one"
        exit 1
    fi
}

function port_open() {
    # $1 = port.  True if something is listening on localhost:$1.
    (exec 3<>"/dev/tcp/127.0.0.1/${1}") >/dev/null 2>&1
}

function wait_for_port() {
    # $1 = port, $2 = label, $3 = timeout in seconds
    local port="${1}" label="${2}" timeout="${3}" i
    for ((i = 0; i < timeout * 2; i++)); do
        if port_open "${port}"; then
            echo "    OK    ${label}: listening on ${port}"
            return 0
        fi
        sleep 0.5
    done
    echo "    FAIL  ${label}: nothing listening on ${port} after ${timeout}s"
    return 1
}

function restart() {
    stop
    # Wait for the old processes to actually exit before starting new ones.
    # The previous fixed "sleep 0.1" raced: start() still saw the dying manager
    # and reported "is already running", leaving HTTP server and proxy down.
    local i
    for ((i = 0; i < 50; i++)); do
        checkpid || break
        sleep 0.2
    done
    if checkpid; then
        echo "WARNING: ${SESSION_NAME} (pid=${MY_PID}) did not exit; not restarting."
        exit 1
    fi
    start
}

function run_process() {
    # only use this for diagnostic purposes
    exit_if_running
    cd "${STARTUP_DIR}"
    ${STARTUP_COMMAND}
}

function screenpid() {
    if [ -z "${SCREEN_PID}" ] ; then
        echo
    else
        echo " in a screen session (pid=${SCREEN_PID})"
    fi
}

function start() {
    if checkpid; then
        echo -n "${SCREEN_SESSION} is already running (pid=${MY_PID})"
        screenpid
    else
        if [ ! -f "${CONDA_EXE}" ]; then
            echo "No 'conda' command available."
            exit 1
        fi
        echo "Starting ${SESSION_NAME}"
        cd "${STARTUP_DIR}"

        # "screen -dm" forks a real daemon, so the session survives this script
        # exiting.  The previous "screen -Dm ... &" left screen as a child of
        # this shell and tied its lifetime to the calling terminal.
        screen -dmS "${SESSION_NAME}" -h 5000 ${STARTUP_COMMAND}

        echo "Starting ${HTTP_SESSION_NAME} on ${HTTP_HOST}:${HTTP_PORT}"
        if [ "${HTTP_API_KEY}" == "test" ]; then
            echo "WARNING: HTTP server API key is the default value 'test'."
            echo "         Now that HTTP_HOST=${HTTP_HOST}, this endpoint may be reachable"
            echo "         from other machines on the network. Set a real secret via"
            echo "         QSERVER_HTTP_SERVER_SINGLE_USER_API_KEY before relying on this in production."
        fi
        QSERVER_HTTP_SERVER_SINGLE_USER_API_KEY="${HTTP_API_KEY}" \
        QSERVER_ZMQ_CONTROL_ADDRESS="tcp://localhost:${ZMQ_CONTROL_PORT}" \
        screen -dmS "${HTTP_SESSION_NAME}" -h 5000 ${HTTP_STARTUP_COMMAND}

        if [ -x "${QS_ENV_BIN}/bluesky-0MQ-proxy" ]; then
            echo "Starting ${PROXY_SESSION_NAME} (${PROXY_IN_PORT} -> ${PROXY_OUT_PORT})"
            screen -dmS "${PROXY_SESSION_NAME}" -h 5000 ${PROXY_STARTUP_COMMAND}
        else
            echo "bluesky-0MQ-proxy not found in ${QS_ENV_BIN}; GUI live plots will be unavailable"
        fi

        # Verify.  Previously every service was launched with "&" and nothing
        # checked the result, so a service that died on startup was silent.
        echo "Verifying services ..."
        RC=0
        wait_for_port "${ZMQ_CONTROL_PORT}" "RE Manager (ZMQ control)" 60 || RC=1
        wait_for_port "${HTTP_PORT}" "HTTP server" 30 || RC=1
        if [ -x "${QS_ENV_BIN}/bluesky-0MQ-proxy" ]; then
            wait_for_port "${PROXY_OUT_PORT}" "0MQ document proxy" 15 || RC=1
        fi
        if [ "${RC}" -ne 0 ]; then
            echo ""
            echo "One or more services failed to start.  Inspect them with:"
            echo "    screen -ls"
            echo "    ${SHELL_SCRIPT_NAME} console"
            echo "    screen -r ${HTTP_SESSION_NAME}"
            return 1
        fi
        echo "All queueserver services are up."
    fi
}

function status() {
    if checkpid; then
        echo -n "${SCREEN_SESSION} is running (pid=${MY_PID})"
        screenpid
    else
        echo "${SESSION_NAME} is not running"
    fi
}

function stop() {
    if checkpid; then
        echo "Stopping ${SCREEN_SESSION} (pid=${MY_PID})"
        kill "${MY_PID}"
    else
        echo "${SESSION_NAME} is not running"
    fi

    # Always clean these up, even when the manager was already down.  A stale
    # HTTP server or proxy keeps holding ports ${HTTP_PORT}/${PROXY_IN_PORT}/${PROXY_OUT_PORT}
    # and makes the next start fail with "address already in use".
    HTTP_PID=$(pgrep -f "bluesky_httpserver.server")
    if [ -n "${HTTP_PID}" ]; then
        echo "Stopping ${HTTP_SESSION_NAME} (pid=${HTTP_PID})"
        kill ${HTTP_PID}
    fi
    PROXY_PID=$(pgrep -f "bluesky-0MQ-proxy")
    if [ -n "${PROXY_PID}" ]; then
        echo "Stopping ${PROXY_SESSION_NAME} (pid=${PROXY_PID})"
        kill ${PROXY_PID}
    fi
}

function usage() {
    echo "Usage: $(basename "${SHELL_SCRIPT_NAME}") {start|stop|restart|status|checkup|console|run} [NAME]"
    echo ""
    echo "    COMMANDS"
    echo "        console   attach to process console if process is running in screen"
    echo "        checkup   check that process is running, restart if not"
    echo "        restart   restart process"
    echo "        run       run process in console (not screen)"
    echo "        start     start process"
    echo "        status    report if process is running"
    echo "        stop      stop process"
    echo ""
    echo "    OPTIONAL TERMS"
    echo "        NAME      name of process (default: ${DEFAULT_SESSION_NAME})"
}

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

case ${SELECTION} in
    start) start ;;
    stop | kill) stop ;;
    restart) restart ;;
    status) status ;;
    checkup) checkup ;;
    console) console ;;
    run) run_process ;;
    *) usage ;;
esac

# -----------------------------------------------------------------------------
# :author:    BCDA
# :copyright: (c) 2017-2025, UChicago Argonne, LLC
# The full license is in the file LICENSE, distributed with this software.
# -----------------------------------------------------------------------------
