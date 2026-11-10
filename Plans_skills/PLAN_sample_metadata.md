# PLAN — Sample metadata from the usxSample IOC

## 0. Current state — read this first

**Branch:** `December2026` (general development branch, off `main` @ ada1010).
This project is one of several on it; `main` stays the known-good fallback.
**Last updated:** 2026-11-10. **Status:** Steps 1 (survey) and 2 (schema)
done; findings in §0.1, answers in §0.2, Step 2 choices in §0.3. Next: Step 3
(IOC records; agree a restart time). The step-by-step order is §12.
Decisions are in §11.

### 0.1 Step 1 findings (2026-11-10)

**usxSample IOC**
* Top: `/net/s12dserv/xorApps/epics/synApps_6_3/ioc/usxSample/`. Runs on
  **`usaxsserver`** under procServ. Start/stop/restart with
  `iocBoot/iocusxSample/softioc/usxSample.pl {start|stop|restart|status|console}`
  (the `usxSample` alias in `bash_ioc_aliases` only exists on `usaxsserver`).
  Logs: `iocBoot/iocusxSample/softioc/logs/iocConsole/`. Last boot 2026-11-09 12:05.
* **Already version-controlled:** its own git repo,
  `git@git.aps.anl.gov:12ID/usxSample.git` (owner kpetersn; working tree clean
  except `temp/` and `autosave/dbior.log`). Git as `usaxs` needs
  `-c safe.directory=…`. So §5.2 is settled: edit the IOC repo, don't copy the
  database into this repo.
* Database: `usxSampleApp/Db/SampleTerms.db`, installed to `db/` by `make`
  (the two copies are identical now). Loaded in `st.cmd.Linux` with
  `P=usxSample:`. **Add the new records to this file and run `make`.**
* **All 15 records exist, including `Density`** (the Python device lacks it).
  `Description` and `ChemicalFormula` are already **`waveform` FTVL=CHAR,
  NELM=1024**, so long strings are solved. `ProcedureName` follows the same
  pattern. Numeric fields are `ao` with no `PREC` (displays as integers); the
  `*Dir` fields are `mbbo` X/Y/Z.
* Units bugs in the `.db`: `Density` EGU is `cm3/g` (should be `g/cm3`);
  `MagneticField`/`StressField` have no EGU.
* **Autosave is ON, contrary to D6.** `auto_settings.req` is empty, but
  `autosaveBuild` (`common.iocsh`) automatically adds
  `SampleTerms_settings.req` to `autosave/built_settings.req`, and
  `built_settings.sav` is restored in pass 0 and pass 1. That covers `.VAL`,
  `.DESC` and `.EGU` of every field, which is why the IOC holds 20 / 1 / 1 / 1
  after a reboot. **Step 3 must stop this**: delete (or empty)
  `SampleTerms_settings.req` in `usxSampleApp/Db` and `db/`, then remove the
  stale entries from `built_settings.sav` before restarting, or the restore
  brings back the old `.EGU` values as well.
* **Live values today are placeholders that every data file records as
  real:** Temperature 20, Density 1, Concentration 1, VolumeFraction 1,
  SLD 1, fields 0, directions X, strings empty. `usxLAX:sampleThickness` = 4.
* **NaN round trip works.** `caput usxSample:Temperature nan` reads back NaN
  in caget and pyepics (`math.isnan` True), and autosave stored `nan`. A NaN
  `ao` goes to **SEVR INVALID / STAT UDF**: a usable "unset" marker on a
  screen, and ophyd/pyepics still return the value. A 60-char string
  round-trips through `Description`, and `""` clears it. (Test values were
  restored: Temperature 20, Description empty.)

**AreaDetector**
* Live config dir confirmed: `/share1/AreaDetectorConfig/`, itself a git repo
  with uncommitted changes. Layouts live in a **`hdf5_plugin/`** subdirectory:
  `SAXS_config/hdf5_plugin/layout.xml`, `WAXS_config/hdf5_plugin/layout_waxs.xml`;
  `attributes.xml` is directly in `SAXS_config/` / `WAXS_config/`. All four
  are **identical to `ADconfigs/` in this repo**.
* Eiger IOC (`usaxs_eiger1`, under the synApps_6_3 `ioc/` tree): **ADCore
  R3-13**. `PVAttribute.cpp` reads a `DBF_CHAR` waveform requested as
  `dbrtype="DBR_STRING"` as a full string of all NELM elements (lines 237-243,
  270-274), so **long strings do reach the Eiger files**. The existing
  `Sample_Description` attribute already uses that form.
