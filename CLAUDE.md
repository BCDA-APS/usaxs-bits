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
   - `scalers_and_amplifiers.yml` (loaded first; `setup_scalers(claim_detector_names=False)` runs after — the FX4 owns the `UPD`/`I0`/`I00`/`TRD` names now, so the scaler must not claim them)
   - `devices.yml` (creates `fx4`, `fx42`, `fx4_autorange`, `fx42_autorange`), `devices_aps_only.yml`, `ad_devices.yml`, `autorange_devices.yml` (binds detector → electrometer/channel/autoranger), then `setup_fx4_channels()` names those channels `UPD`/`I0`/`I00`/`TRD`
   - **then** either `shutters_op.yml` or `shutters_sim.yml` based on `caget("usxLAX:blCalc:userCalc2.VAL") == 1`
5. Suspenders are wired (`suspender_in_operations` vs `suspender_in_sim`) accordingly.
6. Bluesky/apstools plans are imported with `bp`/`bps` prefixes in IPython, but `import *` when `running_in_queueserver()` (so the QS sees flat plan names).
7. User-facing plans from `src/usaxs/plans/*` are imported into the namespace (`Flyscan`, `USAXSscan`, `mode_USAXS`, `tune_*`, `insertSaxsFilters`, etc.). These are the public API surface — when adding a plan, decide whether it belongs in this list.
8. Final calls: `setup_baseline_stream`, customize `usaxs_shutter.delay_s`, `newUser()`.

**Operation vs sim is a runtime decision based on a live PV.** When editing startup or shutter logic, both branches must stay valid.

The decision is made by `utils/operation_mode.determine_in_operation()`, which **raises `OperationModeUnknown` rather than guessing**. It used to be `caget(...) == 1`, and because `caget` returns `None` on a connection timeout and `None == 1` is `False`, an unreachable `iocusxlax` silently selected simulation — `usaxs_shutter` became a `SimulatedApsPssShutterWithStatus` that opens nothing and the suspenders became inert, so tunes ran to completion against a dead beam and reported only a failed fit. Never reintroduce a fallback path: *unknown* must not mean *simulated*. `USAXS_SIMULATE=1` (or `=0`) forces the mode explicitly, and `startup.py` prints a banner naming the mode as the last thing on screen.

### No back-edges into `usaxs.startup`

**No module under `src/usaxs/` may `from usaxs.startup import …` at module top level.** `startup.py` is the only place where `RE`, `bec`, suspenders, and the public plan callables are constructed. This rule prevents the circular import that occurs when `start-re-manager` loads `usaxs.startup` and a plan module tries to read `RE`/`bec`/suspenders from a half-initialised `usaxs.startup`.

Two patterns satisfy the rule:

- **Plans that need `RE` or `bec`** — read them from `sys.modules["__main__"]` (`bec = getattr(sys.modules["__main__"], "bec", None)`), as `utils/fx4_channels.py` and `utils/scalers_setup.py` do, or from a module-level registry that `startup.py` fills with a setter, as `utils/setup_new_user.py` does. **Do not import them lazily inside the function body.** `from usaxs.startup import bec` inside a function looks safe and is not: the queueserver worker executes the startup code as `'__main__'` and then drops its modules from `sys.modules`, so the import re-executes the whole of `startup.py` — inside the running RunEngine loop. On 2026-10-25 one such line in `uascan_plan.py` fired on a session's first step scan: `oregistry.clear()` ran, every `make_devices` then failed with `asyncio.run() cannot be called from a running event loop`, and the worker was left with an empty device registry mid-scan. The only recovery is a worker restart.
- **Plans that need suspender decoration** — use `@beam_guarded` from `src/usaxs/suspenders/beam_guard.py`, applied at the plan's definition site *under* `@plan`. It resolves the suspenders at call time from a registry that `startup.py` fills via `set_beam_suspenders(...)`, so no suspender object is needed at module-load time. Do **not** apply the suspenders by rebinding names in `startup.py` — that only affects the `usaxs.startup` namespace, and user scripts importing `from usaxs.plans.plans_usaxs import USAXSscan` would get the undecorated original. Do not nest guarded plans: installing the same suspender twice and removing it once unguards the outer scope, which is why the `USAXSscan` dispatcher is bare and only `Flyscan`/`USAXSscanStep` carry the decorator.

### Rules about suspensions

From two incidents, 2026-10-24 (a ring dump between a fly scan and the following `saxsExp`) and 2026-10-25 (a deliberate test, a ring dump mid-fly-scan). The underlying behaviour is the RunEngine's and ophyd's in each case; the workarounds are in USAXS code.

