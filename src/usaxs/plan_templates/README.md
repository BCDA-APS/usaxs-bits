# `src/usaxs/plan_templates` — canonical plan templates

Templates only. **Nothing in this directory is run as an experiment.**
Copy a template to `src/usaxs/user/<experiment_name>.py`, edit the copy, then
load it with `%run -im usaxs.user.<experiment_name>`.

| Template | Use when |
|---|---|
| `minimal_plan_template.py` | One position, one USAXS/SAXS/WAXS set. The base skeleton — start here when nothing else fits. |
| `sample_list_template.py` | Several samples / spots measured in turn, once or N times. Defined by *how many*. |
| `finite_loop_template.py` | Ambient-temperature time series or kinetics. Defined by *how long*. Four variants: single position, multi-position sequential, multi-position grouped-detector, y-drift. |
| `linkam_template.py` | Linkam TC-1 temperature stage: ramps, holds, data during or after a ramp. |
| `ptc10_template.py` | PTC10 furnace: ramps, holds, cooling. Single-position and SampleList variants. |
| `external_device_template.py` | User hardware not declared in `src/usaxs/configs/*.yml` (load frame, pump, flow cell). Shows how to wrap PVs in an ophyd `Device`. |

Every template carries the same mandatory structure:

1. module-level `logger` and a debug `Signal`
2. inner `getSampleName()` — rebuilt before *each* detector
3. inner `collectAllThree(debug)` — with a debug branch that prints and sleeps
4. `recordFunctionRun()` at plan start
5. `before_command_list()` / `after_command_list()`, both gated on `isDebugMode`
6. `appendToMdFile()` at start and end — never inside the collection loop

Older, thinner variants of the Linkam and PTC10 templates remain in
`src/usaxs/user/` (`linkam_template.py`, `ptc10_planG.py`) for reference only.