* Pilatus IOC (`usaxs_pilatus3:`): **not in the synApps_6_3 `ioc/` tree**,
  and its PVs did not answer on 2026-11-10 (the Eiger's didn't either; both
  were probably off). The ophyd device uses `ImagePlugin_V34`, so ADCore ≥ 3.4.
  The char-waveform-as-string path dates from ADCore 2.x, so it very likely
  works; verify in Step 8.

**Fly scan**
* The writer reads `/share1/AreaDetectorConfig/FlyScan_config/saveFlyData.xml`
  (`saveFlyData.py:52`). It **differs from `ADconfigs/`**: the repo adds
  `AR_PulseLength`/`AR_PulsePeriod`, which are not deployed. Deploy that change,
  or decide against it, before Step 7, so the two don't drift further.
* Confirmed: without `string="true"`, `Description`/`ChemicalFormula` are
  written as uint8 arrays (`preliminaryWriteFile` only asks for
  `as_string=True` when the attribute is set). Fly XML also lacks `Density`.

**X-ray shutter (§7.6)**
* `usaxs_shutter` = `12idc:uniblitz:shutter:{open,close}`, which are `fanout`
  records into `…:open_action`/`close_action` (`stringout`) →
  `12idc:uniblitz:asyn.AOUT`. The asyn record is **write-only (TMOD=Write)**,
  so there is **no true state readback**.
* Best available signal: a CA monitor on **`12idc:uniblitz:asyn.AOUT`**
  (`'@'` = open, `'A'` = close). It posts on every command from any client
  (Bluesky, caQtDM, scripts), even when the value doesn't change. It records
  *commanded* state, not measured state, but it is far more complete than
  instrumenting call sites. **Recommend it over §7.6's call-site method.**
* Call sites for comparison: ~80 `bps.mv(usaxs_shutter, …)` in `src/usaxs/plans/`,
  mostly `axis_tuning.py`, `plans_tune.py`, `mode_changes.py`,
  `plans_usaxs.py`, `sample_transmission.py`, `move_instrument.py`,
  `fly_scan_plan.py`, `uascan_plan.py`, `tune_guard_slits.py`.
* **Use Jan's existing tracker: `usxLAX:userStringCalc10.VAL`** (DESC
  "ShutterOpen-QT used"). A `scalcout` at 0.1 s SCAN with
  `INAA = 12idc:uniblitz:asyn.AOUT`, `CALC = AA="@"`: VAL is 1 while the last
  command was *open*, 0 otherwise. After a `12idc` IOC restart AOUT is empty,
  so VAL reads 0 until the first shutter command re-syncs it; after that it
  tracks well. Bluesky CA-monitors VAL and integrates the time spent at 1.
  This replaces §7.6's call-site method; no plan's shutter calls need editing.

### 0.2 Answers (Jan, 2026-11-10)
* **Tunes:** the sample is out of the beam during tunes, apart from rare
  occasions, and exposure accounting may assume it is always out. So the
  accumulator integrates tracker-open time **only while one of the five data
  plans is running** (outermost scope, the same depth rule as
  `@obsidian_logged`), not around the clock. Step 5 checks whether any data
  plan runs a tune inside that scope, and pauses the accumulator there if so.
* **AD IOCs:** Pilatus runs on its own Linux computer, Eiger on
  `usaxsserver`. Staff restart both by hand, and Bluesky fails without them, so
  code may assume they are up whenever the instrument is operating. Step 7
  deploys the XML files and asks staff to restart both.
* **usxSample commits:** neither `usaxs` nor Jan has push rights to
  `12ID/usxSample`. Commit locally in the IOC working tree; **Kevin
  (kpetersn) pushes.**
* **UV TTL:** no fixed setup. Last time a generic TTL output on the LabJack
  `usxLJ7` was cabled to the source, and something similar is likely. The
  exposure template takes the TTL signal as a **parameter** and its docstring
  says so (Step 6).
* **Fly-scan XML:** the deployed `saveFlyData.xml` lacked the FX4 additions
  from `f181f20` (`AR_PulseLength`/`AR_PulsePeriod`). Deploy the repo version
  now, separately from this project (see §0.3).

### 0.3 Step 2: schema choices (2026-11-10)
`src/usaxs/utils/sample_metadata_schema.py` holds the table;
`tests/test_sample_metadata_schema.py` checks it against the device and the
four XML files. Checks for later steps are `xfail(strict=True)`: the device
check until Step 4, the XML checks until Step 7. Choices made beyond §4:
* **Integer fields** (`StepIndex`, `SeriesIndex`, `RheoPulseCount`) are `ao`
  with `PREC=0`, not `longout`, so that they can be NaN when unset.
