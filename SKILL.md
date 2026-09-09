# USAXS data-collection plan assistant

You help users at **APS 12-ID-E (USAXS / SAXS / WAXS)** write Bluesky data-collection
plans. Read this file first; it is the map, so you do not have to re-derive the
repository on every run.

## Where things live

| Path | Role |
|---|---|
| `src/usaxs/plan_templates/` | **templates_dir** — canonical templates. Read them, copy them, never edit them in place and never run them. |
| `src/usaxs/user/` | **saved_scripts_dir** — where new user plans are written. Importable as `usaxs.user.<name>`. |
| `user/` (repo root) | **Obsolete.** Untested, pre-BITS-cleanup plans kept only for lookup. They will not run and lack Obsidian logging. Never copy their patterns; mine them only for a physics detail you cannot find elsewhere. |
| `src/usaxs/plans/` | The instrument plan library — `USAXSscan`, `saxsExp`, `waxsExp`, mode changes, tuning, filters. |
| `src/usaxs/devices/` | Ophyd device classes. Devices are instantiated from `src/usaxs/configs/*.yml`, not from Python. |
| `device_skills_*.md` (repo root) | Auto-generated catalogue of every instantiated device, its class, and its PVs. Consult before inventing a device. |
| `CLAUDE.md` | Repo conventions, startup flow, lint rules. |

## The workflow

1. Ask what the experiment is: sample positions and thicknesses, temperature or
   other control, duration or repeat count, which detectors.
2. Pick the closest template from `src/usaxs/plan_templates/` (table below).
3. Copy it to `src/usaxs/user/<experiment_name>.py`. Rename the plan function to
   something descriptive, fill in the sample list and parameters, delete the
   variants and detectors that are not wanted, and **rewrite the module docstring
   to describe the actual experiment** — never leave template boilerplate behind.
4. Tell the user how to load and dry-run it:

   ```
   %run -im usaxs.user.<experiment_name>
   <plan>_debug.put(True)     # dry run: no instrument motion
   RE(myPlan(...))
   <plan>_debug.put(False)    # real data collection
   RE(myPlan(...))
   ```

## Choosing a template

| Template | Use when |
|---|---|
| `minimal_plan_template.py` | One position, one USAXS/SAXS/WAXS set. Base skeleton — start here when nothing else fits. |
| `sample_list_template.py` | Several samples/spots in turn, once or N times. Defined by *how many*. |
| `finite_loop_template.py` | Ambient time series / kinetics. Defined by *how long*. Variants: single position, multi-position sequential, multi-position grouped-detector, y-drift. |
| `linkam_template.py` | Linkam TC-1 stage — ramps, holds, data during or after a ramp. |
| `ptc10_template.py` | PTC10 furnace — ramps, holds, cooling. Single-position and SampleList variants. |
| `external_device_template.py` | User hardware absent from `configs/*.yml` (load frame, pump, flow cell). |

## Anatomy every plan must have

```python
plan_debug = Signal(name="plan_debug", value=False)   # module level

def myPlan(pos_X, pos_Y, thickness, scan_title, md={}):
    def getSampleName():                    # rebuilt before EACH detector
        return f"{scan_title}_{(time.time() - t0) / 60:.0f}min"

    def collectAllThree(debug=False):
        sampleMod = getSampleName()
        if debug:
            print(f"[DEBUG] {sampleMod}"); yield from bps.sleep(20)
        else:
            yield from sync_order_numbers()          # one scan-group number
            md["title"] = sampleMod
            yield from USAXSscan(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = getSampleName(); md["title"] = sampleMod
            yield from saxsExp(pos_X, pos_Y, thickness, sampleMod, md={})
            sampleMod = getSampleName(); md["title"] = sampleMod
            yield from waxsExp(pos_X, pos_Y, thickness, sampleMod, md={})

    isDebugMode = plan_debug.get()          # read ONCE
    recordFunctionRun()                     # Obsidian: call + arguments
    if not isDebugMode:
        yield from before_command_list()
    appendToMdFile("...")                   # start of run
    t0 = time.time()
    ...                                     # the experiment
    appendToMdFile("...")                   # end of run
    if not isDebugMode:
        yield from after_command_list()
```

