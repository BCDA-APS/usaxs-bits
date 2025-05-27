# Bluesky code for USAXS instrument (APS-U, 12ide)

**Description** USAXS instrument web page : https://usaxs.xray.aps.anl.gov/

USAXS instrument old Bluesky code is here: https://github.com/APS-USAXS/usaxs-bluesky-ended-2023

New USAXS instrument is located at APS 12ID beamline, hutch E. This is code used for operations of this instrument and is specific to existing hardware.


## Installing your own BITS instrument

```bash
export ENV_NAME=usaxs-bits
conda create -y -n $ENV_NAME python=3.11
conda activate $ENV_NAME
pip install apsbits
```


## Creating a New Instrument
```bash
export YOUR_INSTRUMENT_NAME=usaxs
create-bits $YOUR_INSTRUMENT_NAME
pip install -e .
```


## IPython console Start

To start the bluesky instrument session in a ipython execute the next command in a terminal:

```bash
ipython
```

## Jupyter Notebook Start
Start JupyterLab, a Jupyter notebook server, or a notebook, VSCode.

## Starting the BITS Package

```py
from YOUR_INSTRUMENT_NAME.startup import *
```

## Run Sim Plan Demo

To run some simulated plans that ensure the installation worked as expected
please run the next commands inside an ipython session or a jupyter notebook
after starting the data acquisition:

```py
RE(sim_print_plan())
RE(sim_count_plan())
RE(sim_rel_scan_plan())
```

## Configuration files

The files that can be configured to adhere to your preferences are:

- `configs/iconfig.yml` - configuration for data collection
- `configs/logging.yml` - configuration for session logging to console and/or files
- `qserver/qs-config.yml`    - contains all configuration of the QS host process. See the [documentation](https://blueskyproject.io/bluesky-queueserver/manager_config.html) for more details of the configuration.

## queueserver

The queueserver has a host process that manages a RunEngine. Client sessions
will interact with that host process.

### Run a queueserver host process

Install screen

```bash
sudo apt install screen
```

Use the queueserver host management script to start the QS host process.  The
`restart` option stops the server (if it is running) and then starts it.  This is
the usual way to (re)start the QS host process. Using `restart`, the process
runs in the background.

```bash
./src/YOUR_INSTRUMENT_NAME_qserver/qs_host.sh restart
```

### Run a queueserver client GUI

To run the gui client for the queueserver you can use the next command inside the terminal:

```bash
queue-monitor &
```

### Shell script explained

A [shell script](https://github.com/BCDA-APS/BITS/blob/main/src/apsbits/demo_qserver/qs_host.sh) (`./src/YOUR_INSTRUMENT_NAME_qserver/qs_host.sh`) starts the QS host process. Below
are all the command options, and what they do.

```bash
(BITS_env) $ ./src/YOUR_INSTRUMENT_NAME_qserver/qs_host.sh help
Usage: qs_host.sh {start|stop|restart|status|checkup|console|run} [NAME]

    COMMANDS
        console   attach to process console if process is running in screen
        checkup   check that process is running, restart if not
        restart   restart process
        run       run process in console (not screen)
        start     start process
        status    report if process is running
        stop      stop process

    OPTIONAL TERMS
        NAME      name of process (default: bluesky_queueserver-)
```

Alternatively, run the QS host's startup command directly within the `./qserver/`
subdirectory.

```bash
cd ./qserver
start-re-manager --config=./qs-config.yml
```
