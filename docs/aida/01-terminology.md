# Terminology — USAXS/SAXS/WAXS and Bluesky

A glossary for an agent that knows general AI/automation concepts but not
this beamline or the Bluesky ecosystem specifically.

## The techniques

| Term | What it measures | Notes |
|---|---|---|
| **USAXS** | Ultra-Small-Angle X-ray Scattering | Very low Q (long real-space length scales, ~1 nm to several µm). The Bonse-Hart camera geometry used here trades angular range for extreme angular resolution. |
| **SAXS** | Small-Angle X-ray Scattering | Higher Q than USAXS, shorter length scales (~1–100 nm). Uses an area detector (`saxs_det`, a Pilatus). |
| **WAXS** | Wide-Angle X-ray Scattering | Highest Q, atomic/molecular length scales (crystallography-adjacent). Uses an area detector (`waxs_det`, an Eiger). |
| **Radiography** | Direct transmission imaging | Not scattering — a plain absorption image through the sample, used for alignment and sample inspection. |
| **Imaging** | Optical camera view | The Blackfly cameras (`blackfly_det`, `blackfly_optical`) give a visible-light view of the sample position, not X-ray data. |

A single "USAXS/SAXS/WAXS set" on one sample position typically runs all
three techniques back-to-back (see `USAXSscan` → `saxsExp` → `waxsExp` in
[02-plans-catalog.md](02-plans-catalog.md)) so the same spot is characterized
across the full Q-range.

**Q** (units Å⁻¹) is the scattering vector magnitude — the x-axis of a
scattering curve. Larger Q = smaller real-space features. Sample positions
and thickness are always in **mm**; temperature is in **°C**.

## Instrument stages (motors grouped into ophyd devices)

| Device | Physical role | Key axes |
|---|---|---|
| `s_stage` | Sample stage | `x`, `y` — translates the sample into/out of the beam |
| `m_stage` | Collimating (M) crystal stage | `r` (MR rotation), `x`/`y` translation, `r2p` piezo roll/pitch (M2RP) fine-tuning |
| `a_stage` | Analyzer (A) crystal stage | `r` (AR rotation), `x`/`y` (AY) translation, `r2p` piezo roll/pitch (A2RP) fine-tuning |
| `d_stage` | USAXS detector stage | `x` (DX), `y` (DY) |
| `saxs_stage` | SAXS/WAXS detector stage | `x`, `y`, `z` |
| `guard_slit` | Guard slit upstream of the sample | 4 blades (`inb`/`outb`/`top`/`bot`) + `x`/`y` translation |
| `gslit_stage` | Guard slit translation-only summary device | `x`, `y` (a slimmer alias onto the same physical axes as `guard_slit.x`/`.y`) |
| `usaxs_slit` | USAXS-specific sample slit | same 4-blade + translation shape as `guard_slit` |

"Tuning" a stage (see `tune_ar`, `tune_mr`, `tune_dx`, `tune_dy`,
`tune_a2rp`) means running a small scan across that axis to find and set the
peak-intensity position — it's an alignment step, not data collection.
`find_ar`/`find_a2rp` do a wide search first for when the peak has drifted
out of the range a plain `tune_*` would catch.

## Modes

"Mode" plans (`mode_USAXS`, `mode_SAXS`, `mode_WAXS`, `mode_Radiography`,
`mode_DirectBeam`, `mode_OpenBeamPath`) move the detector/optics stages into
the physical configuration for that technique — they don't collect data
themselves. A data-collection plan (`USAXSscan`, `saxsExp`, `waxsExp`)
switches mode internally as needed; you generally don't need to call a mode
plan before those. Call one directly only when positioning the instrument
without collecting data (e.g. leaving it parked in a known mode).

## Scan mechanics

- **Fly scan vs. step scan**: a fly scan (`Flyscan`) moves the AR stage
  continuously while streaming detector counts — fast, the default. A step
  scan (`USAXSscanStep`) moves to discrete positions and counts at each —
  slower, used as a fallback. `USAXSscan` is the plan that picks between
  them automatically based on the `terms.FlyScan.use_flyscan` setting; call
  `Flyscan`/`USAXSscanStep` directly only to force one.