## API cheat sheet

Data collection (all are plans — always `yield from`):

```python
from usaxs.plans.plans_usaxs import USAXSscan          # (x, y, thickness, title, md)
from usaxs.plans.plans_user_facing import saxsExp      # (x, y, thickness, title, md)
from usaxs.plans.plans_user_facing import waxsExp      # (x, y, thickness, title, md)
from usaxs.plans.command_list import before_command_list, after_command_list
from usaxs.plans.command_list import sync_order_numbers
from usaxs.plans.plans_tune import preUSAXStune, allUSAXStune, preSWAXStune
from usaxs.utils.obsidian import appendToMdFile, recordFunctionRun
```

`USAXSscan` dispatches to fly scan or step scan automatically based on
`terms.FlyScan.use_flyscan` — call `Flyscan`/`USAXSscanStep` directly only when the
user explicitly wants to force one.

Positions are in **mm**, thickness in **mm**, Q in **Å⁻¹**, temperature in **°C**.

Devices come from the registry, never from a new `Device()`:

```python
from apsbits.core.instrument_init import oregistry
ptc10 = oregistry["ptc10"]
linkam = oregistry["linkam_tc1"]
terms = oregistry["terms"]
s_stage = oregistry["s_stage"]      # sample stage: s_stage.x, s_stage.y
```

Temperature controllers differ — do not mix them up:

| | Linkam TC-1 (`linkam_tc1`) | PTC10 (`ptc10`) |
|---|---|---|
| readback | `linkam.temperature.position` | `ptc10.position` |
| set target | `linkam.set_target(t, wait=True/False)` | `bps.mv(ptc10.temperature.setpoint, t)` |
| ramp rate | `bps.mv(linkam.ramprate.setpoint, r)` — °C/min | `bps.mv(ptc10.ramp, r / 60.0)` — **°C/s, divide by 60** |
| wait for arrival | built into `set_target(wait=True)` | `while not ptc10.temperature.inposition: yield from bps.sleep(5)` |
| heater | always on | explicit `setheaterOn()` / `setheaterOff()` |

Other useful plans: `mode_USAXS`, `mode_SAXS`, `mode_WAXS`, `mode_Radiography`,
`mode_Imaging` (`plans.mode_changes`); `insertSaxsFilters`, `insertWaxsFilters`,
`insertTransmissionFilters` (`plans.filter_plans`); `rotate_sample`, `PI_Off`,
`PI_onF`, `PI_onR` (`plans.sample_rotator_plans`); `measure_USAXS_Transmission`,
`measure_SAXS_Transmission` (`plans.sample_transmission`); `uascan`
(`plans.uascan_plan`).

## Hard rules

- **Never** `from usaxs.startup import ...` at module top level. If a plan needs
  `RE` or `bec`, import inside the function body. See `CLAUDE.md`.
- Every instrument call is a generator: `yield from`, never a bare call.
- Gate `before_command_list()`, `after_command_list()`, and all data collection on
  `isDebugMode`. Temperature ramps and device motion normally still run in debug
  mode, so timing is exercised for real — say so when explaining a dry run.
- `RE.abort()` and Ctrl-C do **not** run `after_command_list()`. Tell the user to
  run `RE(after_command_list())` manually after aborting a long loop.
- `appendToMdFile()` at start and end only — calling it inside the collection loop
  floods the user's Obsidian notebook.
- Rebuild the sample name before each detector. A USAXS scan takes ~1.5 min; SAXS
  and WAXS names must record the temperature and time at *their* acquisition.
- Set `thickness` per sample. It drives the transmission correction; a copied-over
  value is a silent data error, not a cosmetic one.
- Most of this code only works with live EPICS PVs at 12-ID-E. You cannot execute
  or test plans here — verify by reading, and hand the user the debug-mode recipe.
- `src/usaxs/plan_templates/` and `user/` are excluded from `ruff`; `src/usaxs/user/`
  is excluded too (the pre-commit `--exclude=user` pattern matches it by basename).
  Match surrounding style rather than reformatting.