- **Every plan must bound its rewind cache.** On suspension the RunEngine rewinds to the last checkpoint and replays every message cached since (`run_engine.py: _rewind`). That cache is *not* cleared by `close_run`, so without a boundary it can span a run: a suspension during `mode_SAXS` rewound into the previous, already-closed fly scan, re-armed the busy record against a half-reconfigured instrument, then replayed the closing baseline `create` with no run open (`open_run`/`close_run` are in `_UNCACHEABLE_COMMANDS`, so they are never replayed) and aborted with `IllegalMessageSequence`. `@beam_guarded` now emits `bps.checkpoint()` before anything else, and `Flyscan_internal_plan` emits one after `close_run`. A new long non-scanning stretch of plan (mode change, stage survey) deserves its own `bps.checkpoint()` — it is only illegal between `create` and `save`.
- **Settle delays go in the `post_plan`, never in `SuspendXxx(sleep=…)`.** When a second suspender trips, `request_suspend` cancels the RunEngine task; `_run` handles that with a bare `continue` while the state is `suspending`, so the earlier helper's `Msg('wait_for')` is never re-issued and the future its `sleep=` gates is no longer awaited. Only the last suspender to trip times the resume. `suspend_white_beam_ready` therefore uses `sleep=0` and opens `mono_beam_just_came_back_but_after_sleep_plan` with `bps.sleep(settle_s)`; `post_plan` does run in that situation.
- **The fly-scan abort is: clear `flying`, write "Done" to the busy record, stop the electrometers.** In that order, nothing else. `flying` goes first because all three suspenders trip within ~100 ms of a dump and each runs the pre_plan — it doubles as the idempotence guard, so invocations two and three return at the top instead of repeating the cleanup. The busy write is the whole abort; the sweep then finishes unmonitored and the IOC's `scanSseq` re-taxis AR/AX/DX on the replay.
- **Do not reach for `usxLAX:USAXSfly:Abort`, however much it looks right.** It drives `fanAbort`, which does properly stop the sequence and the Aerotech — but `usxAERO:pm1:Abort` is a plain `bo` with no self-reset, so it **latches**, and every later profile run fails with `(54000) "This move command was stopped due to an abort command."` Tried 2026-10-25: a replayed sweep sat 65 s before the controller recovered, then ran its full 90 s, and the busy Status expired mid-sweep. If it ever does get latched, clear `usxLAX:USAXSfly:Abort` first and `usxAERO:pm1:Abort` second — a write to the former's `OUT` reaches `fanAbort.PROC`, which processes whatever the value and re-latches the Aerotech.
- **Writing a `put_complete=True` signal the value it already holds hangs for its full timeout.** The Status comes from the CA put-callback, which on a busy record fires only on the return to Done — no transition, no callback. Don't add "belt-and-braces" writes to `usaxs_flyscan.busy`.
- **`timeout_s` must cover the IOC's rebuild and taxi, not just jitter.** The busy Status budget (`scan_time + timeout_s`) starts when the record is armed, and `scanSseq` rebuilds the trajectory and taxis AR/AX/DX before any sweeping happens. At 15 s a replayed sweep died three-quarters done.
- **A suspender `pre_plan` must be short, and must never move a motor.** It can be abandoned part-way: when a second suspender trips, `request_suspend` cancels the RunEngine task and `_run` resumes at the new helper, so whatever message the first pre_plan was waiting on is never re-issued. A three-motor `bps.mv` added to `abort_flyscan_if_flying` on 2026-10-25 left it frozen on its `wait` for three minutes with the moves issued and nobody waiting on them, and the next scan's busy Status aged out. Returning the stages home belongs in `Flyscan`'s own exit path — **still to be done**.
- **`tune_ar` tunes wherever AR happens to be, and that is deliberate — do not "fix" it.** `tune_ar` runs `lineup2` *relative to the current position* over ±`tune_ar_range` (0.0009 deg) and writes where it lands into `ARcenter`, with no comparison against the old value. That is what makes an **energy change** work: the Bragg angle moves the AR centre far more than any tune range, so the operator repositions AR for the new energy and lets the tune adopt it. Two plausible-looking guards were tried on 2026-10-25 and both had to be reverted, because each would have blocked exactly that workflow: moving AR to the stored centre at the top of `preUSAXStune`/`allUSAXStune`, and refusing a `tune_ar` result far from the stored centre. The cost of this openness is that a stranded AR silently redefines the alignment (8.8453 → 8.8202 that same day, after a beam-dump abort left AR mid-sweep); the defence is to never strand the stage — see the abort rule above — not to second-guess the tune. The `usxLAX` IOC autosave rotation (`.../ioc/usxLAX/iocBoot/iocusxLAX/autosave/auto_settings.sav*`) keeps ~8-hourly history of `ARcenter.VAL` and is how to recover a lost value.
- **`bps.mv(..., timeout=X)` does not bound the write.** bluesky's `mv` spends its `timeout` on the group `wait` message and never passes it to `obj.set()`. For an `EpicsSignal` the write budget is ophyd's `write_timeout`, which comes from `OPHYD.TIMEOUTS.PV_WRITE` in `iconfig.yml` — so that one value, not `MASTER_TIMEOUT`, decides when a write raises `FailedStatus`. It is 60 s and deliberately not sharing the 5 s anchor with `PV_READ`/`PV_CONNECTION`: at 5 s a single transient stall aborts the whole command list. Use `bps.abs_set(..., timeout=X)` when a specific write needs its own budget — that one *is* forwarded to `set()`.

### Counting chain: FX4 electrometers (since 2026-09)

