# Gemini Code Assistant Report

This document provides a summary of the `usaxs-bits` project, a Bluesky-based control system for the USAXS instrument at the Advanced Photon Source (APS).

## Project Overview

The `usaxs-bits` project is a Python-based control system for the USAXS instrument at the APS. It uses the Bluesky framework for experiment orchestration and data acquisition. The project is structured to separate device definitions, plans, and other components into distinct modules.

### Key Technologies

*   **Python:** The primary programming language.
*   **Bluesky:** A data acquisition and experiment control framework for scientific instruments.
*   **Ophyd:** A library for defining and interacting with hardware devices.
*   **EPICS:** A set of software tools and applications used to create distributed control systems for scientific instruments.
*   **YAML:** Used for configuration files, such as device definitions.

### Architecture

The project follows a standard Bluesky architecture:

*   **`src/usaxs/startup.py`:** The main entry point for initializing the Bluesky environment. It loads devices, plans, and callbacks.
*   **`src/usaxs/configs/*.yml`:** YAML files that define the hardware devices and their configurations.
*   **`src/usaxs/devices/*.py`:** Python modules that define custom `ophyd` device classes.
*   **`src/usaxs/plans/*.py`:** Python modules that define Bluesky plans for running experiments.
*   **`src/usaxs/callbacks/*.py`:** Python modules that define callbacks for processing and saving data.

## Building and Running

The project is packaged using `setuptools` and can be installed using `pip`. The `pyproject.toml` file defines the project's dependencies and build system.

### Installation

To install the project and its dependencies, run the following command from the root of the repository:

```bash
pip install -e .
```

### Running the Bluesky Environment

The Bluesky environment can be started by running the `startup.py` script. This will initialize the RunEngine, load the devices, and make the plans available for execution.

```bash
ipython -i -m usaxs.startup
```

### Running Experiments

Experiments are run by executing Bluesky plans in the `ipython` environment. For example, to run a USAXS scan, you would use the `USAXSscan` plan:

```python
RE(USAXSscan(x=0, y=0, thickness_mm=1, title="My Sample"))
```

## Development Conventions

The project follows standard Python development conventions.

*   **Linting and Formatting:** The project uses `ruff`, `black`, and `isort` for code linting and formatting. A `pre-commit` configuration is provided to automatically run these tools before each commit.
*   **Testing:** The project uses `pytest` for testing.
*   **Documentation:** The project uses `sphinx` for generating documentation.
*   **Git:** The project is managed using `git` and is hosted on GitHub.

### Adding New Devices

To add a new device, you will need to:

1.  Define the device in a YAML file in the `src/usaxs/configs` directory.
2.  If necessary, create a new `ophyd` device class in a Python module in the `src/usaxs/devices` directory.
3.  Load the device in the `src/usaxs/startup.py` script.

### Adding New Plans

To add a new plan, you will need to:

1.  Create a new Python module in the `src/usaxs/plans` directory.
2.  Define the plan in the new module.
3.  Import the plan in the `src/usaxs/startup.py` script.
