# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Bluesky data-acquisition package for the **USAXS / SAXS / WAXS** instrument at **APS 12-ID-E**. Built on top of the `apsbits` BITS framework (BCDA-APS). Python 3.11. Package name: `bits_usaxs`; importable as `usaxs`.

The repo replaces the pre-2023 `usaxs-bluesky-ended-2023` codebase. Hardware-specific — most code only makes sense when EPICS PVs at 12-ID-E (`usxLAX:`, `usxTerms:`, etc.) are reachable.

## Common commands

```bash
# Environment (one-time)
export CONDA_ENV=bits_usaxs
conda create -y -n "${CONDA_ENV}" python=3.11 pyepics
conda activate "${CONDA_ENV}"
pip install -e .
pip install git+https://github.com/BCDA-APS/apstools  # pre-release for APS cycle exception

# Lint (CI runs this — must pass before merge)
pre-commit run --all-files

# Tests (CI matrix, py3.11; -x stops on first failure per pyproject.toml)
pytest

# Run a single test
pytest path/to/test_file.py::test_name

# Start IPython console session (loads usaxs.startup)
./scripts/start-usaxs-bits.sh

# Queueserver (must run on the QS host; uses redis on localhost:6379)
./src/usaxs_qserver/qs_host.sh {start|stop|restart|status|console}
```

## Architecture

### Startup flow — read `src/usaxs/startup.py` first

`startup.py` is the single entry point for **both** the IPython console and the queueserver. It runs top-to-bottom on import:

1. Loads `src/usaxs/configs/iconfig.yml` (RunEngine metadata, BEC, callbacks, scaler PVs, fly-scan paths, OPHYD timeouts).
2. `init_instrument("guarneri")` creates the device manager; `oregistry.clear()` discards apsbits' default devices so only USAXS devices remain.
3. `init_RE` builds `RE`, `sd`, with `bec` and `cat` (databroker `usaxs`) as subscribers.
4. `make_devices(file=...)` is called multiple times against per-area Guarneri YAML files in `configs/`:
   - `scalers_and_amplifiers.yml` (loaded first; `setup_scalers()` runs after)
   - `devices.yml`, `devices_aps_only.yml`, `ad_devices.yml`, `autorange_devices.yml`
   - **then** either `shutters_op.yml` or `shutters_sim.yml` based on `caget("usxLAX:blCalc:userCalc2.VAL") == 1`
5. Suspenders are wired (`suspender_in_operations` vs `suspender_in_sim`) accordingly.
6. Bluesky/apstools plans are imported with `bp`/`bps` prefixes in IPython, but `import *` when `running_in_queueserver()` (so the QS sees flat plan names).
7. User-facing plans from `src/usaxs/plans/*` are imported into the namespace (`Flyscan`, `USAXSscan`, `mode_USAXS`, `tune_*`, `insertSaxsFilters`, etc.). These are the public API surface — when adding a plan, decide whether it belongs in this list.
8. Final calls: `setup_baseline_stream`, customize `usaxs_shutter.delay_s`, `newUser()`.

**Operation vs sim is a runtime decision based on a live PV.** When editing startup or shutter logic, both branches must stay valid.

### No back-edges into `usaxs.startup`

**No module under `src/usaxs/` may `from usaxs.startup import …` at module top level.** `startup.py` is the only place where `RE`, `bec`, suspenders, and the public plan callables are constructed. This rule prevents the circular import that occurs when `start-re-manager` loads `usaxs.startup` and a plan module tries to read `RE`/`bec`/suspenders from a half-initialised `usaxs.startup`.

Two patterns satisfy the rule:

- **Plans that need `RE` or `bec`** — import them lazily *inside* the function body (`def my_plan(...): from usaxs.startup import RE, bec; ...`). The import resolves at first call, well after `startup.py` has finished loading.
- **Plans that need suspender decoration** (`@bpp.suspend_decorator(suspend_FE_shutter)`) — export the plan **bare** from its module (no decorators) and apply the suspenders in `startup.py`'s wiring block via `_with_beam_suspenders(...)`. Decorators evaluate at module-load time, so they cannot use lazy imports.

### Device configuration is YAML, not Python

Devices are declared in `src/usaxs/configs/*.yml` in Guarneri format (`module.path.ClassName: [{name, prefix, labels, ...}]`) and instantiated by `make_devices`. Device classes live in `src/usaxs/devices/`. To add a device, write the class **and** add an entry to the appropriate YAML — it will not appear in `oregistry` otherwise. Devices labeled `baseline` are added to the baseline stream by `setup_baseline_stream`.

### Two `user/` directories — don't confuse them

- **`user/` (repo root)** — ad-hoc experiment scripts loaded interactively with `%run -i user/foo.py` from the IPython session. They are excluded from `ruff`, `black`, and most lint. Treat as scratch space; do not refactor without asking.
- **`src/usaxs/user/`** — committed, importable user plans for specific samples/setups (linkam, ptc10, etc.). These are part of the package and subject to lint.

### Callbacks

`src/usaxs/callbacks/` includes optional NeXus and SPEC writers, gated by `iconfig.yml` flags (`NEXUS_DATA_FILES.ENABLE`, `SPEC_DATA_FILES.ENABLE`). SPEC is enabled by default; NeXus is off. Fly-scan HDF5 output is separate (`usaxs_flyscan_support/saveFlyData.py`) and writes to `USAXS_FLY_SCAN_SETTINGS.SAVE_FLY_DATA_HDF5_DIR` from iconfig.

### Obsidian logging

`src/usaxs/utils/obsidian.py` writes machine-generated Markdown entries into a shared Obsidian vault at `/share1/Obsidian/Experiments/YYYY-P/Instrument_Records/`. The `recordUserStart`, `recordNewSample`, `recordRunCommandFile`, `recordBeamDump`, etc. helpers are wired into plans and `newUser()`. Entries are append-only; staff notes coexist in the same files.

## Style

- `ruff` (replaces flake8 + isort + black) and `ruff-format` via pre-commit. Line length 88 for `ruff`, 115 for `black` config (legacy). Force single-line imports.
- Pre-commit excludes `user/` and `src/usaxs/original_plans/` from `ruff`.
- Pytest is configured with `-x` (stop on first failure) and ignores Deprecation/PendingDeprecation warnings.