UPD, TRD, I0 and I00 read out through **Pyramid FX4 electrometers**, replacing
the Femto amplifier / V-F converter / scaler chain.  Three consequences shape
the code:

- **Readings are gain-independent picoamps.**  Nothing divides by an amplifier
  gain; transmission and data reduction are `diode / I0`.  Range readbacks are
  diagnostics only.
- **One `Range` serves all four channels of an electrometer.**  `fx4` carries
  UPD (ch1) and TRD (ch4), `fx42` carries I0 (ch1) and I00 (ch2).  The sequence
  program's `channel` record selects which one it optimises for, so plans must
  point it at the detector in use — always via
  `fx4_setup.enable_fx4_autorange` or `fx4_autorange_plan.autoscale_amplifiers`,
  never by writing `auto.mode` or `auto.direction` directly.  Getting this wrong
  yields plausible-looking wrong numbers, not an error.
- **`seq01:dir` sets which way the range may move**, and every plan states its
  policy.  `Both` (0) is the normal condition.  `Increase` (1) lets the range's
  max current only increase, i.e. the gain only falls — the program holds its
  range but can still escape a railed one.  Tunes use it, via
  `fx4_setup.autorange_hold_for_peak(<detector being fitted>)`: full
  autoranging cannot follow the climb into a peak, so the peak tops out and the
  fitted profile is distorted.  Step and fly scans, and the wide `find_ar` /
  `find_a2rp` searches, use `Both`.  The record is **autosaved in the IOC**, so
  it is written unconditionally on every `enable_fx4_autorange` call rather than
  assumed; that is also what clears it after a tune aborts mid-scan.
- **Count times are quantised to whole mains cycles** so 60 Hz pickup averages
  out (`utils.count_time.quantize_count_time`).

Key modules: `devices/fx4_quadem.py` (device layer), `plans/fx4_setup.py` (mode
configuration, channel selection, plot selection), `plans/fx4_autorange_plan.py`
(autoscale, dark currents), `utils/fx4_channels.py` (names the channels `UPD` /
`I0` / `I00` / `TRD`), `utils/fx4_ranges.py`.

`scaler0`, `scaler1` and `struck` are still declared so the old chain can be
restored, but nothing feeds them — **do not use them in new code**.  Rollback is
a branch switch, not a runtime flag: the hardware is rewired.

`PLAN.md` is the running record of the conversion, including what has not yet
been verified against hardware.  `ADconfigs/` holds the IOC-side data-format
configuration.

### Device configuration is YAML, not Python

Devices are declared in `src/usaxs/configs/*.yml` in Guarneri format (`module.path.ClassName: [{name, prefix, labels, ...}]`) and instantiated by `make_devices`. Device classes live in `src/usaxs/devices/`. To add a device, write the class **and** add an entry to the appropriate YAML — it will not appear in `oregistry` otherwise. Devices labeled `baseline` are added to the baseline stream by `setup_baseline_stream`.

### Three plan directories — don't confuse them

- **`src/usaxs/plan_templates/`** — canonical, ready-to-copy plan templates (`templates_dir` for the plan-writing agent). Never run directly and never edited in place: copy to `src/usaxs/user/` first. Excluded from `ruff`. See `src/usaxs/plan_templates/README.md`.
- **`src/usaxs/user/`** — committed, importable user plans for specific samples/setups (linkam, ptc10, etc.), and where new user plans are written (`saved_scripts_dir`). Loaded with `%run -im usaxs.user.<name>`.
- **`user/` (repo root)** — obsolete pre-BITS-cleanup scripts kept only for lookup; they will not run and lack Obsidian logging. Treat as scratch space; do not refactor without asking.

`SKILL.md` (repo root) is the orientation file loaded by the plan-writing agent; keep it in sync when the plan API or directory layout changes.

### Callbacks

`src/usaxs/callbacks/` includes optional NeXus and SPEC writers, gated by `iconfig.yml` flags (`NEXUS_DATA_FILES.ENABLE`, `SPEC_DATA_FILES.ENABLE`). SPEC is enabled by default; NeXus is off. Fly-scan HDF5 output is separate (`usaxs_flyscan_support/saveFlyData.py`) and writes to `USAXS_FLY_SCAN_SETTINGS.SAVE_FLY_DATA_HDF5_DIR` from iconfig.

### Obsidian logging

`src/usaxs/utils/obsidian.py` writes machine-generated Markdown entries into a shared Obsidian vault at `/share1/Obsidian/Experiments/YYYY-P/Instrument_Records/`. The `recordUserStart`, `recordNewSample`, `recordRunCommandFile`, `recordBeamDump`, etc. helpers are wired into plans and `newUser()`. Entries are append-only; staff notes coexist in the same files.

## Style

- `ruff` (replaces flake8 + isort + black) and `ruff-format` via pre-commit. Line length 88 for `ruff`, 115 for `black` config (legacy). Force single-line imports.
- Pre-commit excludes `user/` and `src/usaxs/original_plans/` from `ruff`.
- Pytest is configured with `-x` (stop on first failure) and ignores Deprecation/PendingDeprecation warnings.