- **Autorange amplifiers**: the current amplifiers reading the diode/ion
  chamber signals (`I0`, `I00`, `trd`, `upd` — see
  [03-devices-and-pvs.md](03-devices-and-pvs.md)) automatically pick a gain
  range so the signal stays in a good part of the amplifier's dynamic range.
  This happens inside data-collection plans; it isn't something you drive
  directly.
- **Transmission**: the fraction of incident beam that passes through the
  sample, used to normalize scattering intensity. Filters
  (`insertTransmissionFilters` etc., console-only, not queue-server-exposed)
  attenuate the direct beam so the transmission measurement itself doesn't
  saturate the detector.

## Operational / hardware terms

- **PSS shutter (`FE_shutter`)**: the APS Personnel Safety System
  front-end shutter — a hard interlock, not something you open/close
  casually.
- **Mono shutter (`mono_shutter`)**: a second PSS-controlled shutter
  downstream of the monochromator.
- **USAXS/uniblitz shutter (`usaxs_shutter`)**: the fast local shutter this
  instrument uses to gate exposures during a scan — the one plans open and
  close routinely, unlike the two PSS shutters above.
- **"In operation" vs. "simulation"**: at startup the instrument checks a
  live PV (`usxLAX:blCalc:userCalc2.VAL`). If it equals `1`, real PSS
  shutters are loaded (`shutters_op.yml`); otherwise simulated shutter
  devices are loaded (`shutters_sim.yml`) with the same device names. This
  is decided once per session (console or queue-server restart), not
  per-plan.
- **Suspenders**: `suspend_FE_shutter` and `suspend_BeamInHutch` are
  Bluesky suspenders wired onto `USAXSscan`, `saxsExp`, and `waxsExp` (see
  `startup.py`). If the front-end shutter closes or the beam leaves the
  hutch mid-scan, the RunEngine automatically pauses those three plans and
  resumes them when conditions are OK again — you don't need to detect or
  react to a beam drop yourself during one of those plans. Other plans
  (tuning, mode changes) are **not** suspender-protected.
- **Baseline stream**: devices labeled `baseline` in the config YAML are
  recorded once at the start and end of every run automatically, for
  provenance — not something a plan call needs to request.

## Bluesky / ophyd / queue-server core vocabulary

| Term | Meaning here |
|---|---|
| **RunEngine (`RE`)** | The Bluesky object that actually executes a plan against hardware and emits data documents. AIda never touches `RE` directly — the queue server does that. |
| **Plan** | A Python generator function describing a sequence of hardware moves and reads (e.g. `USAXSscan`). Submitting a plan to the queue server is how AIda causes anything to happen. |
| **Plan stub** | A small building-block plan (e.g. "move", "sleep", "trigger") that larger plans are built from. AIda generally submits whole plans, not stubs. |
| **Device** | An ophyd object representing one piece of hardware (a motor, detector, or a composite of several PVs), addressed by name (e.g. `s_stage`, `fx4`). |
| **Signal** | The smallest ophyd unit — one readable/writable value, usually backed by one EPICS PV. A device is a tree of signals and sub-devices. |
| **PV (Process Variable)** | An EPICS channel — the actual named value on the control-system network (e.g. `usxLAX:m58:c0:m1`). Every signal ultimately maps to one. |
| **`kind`** | Metadata on a signal/device controlling whether it's included in default reads: `hinted` (shown in live plots), `normal` (read, not plotted), `config` (read once per run, not per point), `omitted` (not read by default). |
| **Queue server (RE Manager)** | The service that owns the RunEngine and accepts plan submissions over its API (what the MCP tools AIda uses talk to). It runs `usaxs.startup` once per environment start. |
| **Environment** | A queue-server session with the RunEngine and all devices/plans loaded — must be "opened" before plans can run and "closed" when done. |
| **Queue / history** | The list of pending plan submissions, and the record of what has already run, tracked by the queue server. |

<!-- PLACEHOLDER: beamline-specific shorthand and verbal jargon that staff
     use but that isn't obvious from code or PV names — e.g. nicknames for
     specific samples, sample environments, or recurring experiment types.
     Fill this in with terms AIda is likely to hear from users. -->