* **`ExposureOn`** is an `mbbo` Unset/Off/On, not a `bo`, for the same reason.
* **Field directions** (`*FieldDir`) keep their X/Y/Z states: a direction
  means nothing while its field is NaN, and renumbering the states would change
  the meaning of existing files.
* **Enums are written as strings everywhere.** The AD attributes already use
  `DBR_STRING`; Step 7 adds `string="true"` to the fly-scan enums too, which
  were written as integer indices.
* **Directions get their own datasets** (`magnetic_field_direction`, …) in the
  AD layouts, as the fly-scan file already has. The existing `direction`
  attribute stays, so the change is additive.
* **Units chosen** where the IOC had none: `MagneticField` T, `StressField`
  MPa. `Density` g/cm3 (the IOC's `cm3/g` is wrong). **Check these with Jan.**
* `BoundTitle` is a char waveform (titles go up to 255 characters).

---

## 1. Goal

Every data file — USAXS fly scan, USAXS step scan, SAXS (Pilatus), WAXS
(Eiger) — carries **structured** metadata describing the sample and what was
being done to it: heating procedure, time-series position, rheometer pulses,
radiation exposure, and other environments as they come. Today all of that
exists only as text encoded in the sample title (`MySample_200C_22min`),
rounded to the nearest minute.

Sample metadata that is wrong is worse than none. A required part of this
work is a reliable way to **unset** metadata when the sample changes.

## 2. What exists today

| Piece | State |
|---|---|
| `devices/sample_data.py` `SampleDataDevice` (`sample_data`) | 14 PVs under `usxSample:`. Labelled `baseline` in `devices.yml`, so step scans already record it in the baseline stream. |
| `SampleDataDevice.resetAll()` | **Nothing calls it.** It writes made-up physical values (25 °C, concentration = volume fraction = SLD = 1), which can't be told apart from real data. |
| `ADconfigs/SAXS_config`, `WAXS_config` `attributes.xml` | All 14 PVs **plus `usxSample:Density`**, which the Python device does not have. Check against the IOC. |
| `SAXS_config/layout.xml` | Explicit `/entry/sample` (NXsample) placement for all of them. |
| `Flyscan_config/saveFlyData.xml` | NXsample group with the 14 PVs. `description` and `chemical_formula` lack `string="true"`. Concentration units disagree with the AD files. |
| Step-scan NeXus (`NXWriterUascan`, enabled) | `/entry/sample` gets only `name` and `thickness`. The `sample_data` baseline is in the file's streams but not linked into NXsample. |
| Plans and templates | **No plan writes any `usxSample:` PV.** Temperature and time live only in the title strings built by `getSampleName()`/`setSampleName()` in each template. |
| Matilda | Already reads `/entry/sample` into a dict (`supportFunctions.py:178`). Its blank rule is "title contains `blank`, any case" (`readfromtiled.py:344`). |

The plumbing exists from end to end. What's missing is (a) fields for
procedures, series, exposure and rheometer, (b) code that writes the PVs, and
(c) a lifecycle that clears them.

## 3. Design principles

1. **The IOC PVs are the single source of truth.** The AD IOCs and the fly-scan
   writer can only read PVs, so any value that is not a PV cannot reach three of
   the four file types. Bluesky reads the same PVs (baseline plus a start-document
   snapshot). Never keep a Bluesky-only copy.
2. **Titles keep their encoding: critical, not optional.** Users and the
   downstream software (Matilda, pyIrena) parse the `_200C_22min`-style
   suffixes, and there is no other heater convention. The structured metadata
   is **in addition to** the title encoding, never a replacement. One helper
   builds the title **and** writes the PVs from the same values, so the two
   can't disagree, and a test pins the title format byte for byte.
3. **Unset is NaN or `""`, never a plausible value.** The one exception is
   **thickness** (`usxLAX:sampleThickness`, not a usxSample PV): its default
   stays **1**, because data reduction breaks on NaN, and 1 makes later
   recalibration (powders) easy. A known, accepted limitation. Clearing never
   touches thickness.
4. **One field schema, enforced by a test.** A Python table (name, PV, type,
   units, NeXus path, scope) is checked against the device and all XML
   templates. Adding a field without updating every file fails CI.
5. **Additions only in the files.** No existing HDF5 path moves or changes
   meaning. `config_version` goes from 2.0 to 2.1 in the AD layouts and the
   fly-scan XML.
6. **No autosave for usxSample** (agreed). Reboots are rare, and setting
   metadata before each sample is the routine. The IOC boots to Unset.

## 4. Field schema

Each field has a **scope**, which decides who writes it and when it is cleared:

* **sample**: a property of the specimen (what it *is*). Survives across the
  scans of one sample, including an in-situ series.
* **environment**: what is being done to it *now*. Rewritten before every
  scan by the plan that owns the experiment.
* **bookkeeping**: describes the state of the metadata itself.

### A. Sample properties — scope *sample* (existing + Density)
Description, ChemicalFormula, Concentration, VolumeFraction,
ScatteringLengthDensity, **Density** (add to the device), MagneticField(+Dir),
StressField(+Dir), ElectricField(+Dir), XTranslation, RotationAngle.
Title and thickness stay in `usxLAX:` as now.

### B. Environment type and heating — scope *environment*
| PV | Type | Notes |
|---|---|---|
| `EnvType` | mbbo | None, Ambient, Linkam, PTC10, Rheometer, Other. Covers what the templates support now; more states can be added later. |
| `ProcedureName` | long string | **Generated by the template from its own arguments** (e.g. "Linkam: 20 C/min to 200 C, hold 30 min, cool 100 C/min to 40 C"), so the operator doesn't type it. |
| `ProcedureStep` | stringout | `baseline` / `heat` / `hold` / `cool` / `final` / `pre` / `post` / … |
| `StepIndex` | longout | segment number |
| `Temperature` | ao (exists) | **measured** at scan start, from the controller readback |
| `TemperatureSetpoint` | ao | °C |
| `RampRate` | ao | °C/min, 0 for a hold |
| `TemperatureSource` | stringout | `linkam_tc1`, `ptc10`, `manual` |

### C. Time series — scope *environment*
| PV | Type | Notes |
|---|---|---|
| `SeriesName` | stringout | groups the scans of one series |
| `SeriesIndex` | longout | 0, 1, 2 … |
| `SeriesT0` | ao, epoch s | the "t0" the templates reset. Exact elapsed time = frame timestamp − T0, with no rounding |
| `ElapsedTime` | ao, s | written at scan start for convenience; T0 is authoritative |

### D. Rheometer — scope *environment*
Our only link to the rheometer is a **TTL pulse that advances the RheoCompass
program**. We have no access to its operation, so we record only what we know:

| PV | Type | Notes |
|---|---|---|
| `RheoPulseCount` | longout | pulses sent by this plan so far |
| `RheoLastPulseTime` | ao, epoch s | time of the last pulse: the key for matching frames to rheometer data afterwards |
| `RheoPhase` | stringout | the plan's own label (`pre` / `post` / …) as in `rheometer_template.py` |

No shear rate, strain or program name: we can't know them reliably.
`rheometer_template.py` and `SKILL.md` must say this explicitly, so the
plan-writing agent doesn't invent rheometer parameters.

### E. Radiation exposure — scope *environment* (new)
Two separate things, because both can be true at once:

**E1. X-ray self-exposure: tracked for every non-blank sample, always.**
| PV | Type | Notes |
|---|---|---|
| `XrayExposureTime` | ao, s | cumulative time the USAXS shutter has been open on this sample **before** this scan started. The scan's own exposure is in its file. Accounting method in §7.6. |

This is what the X-ray exposure experiments measured: the experiment's own beam
as the dose. Recording it for every sample also gives radiation-damage history
for free.

**E2. Deliberate exposure: UV, visible, laser, other.** Independent of
`EnvType`: a sample can be heated and UV-exposed at once.

| PV | Type | Notes |
|---|---|---|
| `ExposureType` | mbbo | None, UV, Visible, Laser, Other (X-ray is E1, not here) |
| `ExposureSource` | stringout | free text, e.g. "365 nm LED", "405 nm laser" |
| `ExposureWavelength` | ao, nm | NaN if not applicable |
| `ExposureIntensity` | ao | units in `ExposureIntensityUnits` (e.g. mW/cm2); NaN if unknown |
| `ExposureIntensityUnits` | stringout | |
| `ExposureOn` | bo | whether the source was on at scan start (read from the control signal, not assumed) |
| `ExposureStartTime` | ao, epoch s | first switch-on for this sample |
| `ExposureTime` | ao, s | **cumulative** time on, at scan start: the "time at exposure" measured in the UV/X-ray experiments |
| `ExposureDose` | ao | only if intensity is known (= intensity × time); NaN otherwise. Units in `ExposureDoseUnits` |

### F. Generic slots — for environments not yet known
`UserKey1..4` (stringout), `UserValue1..4` (ao), `UserUnits1..4` (stringout).
A new environment can be recorded immediately, and gets real PVs once it
proves to be recurring. Used by `external_device_template.py`.

### G. Bookkeeping
| PV | Notes |
|---|---|
| `MetaState` | mbbo: Unset / Set |
| `MetaOwner` | who set it: plan name, `manual`, `command file` |
| `MetaSetTime` | epoch s |
| `BoundTitle` | the base sample title the metadata belongs to (§6) |

**Long strings:** EPICS `stringout` holds 39 characters. `ProcedureName` and
`Description` need `lso` or char-waveform records. **Check on the beamline
(Step 1):** whether ADCore on the Pilatus and Eiger IOCs reads them through an
`EPICS_PV` NDAttribute. Do not assume it does. `saveFlyData.py` already
handles `as_string=True` (line 150). If AD can't, AD files get a ≤39-char
truncation and the full text goes to the fly-scan and Bluesky files only.

## 5. IOC work (usxSample)

1. Inventory the existing records (`dbl`, `caget` all `usxSample:*`). Does
   `Density` exist? What record types are used for strings?
2. Put the IOC database under version control (ask Jan where: next to
   `ADconfigs/` as `IOCconfigs/usxSample/`, or the IOC's own repo).
3. Add the records in §4. Give `ao` records `PREC`/`EGU` per the schema, and
   **initial value NaN** (strings `""`, mbbo 0 = None/Unset). No autosave.
4. Test NaN through Channel Access: `caput usxSample:Temperature nan` must
   read back NaN in pyepics, in an AD frame and in the fly-scan file.
5. Optional, later: a caQtDM screen showing all fields plus
   `MetaState`/`BoundTitle`.

## 6. Unsetting on sample change — the core of the design

### 6.1 Rules
| Situation | What happens |
|---|---|
| **Blank scan**: title contains `blank`, any case (Matilda's rule; one shared constant) | Before collecting, the data plan **clears everything** (sample + environment) and records MetaState = Unset. A blank carries no environment and no sample properties. |
| **Different sample**: title doesn't start with `BoundTitle` | Clear everything, log a warning, write one Obsidian line ("sample metadata for 'A' cleared: scan 'B' is a different sample"). |
| **Same sample, in situ**: title starts with `BoundTitle` (e.g. `PS_film_200C_22min` under `PS_film`) | Sample properties are kept. The plan rewrites environment fields for this scan. |
| Template plan ends: normally, aborted or stopped | `finalize_wrapper` clears everything. It only writes PVs and moves nothing, so it is consistent with the suspension rules in `CLAUDE.md`. |
| `newUser()` | Clear everything. |
| Command file ends (`after_command_list`) | Clear everything. `before_command_list` does **not** clear: the title check covers stale values, and metadata typed in caQtDM just before starting a file is preserved. |

The user-provided sample name is the whole check (agreed). The data plans run
it in the outermost plan only (`USAXSscan` → `Flyscan` checks once); it is
idempotent anyway.

The data plans do **not** clear environment fields after each scan. Clearing
just after a scan could race the fly-scan file write, and the next scan
rewrites or clears them anyway.

### 6.2 API (`plans/sample_metadata.py`)
* `set_sample_metadata(title, **sample_fields)`: **replaces** all
  sample-scope fields (unnamed → NaN/""), binds `BoundTitle = title`, sets
  owner/time/state. Environment untouched.
* `update_environment(**env_fields)`: **replaces** all environment-scope
  fields (unnamed → NaN/""), so a stale `ProcedureStep` from the previous
  segment can't leak. Sample fields untouched. This is the in-situ operation.
* `clear_sample_metadata()`: everything to NaN/"", MetaState = Unset.
  `resetAll()` becomes an alias for it, so old scripts keep working but stop
  writing 25 °C.
* `check_sample_binding(title)`: the blank/different-sample rule, called by
  the five data plans.
* `sample_metadata_snapshot()`: read all fields via `bps.rd`, return a dict
  for the start document.

### 6.3 Blanks inside a template loop
A loop that measures sample, blank, sample: the blank clears the PVs. The
template's `SampleState` (§7.2) keeps the sample's properties in Python and
rewrites the full set (sample + environment) in `prepare_scan` before the next
sample scan. Nothing is lost, and the blank files stay clean.

### 6.4 Keeping user-supplied sample data in situ
At plan start, `SampleState` **adopts** sample properties already in the IOC if
`BoundTitle` equals the plan's base title (e.g. the operator typed the
concentration in caQtDM), then overlays any properties passed to the plan
(plan arguments win). If `BoundTitle` is a different sample, it starts from
the plan arguments only. During the series only environment fields change.

## 7. Bluesky integration

### 7.1 Code
* `utils/sample_metadata_schema.py`: the field table. No EPICS, no numpy,
  importable in tests. Also holds the blank regex.
* `devices/sample_data.py`: new components, kept explicit (readable). The test
  checks them against the schema.
* `plans/sample_metadata.py`: the §6.2 API plus `SampleState`. Gets
  `sample_data` from `oregistry`. **No import from `usaxs.startup`.**
* The five data plans (`USAXSscan`, `Flyscan`, `USAXSscanStep`, `saxsExp`,
  `waxsExp`): call `check_sample_binding(title)` before any detector is
  armed, and add `md["sample_metadata"] = snapshot` to the start document
  (searchable in tiled).
* `NXWriterUascan` / base `write_entry`: link the `sample_data_*` baseline
  streams into `/entry/sample/...` using the paths in §8.
* `utils/obsidian_plan_log.py`: when metadata is set, add one compact line to
  the per-scan entry (`Linkam hold #2, series S1 #14, T=199.8 °C, UV 1520 s`).
* `startup.py`: add `set_sample_metadata`, `update_environment` and
  `clear_sample_metadata` to the public plan list. Queueserver: regenerate
  `existing_plans_and_devices.yaml`, check permissions. Simple-typed
  signatures, so queueserver validation accepts them.

### 7.2 `SampleState`: the helper every template uses
Replaces the ad-hoc `getSampleName()`/`setSampleName()` closures:

```python
state = yield from SampleState.start(
    base_title=scan_title, env="Linkam", temperature_source="linkam_tc1",
    procedure_name=f"Linkam: {rate_heat} C/min to {temp_target} C, hold ...",
    sample_fields=sample_info,          # optional dict from the plan args
)
...
title = yield from state.prepare_scan(
    step="hold", step_index=2,
    temperature=linkam_tc1.temperature.position, setpoint=temp_target,
    ramp_rate=0,
)
yield from saxsExp(pos_X, pos_Y, thickness, title, md=md)
```

* `prepare_scan` writes sample + environment PVs and returns the title in
  **exactly** today's encoding (`{base}_{T:.0f}C_{min:.0f}min`). A test pins
  the format.
* Series bookkeeping (`SeriesT0`, index, elapsed time) and exposure bookkeeping
  (cumulative on-time) live in `SampleState`, so templates don't each
  reimplement them.
* Debug mode: prints what it would write and writes nothing.
* Wrap the template body in `bpp.finalize_wrapper(..., clear_sample_metadata())`.

### 7.3 Plan templates (`src/usaxs/plan_templates/`) — required for the agent
The plan-writing agent copies these templates, so **this is how metadata
reaches future user plans**. Every template must show the full pattern.

* `README.md`: add mandatory structure item 7: *`SampleState.start` at plan
  start, `prepare_scan` before every scan, `clear_sample_metadata` in
  `finalize_wrapper`; blanks need nothing extra.*
* `minimal_plan_template.py`: `set_sample_metadata` + clear only (EnvType
  Ambient).
* `sample_list_template.py`: optional per-sample metadata dict as an extra
  SampleList entry element. `SampleState` per sample.
* `finite_loop_template.py`: series fields in all four variants.
* `linkam_template.py`, `ptc10_template.py`: env, generated `ProcedureName`,
  step/index, setpoint, ramp, measured T.
* `rheometer_template.py`: pulse count and pulse time, updated where the TTL is
  sent. Docstring states that **the pulse is our only interaction with the
  rheometer**.
* `external_device_template.py`: the UserKey/UserValue slots.
* **New `exposure_template.py`** (§7.4).
* `SKILL.md`: the API, the scopes, the blank rule, the rheometer limitation,
  and the exposure template.

### 7.4 New template: `exposure_template.py`
Measures scattering against **time at exposure**. Three variants:

1. **UV continuous**: the UV source is switched on at t=0 through its **EPICS
   TTL signal**, and scans repeat until a total exposure time is reached.
   `ExposureTime` = now − start at each scan.
2. **UV stepwise dose**: TTL on for N s, off, measure, repeat.
   `ExposureTime` = sum of on-intervals; the source is off during measurement.
3. **X-ray self-exposure**: no extra source. Repeated scans on one spot, with
   `XrayExposureTime` (§7.6) as the exposure variable. Effectively a
   `finite_loop` variant whose docstring explains it is a radiation-damage /
   X-ray-dose series. The title keeps the usual `_{min}min` suffix (D10).

The UV source is an `EpicsSignal` on/off (TTL), switched with
`bps.mv(uv_ttl, 1/0)` and read back for `ExposureOn`. Ask Jan for the TTL PV at
Step 6. If it is a Galil output like the rheometer's (`usxRIO:GalilAo1_SP`),
follow the same pattern; if the source is used routinely, declare it in
`devices.yml`. **Switch the TTL off in the template's `finalize_wrapper`**,
so an abort can't leave the UV on. For time-based ordering, an abort must leave
the source off before anything else is cleared.

### 7.6 X-ray self-exposure accounting
* **Method:** the data plans already open and close `usaxs_shutter` (the
  12idc Uniblitz) around their counting. Next to each existing open/close call,
  they report the open interval to a module-level accumulator in
  `plans/sample_metadata.py`. This measures *actual* shutter-open time,
  including transmission measurements, autoranging and fly-scan taxi with the
  shutter open, not nominal count times.
  `usaxs_shutter` is an `ApsPssShutter` with open/close PVs only, so its state
  can't be monitored. Step 1 checks whether the Uniblitz IOC has a readable
  state PV; if it does, a CA monitor on it is more complete and becomes the
  preferred method.
* **Step 1 must also check** every place `usaxs_shutter` is opened (data plans,
  tunes, `a_shutter_autoopen` / `12ida2:AShtr:Enable`). Tunes count only if the
  sample is in the beam during them; settle this with Jan.
* **Scope:** the accumulator is keyed to the bound sample (`BoundTitle`).
  * Blanks don't add.
  * A template's `SampleState` owns the counter for its sample, so a blank in
    the loop doesn't reset it.
  * For manual and command-file use, the counter resets when the binding moves
    to a different sample, and on `newUser()`.
  * Re-measuring the same title later continues the count: same specimen,
    more dose. Pass `reset_xray_exposure=True` to `set_sample_metadata` for a
    fresh spot.
* **Written** to `XrayExposureTime` in `check_sample_binding` / `prepare_scan`
  at the start of each scan.

### 7.5 Command files (later, low priority)
New actions:
```
SampleMetadata  PS_film  Concentration=0.05  Description="PS 50k film"
saxsExp  10 20 1.0  PS_film
ClearSampleMetadata
```

## 8. File templates (on the beamline computer — ask for paths)

**AD (SAXS and WAXS):** add every new PV to both `attributes.xml` (EPICS_PV
entries before PARAM/FUNCTION). Because of `ndattr_default`, they appear under
`/entry/Metadata` automatically. Add explicit placement to `layout.xml` /
`layout_waxs.xml`:

```
/entry/sample                (NXsample)       existing fields + density
/entry/sample/environment    (NXenvironment)  type, procedure_name, step, step_index,
                                              temperature_setpoint, ramp_rate,
                                              temperature_source
/entry/sample/time_series    (NXcollection)   name, index, t0, elapsed_time
/entry/sample/rheometer      (NXcollection)   pulse_count, last_pulse_time, phase
/entry/sample/exposure       (NXcollection)   xray_exposure_time,
                                              type, source, wavelength, intensity(+units),
                                              on, start_time, time, dose(+units)
/entry/sample/user_metadata  (NXcollection)   key/value/units slots
/entry/sample/metadata_state (NXnote)         state, owner, set_time, bound_title
```
Re-run `copy_attributes_to_template.py` for WAXS. Bump `config_version` to 2.1.

**Fly scan:** the same groups in `saveFlyData.xml`, with `string="true"` on
every string PV (fix the existing two). Validate with `xmllint` against the
XSD.

**Step scan:** the same paths, via `NXWriterUascan` (§7.1).

Identical paths in all four file types mean one reader in Matilda. Keep the
versions in `ADconfigs/` in this repo in sync with what is deployed.

## 9. Downstream (other repos — list only, not on this branch)
* **Matilda:** copy `/entry/sample/**` into the reduced NXcanSAS output; treat
  NaN as absent.
* **pyIrena:** show sample/environment/exposure in the data browser; sort
  series by `t0 + elapsed` (or exposure time) instead of parsing titles.
* **Igor Irena/Nika:** read the same paths on import (low priority).

## 10. Tests (offline, no EPICS — like `tests/test_obsidian_plan_log.py`)
* **Schema consistency:** every schema field is in the device, both
  `attributes.xml`, both layouts and `saveFlyData.xml`, at the schema's path.
  No orphan `usxSample:` PVs in the XML, and no duplicate attribute names.
  `xml.etree` only, no new dependency.
* **Lifecycle** (ophyd `Signal`s in place of PVs):
  * `set` replaces sample fields and leaves environment fields alone;
    `update_environment` does the reverse;
  * `clear` gives NaN/"" and never touches thickness;
  * a blank title clears, a different title clears, a same-base title keeps;
  * `finalize_wrapper` clears on a simulated abort;
  * a template blank in a loop is followed by a full rewrite;
  * `SampleState` adoption rule (§6.4);
  * `prepare_scan` titles match today's format byte for byte;
  * cumulative exposure time over on/off intervals;
  * X-ray accumulator: blanks don't add, a blank inside a template doesn't
    reset it, a binding change does, `reset_xray_exposure=True` does;
  * UV TTL is off after a simulated abort.

## 11. Decisions

### Settled (2026-11-10)
| # | Decision |
|---|---|
| D1 | Blanks carry no environment and no sample metadata. The user sample name is sufficient for the sample-change check. In situ: environment is updated each scan, sample data is kept. |
| D2 | Templates in `plan_templates/` must implement the full pattern, because the agent builds future plans from them. |
| D3 | Rheometer: only the TTL pulse is known. Record pulse count and time, nothing else; the agent must be told. |
| D4 | IOC and AD/fly-scan templates are modified on the beamline computer. Ask for paths there. |
| D5 | NaN is acceptable for every unset value **except thickness**, which defaults to 1. |
| D6 | No autosave for usxSample. |
| D7 | Support the template environments now (Ambient, Linkam, PTC10, Rheometer, time series) plus **radiation exposure**, with a new template. Others via generic slots until they recur. |
| D8 | `before_command_list` does not clear; `after_command_list` does. |
| D9 | `ProcedureName` is generated by templates from their arguments, as free text. No procedure codes, no `ProcedureID` field: there is no heater convention beyond the title suffixes. |
| D10 | The existing title encodings (`_200C_22min`, `_sx.._sy.._pre1_..min`, …) are **critical** and stay exactly as they are; Matilda and pyIrena parse them. Metadata is additive. |
| D11 | UV is switched by an EPICS TTL signal: the template drives it and reads it back. |
| D12 | X-ray exposure = the experiment's own beam. Tracked as cumulative `usaxs_shutter` open time per sample, for every non-blank sample (§7.6). |

### To ask on the beamline computer (none block starting)
* The usxSample IOC paths and where its database goes in version control (Step 1).
* The AD and fly-scan config paths (Step 7).
* Whether the Uniblitz has a readable state PV, and whether the sample sees
  beam during tunes (Step 1, §7.6).
* The UV TTL PV name, and whether UV intensity is normally known (Step 6).

## 12. Step-by-step implementation (beamline computer)

Each step ends with a commit on `December2026`. Stop and report at each ✋.

**Step 1 — Survey (read-only)** ✋
Ask Jan for the paths in §0. Inventory `usxSample:*` records. Check
`Density`, string record types and ADCore version. Test NaN round-trip and
long-string NDAttribute support on a scratch PV if possible. Find every
`usaxs_shutter` open/close site and any readable Uniblitz state PV (§7.6).
Write the findings into §0 of this file.

**Step 2 — Schema**
`utils/sample_metadata_schema.py` from §4, adjusted to Step 1's findings.
Write the schema-consistency test, expected to fail against the XMLs until
Step 7.

**Step 3 — IOC** ✋
Add the records (§5), version-control the database, restart the IOC, and check
every PV with `caget`, NaN included. *This is the only step that changes a
shared IOC. Agree the restart time with Jan.*

**Step 4 — Device and API**
Extend `SampleDataDevice`; write `plans/sample_metadata.py` (§6.2) and
`SampleState` (§7.2); the lifecycle tests. Try it at the IPython prompt against
the real PVs: set / update / clear / blank / different title.

**Step 5 — Data-plan integration** ✋
Binding check and start-document snapshot in the five data plans; X-ray
exposure accounting at the shutter open/close sites (§7.6); Obsidian line; uascan NeXus links; `startup.py` public list; regenerate the queueserver
yaml. Run one each of `USAXSscan`, `saxsExp` and `waxsExp` on a test sample,
with metadata set and with a blank, and check the start documents and Obsidian
entries.

**Step 6 — Templates**
Update all seven templates, add `exposure_template.py` (ask for the UV TTL
PV), update the README and `SKILL.md`. Run each template in its debug mode. Then generate one
plan through the agent from a template, as an end-to-end check that it sets
metadata.

**Step 7 — AD and fly-scan XML** ✋
Edit `attributes.xml` ×2, `layout.xml` ×2 and `saveFlyData.xml` (§8); bump to
version 2.1; `xmllint`; schema test now passes. Deploy to the live paths,
restart the AD IOCs, and copy back into `ADconfigs/` so the repo matches.

**Step 8 — Beamline verification** ✋
* Set metadata, then one fly, step, SAXS and WAXS scan: `h5dump` shows
  identical values at identical paths.
* Blank: everything NaN/"" (thickness 1).
* Set for A, scan B: cleared, plus an Obsidian warning.
* In situ: Linkam template, few short segments; environment changes, sample
  fields stay.
* Abort a template mid-loop: `MetaState = Unset`.

**Step 9 — Command-file actions** (optional, §7.5).

**Step 10 — Merge** to `main` once Step 8 passes. Then the Matilda/pyIrena
downstream work (§9), in their own repos.
