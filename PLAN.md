# PLAN — FX4 counting-chain conversion

Branch: `fx4-conversion` (from `main` @ 89adbc4)
Status: **planning / questions open** — no code written yet.
Target: usable at the beamline for the coming Sunday start-up, with a clean
rollback to `main` if the new chain misbehaves.

Companion references in `docs/`:
* `FX4_config_cheatsheet.md` — the two FX4 operating configs (§ = its sections)
* `FX4_PSO_flyscan_setup.md` — full explanation, PV table, hardware facts

---

## 1. What we are replacing

### 1.1 Present step-scan chain

```
diode/ion chamber → Femto amplifier → V/F converter → scaler0 (usxLAX:vsc:c0) → counts
                         ▲
                         └── autorange sequence program (usxLAX:pdNN:seqNN:)
```

| Detector | scaler0 chan | ophyd name | Femto            | Autorange seq      |
|----------|--------------|------------|------------------|--------------------|
| I0       | chan02       | `I0`       | usxRIO:fem02     | usxLAX:pd02:seq01  |
| I00      | chan03       | `I00`      | usxRIO:fem03     | usxLAX:pd03:seq01  |
| UPD      | chan04       | `UPD`      | usxLAX:fem09:seq02 (DDPCA300) | usxLAX:pd01:seq02 |
| TRD      | chan05       | `TRD`      | usxRIO:fem05     | usxLAX:pd05:seq01  |
| I000     | chan06       | `I000`     | usxRIO:fem04     | none               |

Wiring: `src/usaxs/utils/scalers_setup.py` registers the channel signals into
`oregistry` under the bare names `I0`, `UPD`, … and the channel objects as
`UPD_SIGNAL`, … . `DetectorAmplifierAutorangeDevice`
(`src/usaxs/devices/amplifiers.py:311`) bundles *(scaler, ScalerChannel, Femto,
AmplifierAutoDevice)* into `upd_controls` / `I0_controls` / `trd_controls` /
`I00_controls`.

There is a **second** scaler, `scaler1` (`usxLAX:vsc:c1`), hardware-gated by the
area-detector exposure. It supplies `terms.SAXS_WAXS.I0_gated`
(`plans_user_facing.py:325`, `:577`). It is *not* in the list of things Jan
named for conversion — see Q7.

### 1.2 Present fly-scan chain

```
PSO strobes ─┬─► Struck 3820 MCS (usxLAX:3820:)  mca1=50 MHz clock, mca2=I0, mca3=UPD
             └─► amplifier autorange seq → gain-change arrays usxLAX:USAXSfly:<det>:{mcsChan,ampGain,ampReqGain}
```

Harvested by `usaxs_flyscan_support/saveFlyData.py`, driven by an XML PV map.
**The live XML is not in this repo** — it is
`/share1/AreaDetectorConfig/FlyScan_config/saveFlyData.xml`; the in-repo
`saveFlyData_EXAMPLE.xml` is stale. Data reduction reads
`entry/flyScan/{mca1,mca2,mca3}` plus `AR_*` positioner arrays.

Dwell time per point comes from `mca1` (50 MHz clock counts), needed because
`mca2`/`mca3` are accumulated **counts**. The FX4 reports an **average current**
per interval, so dwell drops out of the normalisation entirely — see §3.3.

### 1.3 Target

| Signal | Device | Channel | Range control (Sunday) |
|--------|--------|---------|------------------------|
| UPD    | `fx4`  (`usxFX4:FX4:`)  | Current1 | autorange seq `usxFX4:FX4:seq01:` |
| TRD    | `fx4`  | Current4 | autorange seq `usxFX4:FX4:seq01:` |
| I0     | `fx42` (`usxFX42:FX4:`) | Current1 | **manual fixed range** (autorange TBD) |
| I00    | `fx42` | Current2 | manual fixed range; nothing connected yet |
| I000   | —      | —        | drop from scaler0 (see §1.5) |

The channel→detector mapping must be **data, not code**: put it in `iconfig.yml`
(`FX4_CHANNELS: {UPD: [fx4, 1], TRD: [fx4, 4], I0: [fx42, 1], I00: [fx42, 2]}`)
and have the naming helper (§3.4) read it. Jan expects this to move.

`fx4` and `fx42` are **already declared** in `src/usaxs/configs/devices.yml:22-27`
and the ophyd class `QuadFX4` already exists in
`src/usaxs/devices/fx4_quadem.py`. Nothing else in the codebase references them.

### 1.4 Four file formats carry counting-chain data, not one

This is bigger than the fly-scan HDF5. Every one of these needs an FX4 version
**and a marker the reduction software can branch on**:

| # | File | Written by | Config in repo | Carries today |
|---|------|-----------|----------------|---------------|
| 1 | fly-scan HDF5 | `saveFlyData.py` | `ADconfigs/Flyscan_config/saveFlyData.xml` (v1.2) | `mca1/2/3`, Femto gain-change arrays |
| 2 | SAXS HDF5 | Pilatus AD NeXus plugin | `ADconfigs/SAXS_config/{attributes,layout}.xml` | `I0_cts`, `I0_cts_gated`, `Exp_time_gated`, `I00_cts`, `I000_cts`, `scaler_freq`, `I0_gain`, `I00_gain` |
| 3 | WAXS HDF5 | Eiger AD NeXus plugin | `ADconfigs/WAXS_config/{attributes,layout_waxs}.xml` | same set |
| 4 | uascan HDF5 | `NXWriterUascan` | `callbacks/nxwriter_usaxs.py` (code, not XML) | whatever is in the primary stream |

(2) and (3) are `NDAttributes`: `attributes.xml` lists the PVs, and
`layout.xml` has `<group name="Metadata" ndattr_default="true">`, so **any
attribute added to `attributes.xml` lands in `/entry/Metadata` automatically** —
no layout edit needed for plain additions. Layout edits are needed only for
explicit placement, of which there is one that matters:

```xml
<hardlink name="integral" target="/entry/Metadata/I0_cts_gated"/>   <!-- /entry/control -->
```

That is the NXcanSAS monitor normalisation for every SAXS/WAXS frame. If
`I0_gated` moves off `scaler1`, this target changes — see Q7.

`layout.xml` supports `<dataset ... source="constant" type="string"/>`, so the
version marker can be a **constant**, no PV required:

```xml
<dataset name="counting_chain" value="FX4" source="constant" type="string"/>
<dataset name="config_version" value="2.0" source="constant" type="string"/>
```

Recommendation: use the **same two field names in all four formats** so the
reduction code has exactly one thing to test, regardless of which file it opened.

Because the FX4 value is gain-independent (§2.1), reduction needs only
`I = diode / I0` from these files — the marker exists to signal the **unit
change** (counts → pA) and the absence of a gain term, not to select a different
correction path.

### 1.5 I000 — there are two of them, and one *is* in use

Worth being precise, because the answer to Q3 was "I don't think I000 is used":

* `oregistry["I000"]` = `scaler0` chan06, plus `I000_femto_amplifier`
  (`usxRIO:fem04:seq01:`) and `I000_photocurrent_calc` (`usxLAX:USAXS:I000`).
  Loaded at `amplifiers_plan.py:61` and **referenced by nothing**. ✅ Safe to drop.
* `scaler2_I000_counts` / `scaler2_I000_cps` = **`usxLAX:vsc:c2`**, a *different*
  scaler (`devices.yml:71-74`). Its cps value is written into **every SAXS and
  WAXS NeXus file** as the `I000_cts` attribute
  (`ADconfigs/{SAXS,WAXS}_config/attributes.xml:97`). ⚠️ **In use — leave alone.**
  It is outside the scope of this conversion.


---

## 2. The two things that make this more than a find-and-replace

### 2.1 Counts → current — smaller than it looks

The scaler returns **integer counts**, the plans work in **counts/second**, and
the FX4 returns a **gain-independent current in pA**. The important consequence
is what *does not* change:

> **No gain bookkeeping anywhere.** The FX4 value is already gain-corrected, so
> transmission and data reduction are just `diode / I0`. No division by amplifier
> gain, no per-range gain table, no gain-change arrays. The range matters only in
> that it must not be topped out.

That deletes a large amount of planned work and several fields I had proposed for
the data files. Gains/ranges are still worth **recording as diagnostics** — to
confirm the autoranger is behaving and nothing railed — but nothing downstream
consumes them.

What *does* still have to be restated in pA:

| where | today | becomes |
|---|---|---|
| `devices/amplifiers.py:206-207` | `max_count_rate=950000`, `min_count_rate=500` | autoscale window in pA (or % of full scale) |
| `utils/constants.py:25` | `TR_MAX_ALLOWED_COUNTS = 980_000` | saturation check in pA |
| `general_terms.py:54-55,212-213` | `setpoint_up/down` = 6000 / 850000 and 4000 / 650000 | see the trap in §4.1 — probably **delete**, not convert |

And one thing to confirm early: that `Current{n}:MeanValue_RBV` really does come
out in **pA** rather than A (it is a `CurrentScale` setting per channel). A
factor of 10¹² is the kind of error that looks like a plausible intensity.
Added to the bench script (§7).

### 2.2 One gate became two boxes

`scaler0` gated I0, UPD, TRD and I00 from **one clock**. With UPD on `fx4` and
I0 on `fx42`, a step-scan point requires triggering **two independent
electrometers** whose integration windows are set in software and will not be
bit-identical. Normalising UPD/I0 across two slightly different windows adds
noise that the old chain did not have.

* **Fly scan**: solved for free — feed the PRL-414B (it is a **1:4** driver) to
  D1 of *both* FX4s, each with its own 50 Ω feed-through. Same gate, same bin
  edges, index `i` corresponds on both.
* **Step scan**: no hardware fix. Mitigation is to fire both `Acquire` writes
  without waiting, then wait on both (`bps.trigger(fx4, wait=False)`,
  `bps.trigger(fx42, wait=False)`, `bps.wait(...)`) so the skew is one CA
  round-trip (~ms) rather than a full exposure. Flagged as Q6.

---

### 2.3 One range per box, shared by all four channels

`Range` is a **device-level** PV, not per-channel — ophyd's `QuadEM` has a single
`em_range = Cpt(EpicsSignalWithRBV, "Range")`, which matches the hardware. So all
four channels on one FX4 digitise at the same range, and the `seq01:` autoranger
has a `channel` PV to select which one it watches.

This works because **UPD and TRD are never used at the same time**: UPD for
USAXS, TRD only for transmission. But it makes channel selection an explicit
responsibility of the Bluesky layer, at every switch point:

```
usxFX4:FX4:seq01:channel = 1   →  autorange on UPD   (tuning, uascan, fly scan)
usxFX4:FX4:seq01:channel = 4   →  autorange on TRD   (transmission only)
```

Three consequences that are easy to miss:

1. **Autoscale must set the channel first, and at most one channel per box may
   be autoranged per call.** Grouping several controls from the same box into one
   convergence loop is now meaningless — they share the range, so converging one
   de-converges the other.
2. **TRD is railed during a USAXS scan** (the range is tuned for UPD, which sees
   orders of magnitude less signal). It is currently recorded via `scaler0` in
   `uascan`'s primary stream and listed in `quiet_detectors`
   (`uascan_plan.py:186`). With the FX4 the fix is free: simply **do not read TRD
   during a uascan.** The whole `quiet_detectors` mechanism largely goes away,
   since FX4 channels are read explicitly rather than swept up by a scaler.
3. **`fx42` has the same latent conflict** — I0 (ch1) and I00 (ch2) will share a
   range once I00 is connected. Today I00 has nothing on it and I0 runs at a
   fixed range, so it does not bite on Sunday; but
   `autoscale_amplifiers([upd_controls, I0_controls, I00_controls])` appears at
   four call sites and will need the same serialisation when I00 goes live.
   (Or, as you note, a third FX4 — they are cheap.)

#### Where the switch points actually are

| call site | box grouping | action |
|---|---|---|
| `axis_tuning.py` ×7 — `[upd, I0]` | fx4:UPD + fx42:I0 | one channel per box ✅ set `channel=1` |
| `plans_usaxs.py:255` — `[upd, I0]` | fx4:UPD + fx42:I0 | ✅ `channel=1` |
| `plans_usaxs.py:507`, `tune_guard_slits.py:84,210,441` — `[upd, I0, I00]` | fx4:UPD + fx42:**I0+I00** | ⚠️ two on fx42 — latent (§2.3.3) |
| `sample_transmission.py:77,92,199`, `plans_user_facing.py:526` — `[I0, trd]` | fx42:I0 + fx4:**TRD** | ✅ one per box, but set `channel=4` |
| `command_list.py:172` — `measure_background([upd, I0, I00, trd])` | **two on each box** | ⚠️ see below |

`measure_background` is the one that genuinely breaks: it asks for all four at
once, and there is only **one** `bkg0..4`/`bkgErr0..4` table per sequence
program. Measuring UPD then TRD on `fx4` overwrites the same records. Options:
serialise and accept that `seq01:bkgN` holds only the last channel measured;
store darks on the Bluesky side instead; or — per Q16 — take a single dark and
stop treating this as a per-range table at all. Flagged as Q19.

## 3. Phase 0 — device layer (must land first, ~half a day)

Everything else depends on this.

### 3.1 Extend `QuadFX4` (`src/usaxs/devices/fx4_quadem.py`)

Verified against `ophyd 1.11.2`:

* `ophyd.QuadEM` already gives `averaging_time`, `acquire`, `acquire_mode`,
  `trigger_mode`, `values_per_read`, `sample_time`, `num_average`,
  `num_averaged`, `num_acquire`, `em_range` (`Range`), `ring_overflows`,
  `current_offsets`, `current_scales`.
* **Missing, must be added**:
  * `trigger_polarity` → `TriggerPolarity` (FX4-only, not in ophyd's QuadEM).
  * On each `current{1..4}` stats plugin: the **TS control** records.
    `StatsPlugin_V34` carries only the TS *data* arrays
    (`ts_mean_value`→`TSMeanValue`, `ts_total`→`TSTotal`,
    `ts_sigma`→`TSSigma`, `ts_timestamp`). It has **no** `TSControl`,
    `TSNumPoints`, `TSCurrentPoint`, `TSAcquireMode` — those live in
    `TimeSeriesPlugin_V34` under a *different* asyn port in newer ADCore.
    The cheatsheet shows them at `Current1:TS…`, i.e. the older in-stats-plugin
    layout. **Verify on the live IOC before coding** (§7, check B).
  * `blocking_callbacks` is already inherited — needed for `CallbacksBlock=Yes`.

* **`trigger()` must be made staging-independent.** `QuadEM` inherits
  `SingleTrigger`, whose `trigger()` **raises `RuntimeError` unless the device
  is staged** and whose completion callback is only subscribed in `stage()`.
  Every existing call site (`uascan_plan.py:316`, `no_run_trigger_and_wait`
  in transmission, `amplifiers_plan.py:252`, `sample_rotator_plans.py:122`)
  does a bare `bps.trigger(...)` on an unstaged `scaler0`, because `ScalerCH`
  allows it. Override `trigger()` in `QuadFX4` to subscribe to `acquire` at
  connect time and drop the staged check; also skip
  `generate_datum(self._image_name, …)` since `image = None`.
  *Alternative*: wrap each plan in `bps.stage`/`bps.unstage`. Rejected — it
  touches more code and changes suspender-replay behaviour.

### 3.2 Two config plans, one per FX4 mode

New module `src/usaxs/plans/fx4_setup.py`:

```
fx4_scaler_mode(det, count_time)   # CONFIG 1 (§cheatsheet)
    trigger_mode      = "Free run"    (0)
    acquire_mode      = "Single"      (2)
    values_per_read   = 100           # 1 kHz/box, 10 s max exposure (§3.3)
    current{1..4}.enable            = "Enable"
    current{1..4}.blocking_callbacks = "Yes"    ← without this, trigger returns
                                                  before MeanValue updates
    averaging_time    = quantize_count_time(count_time)

fx4_flyscan_mode(det, npts)        # CONFIG 2
    trigger_mode      = "Ext. bulb"   (3)
    trigger_polarity  = "Negative"    (1)
    acquire_mode      = "Continuous"  (0)
    values_per_read   = 10            # capped by PSO strobe width (§3.3)
    current{1..4}.enable            = "Enable"
    current{1..4}.blocking_callbacks = "No"
    current{1..4}.ts_num_points     = npts
    current{1..4}.ts_acquire_mode   = "Fixed length"
```

### 3.3 Exposure time and ValuesPerRead

**Step / scaler mode.** Exposure = `AveragingTime`, one PV, replacing
`scaler0.preset_time` one-for-one at every call site. One rule:

* **Quantise to mains cycles.** Make the window an integer multiple of 1/60 s
  (16.667 ms) or 60 Hz pickup does not average out and no amount of averaging
  helps (§12). Add
  `usaxs/utils/count_time.py: quantize_count_time(t, mains_hz=60) -> float`
  returning `max(1, round(t * 60)) / 60`, applied at **every** site that sets a
  count time. `uascan`'s dynamic time divides the base by 3 and multiplies by 2;
  `0.1/3` happens to land on exactly 2 cycles, but an arbitrary base will not,
  so the quantiser is not optional.

**Fly-scan / bulb mode.** You do **not** set the exposure — each PSO interval
defines its own window and `AveragingTime` is ignored.

#### ValuesPerRead — the real knob (Jan: prefer higher, network load)

Two hard relations:

```
max exposure (samples <= RING_SIZE=10000)  =  VPR / 10   seconds
streamed rate per box                      =  100 / VPR  kHz
```

**Key point that makes higher VPR cheap: VPR does not discard data.** The FX4
pre-averages `VPR` of its 100 kHz conversions *on the device*, so a 0.1 s
exposure integrates all 10 000 ADC conversions whether VPR is 10 or 100 — only
the *time resolution within* the exposure gets coarser. For step scans that is
irrelevant. So Jan's instinct is right and the two modes should use **different
VPR**, set by their respective config plans (§3.2):

| Mode | VPR | Rate/box | Max exposure | Bounded by |
|------|-----|----------|--------------|------------|
| idle / display | 100 | 1 kHz | — | nothing; keep the link quiet |
| **scaler (step, tune, transmission)** | **100** | 1 kHz | **10 s** | nothing — go higher if you want |
| **fly scan (bulb)** | **10 (known good)** | 10 kHz | n/a | **PSO strobe width — see below** |

With both boxes at VPR=100 the idle/step load is 2 kHz total. RING_SIZE stays at
10000 and no `FX4.cmd` change or IOC restart is needed. Still assert
`RingOverflows == 0` after every scan — a non-zero value means the means are
biased and the data are wrong.

**Fly-scan VPR is capped by the PSO strobe, not by the ring buffer.** In bulb
mode with Negative polarity the *delimiter* is the HIGH strobe, and the driver
must see both its edges in the streamed samples or two exposures fuse into one
(§8). Safe floor is 3-5 sample periods:

| VPR | SampleTime | min safe strobe | samples in a 0.05 s interval |
|-----|-----------|-----------------|------------------------------|
| 10  | 100 µs | 300-500 µs | 500 |
| 20  | 200 µs | 0.6-1 ms   | 250 |
| 50  | 500 µs | 1.5-2.5 ms | 100 |

VPR=10 is the value already proven on a 2000-pulse train. Raising it needs the
actual PSO strobe width (`usxAERO:pm1:` — see the bench script, §7). A merged
exposure looks exactly like a missed pulse, so this is worth measuring rather
than guessing.

#### Correction to an earlier assumption: dwell time is *not* needed for normalisation

With the Struck, `mca3` was accumulated **counts**, so you had to divide by
`mca1` (50 MHz clock) to get a rate. With the FX4, `TSMeanValue` is already an
**average current over the interval** — it is self-normalising. Since both boxes
share one PSO gate, `UPD_current[i] / I0_current[i]` is a valid ratio with **no
dwell-time term at all**. That is a genuine simplification for data reduction.

Per-point duration is still worth writing to file, for three secondary uses:
tuning-jitter diagnostics, uncertainty (σ_mean = TSSigma/√N), and integrated
charge. It is derived as:

```
N[i]  = TSTotal[i] / TSMeanValue[i]        # exact sample count (use the I0 channel)
dt[i] = N[i] * values_per_read * 10e-6     # seconds, quantised to one SampleTime
```

Because it is no longer on the normalisation path, its 1-part-in-100 quantisation
at higher VPR is acceptable — which removes one more objection to raising VPR.

### 3.4 Names: keep `UPD`, `I0`, `TRD`

`setup_scalers()` renames scaler channel signals to the bare names `UPD`, `I0`,
`TRD`, and those names propagate into BEC hints, the NeXus stream keys, and the
queue-monitor plot configuration
(`usaxs-qmonitor/usaxs_qmonitor/settings.py:55,62,69,76,83`).

**Recommendation: reuse the same names for the FX4 mean-value signals.** A new
`src/usaxs/utils/fx4_setup.py: name_fx4_channels()` (mirroring
`scalers_setup.py`) sets
`fx4.current1.mean_value.name = "UPD"`, registers it in `oregistry`, and puts it
in the `__main__` namespace. Everything downstream — plots, tables, GUI, NeXus
keys — keeps working untouched.

**The hazard**: the *units* under a stable name change from counts/s to amps,
silently. Mitigate by (a) always stamping `md["counting_chain"] = "FX4"` on
every run, and (b) writing a `units` attribute in the NeXus output. See Q8 —
the alternative (new names like `UPD_A`) is more honest but breaks the GUI,
the hints, and every reduction path at once.

### 3.5 Baseline & registry housekeeping

* Add `labels: [baseline]` to the `fx4`/`fx42` entries in `devices.yml` so the
  config PVs (range, VPR, trigger mode, offsets) land in the baseline stream —
  they are needed to reduce the data.
* Regenerate `src/usaxs/qserver/existing_plans_and_devices.yaml` after the
  device set changes, or the queueserver will not see the new plans.

---

## 4. Phase 1 — step scans

### 4.1 Autoranging and dark current — `usxFX4:FX4:seq01:`

The PV list is in hand. Mapped against `AmplifierAutoDevice`
(`devices/amplifiers.py:187`) it is a **close but not exact** match:

| `AmplifierAutoDevice` | suffix | in `seq01:`? |
|---|---|---|
| `reqrange`, `mode`, `selected`, `gainU`, `gainD` | same | ✅ |
| `status`, `updating` | `updating` | ✅ |
| `lurange`, `lucurrent` | same | ✅ |
| `ranges.gainN.background` | `bkg0..bkg4` | ✅ |
| `ranges.gainN.background_error` | `bkgErr0..bkgErr4` | ✅ |
| `gain` (from `CurrentAmplifierDevice`) | `gain` | ❌ **gone** |
| `ranges.gainN.gain` | `gain0..gain4` | ❌ **gone** |
| `counts_per_volt` | `vfc` | ❌ gone (no V/F converter — correct) |
| `lucounts`, `lurate` | — | ❌ gone (no counts — correct) |
| — | `channel` | ➕ new |
| — | `current` | ➕ new |
| — | `modeRdbk` | ➕ new |
| — | `speed`, `debug` | ➕ new |

`NUM_AUTORANGE_GAINS = 5` still holds (bkg0..bkg4). So:

**Dark current (Q16): start simple.** `bkg0..bkg4`/`bkgErr0..bkgErr4` exist, so
the full 5-range sweep still *works* — but since the value is gain-independent
(§2.1) and nothing downstream subtracts a per-range background, a single dark
reading at the most sensitive range is very likely enough. Implement
`measure_background` with a `sweep_all_ranges=False` default that takes one dark
per detector and writes it to the corresponding `bkgN`, keeping the full sweep
behind the flag for Sunday's testing. Called from `command_list.py:171`.

**Decided (Q19): measure UPD's dark only.** There is one `bkgN` table per
sequence program and it serves both UPD and TRD (§2.3), so they cannot both be
stored. Transmission is a ratio of two strong signals, so TRD's dark does not
matter today. Drop `trd_controls` from the `measure_background` call at
`command_list.py:172-174`; keep `I0_controls`/`I00_controls` (different box). A
later autoranger revision may hold all four channels' darks — revisit then.

**New class `FX4AutorangeDevice`** in `devices/fx4_quadem.py` — same shape as
`AmplifierAutoDevice` minus the four dead components, plus `channel`, `current`,
`mode_rdbk`, `speed`. Its `ranges` sub-device drops the `gain` field and keeps
`background`/`background_error`, so `measure_background`'s write targets are
**unchanged** — that plan ports almost verbatim, only the measured quantity
changes from counts/s to amps (read `seq01:current` or the channel's
`mean_value`).

**`gain` has no replacement and that is a real code change.** Every
`control.auto.gain` reference must become a *range index*:

* `amplifiers_plan.py:232,244,247` — `_last_autorange_gain_` keyed on
  `control.auto.gain.name` → key on `lurange`/`reqrange` instead.
* `uascan_plan.py:174-181` — `read_devices` lists four `auto.gain` +
  four `auto.reqrange` → `lurange` + `reqrange` (+ `current` is worth recording).
* `plans_usaxs.py:237-238,509-511` — saves/restores `auto.gainU`/`gainD`;
  those **do** exist in `seq01:`, so unchanged.
* `plans_user_facing.py:229,526` and `sample_transmission.py:225` use
  `*_controls.femto.gain.get()` — that is the **Femto** gain, a different object
  which does not exist for FX4 channels at all. See Q8.

**`DetectorAmplifierAutorangeDevice` needs an FX4 sibling.** It hard-requires a
`ScalerCH`, a `ScalerChannel`, a `FemtoAmplifierDevice` and an
`AmplifierAutoDevice`, type-checking all four (`devices/amplifiers.py:341-370`).
For FX4 there is no scaler and no Femto. New `FX4DetectorControls` binding
*(quadem device, channel number, FX4AutorangeDevice or None)*, with `None`
meaning fixed-range (I0/I00 on Sunday). `group_controls_by_scaler` becomes "group by electrometer box" — but see below,
because the grouping now has to *reject* multi-channel groups rather than
converge them together.

**Channel selection is now part of autoscale (§2.3).** Add a stub:

```python
@plan
def select_fx4_channel(controls):
    """Point the box's seq0N autoranger at this detector's channel."""
    yield from bps.mv(controls.auto.channel, controls.channel_number)
    yield from bps.sleep(controls.auto.settling_time)
```

and call it at the top of `_scaler_autoscale_` for each box's single active
control. `group_controls_by_scaler` → `group_controls_by_box`, with an explicit
guard: **if a box appears twice with two autoranged channels, raise** rather than
silently converge one and de-converge the other. A clear
`FX4RangeConflictError("fx4: cannot autorange UPD and TRD together — they share
one range")` is worth far more than a plausible-looking wrong number. Controls
whose `auto is None` (fixed range — I0/I00 on Sunday) are skipped entirely and
never count toward the conflict.

With that guard in place the existing call sites need only
`[upd_controls, I0_controls]` → unchanged (one per box), and the transmission
sites `[I0_controls, trd_controls]` → unchanged (one per box), because
`select_fx4_channel` puts `seq01:channel` at 4 for the TRD leg and the tune plans
put it back to 1. The `[upd, I0, I00]` sites are fine while I00 is fixed-range,
and will raise the moment it is not — which is the desired behaviour.

**Convergence window.** `min_count_rate=500` / `max_count_rate=950000` become
`min_fraction=0.10` / `max_fraction=0.90` -- matching the IOC, which switches
down below 10 % of full scale and up above 90 %. Fractions rather than absolute
currents, so a range-table change cannot silently invalidate them; full scale
comes from parsing the `Range` enum label
(`utils/fx4_ranges.py: full_scale_pA`). Absolute backstops of 1 pA and 1e10 pA
(10 mA, the top of the FX4 range table) catch a nonsense reading -- a dead PV,
a unit error -- that the fractional test would pass. `seq01:gainU`/`gainD` are the IOC-side setpoints, already tuned. The plans must
**stop writing them** — see the trap below.

#### ⚠️ A guaranteed Sunday bug: the plans will overwrite your tuned `gainU`/`gainD`

You said autoranging is tuned and any tweak is a manual EPICS change. It will not
survive one scan. `terms.USAXS.setpoint_up/down` and
`terms.FlyScan.setpoint_up/down` are **soft `ophyd.Signal`s with hard-coded
Python defaults** — not EPICS PVs (`general_terms.py:54-55, 212-213`):

```python
setpoint_up   = Component(Signal, value=6000)     # FlyScan
setpoint_down = Component(Signal, value=850000)
setpoint_up   = Component(Signal, value=4000)     # USAXS step
setpoint_down = Component(Signal, value=650000)
```

They reset to those **count-rate** numbers on every session restart, and four
code paths push them straight into the sequence program:

* `plans_usaxs.py:244-247` — every `USAXSscanStep`
* `plans_usaxs.py:497-500` — every `Flyscan`
* `tune_guard_slits.py:433-436`
* (`:342-344`, `:619-621` restore the pre-scan values afterwards)

So the first `Flyscan` after startup writes `850000` into
`usxFX4:FX4:seq01:gainD` and your tuning is gone.

**Decided (Q18): delete all four write blocks**, and the matching save/restore
(`plans_usaxs.py:239-240,342-344,492-493,619-621`), which becomes pointless once
nothing overwrites. One tuned set serves all modes; the IOC owns it. The
`setpoint_up`/`setpoint_down` soft signals in `general_terms.py:54-55,212-213`
become unreferenced and should go too. This removes code rather than adding it.

### 4.2 Tune plans (`plans/axis_tuning.py`) — the bulk of the work

Eight plans (`tune_mr`, `tune_ar`, `find_ar`, `tune_a2rp`, `find_a2rp`,
`tune_dx`, `tune_dy`, + `tune_usaxs_optics`/`tune_saxs_optics`) all follow the
same shape:

```python
bps.mv(scaler0.preset_time, 0.1)          → bps.mv(fx4.averaging_time, q(0.1))
bps.mv(upd_controls.auto.mode, "manual")  → usxFX4:FX4:seq01: mode  (§4.1)
autoscale_amplifiers([upd_controls, I0_controls])
scaler0.select_channels(["UPD"])          → set kind on fx4.current{n}.mean_value
lineup2([UPD, scaler0], axis, …)          → lineup2([UPD, fx4], axis, …)
scaler0.count_mode = "AutoCount"          → drop (no FX4 equivalent; see Q9)
```

Notes:
* `select_channels` has no FX4 analogue. Add a helper
  `fx4_plot_only(["UPD"])` that sets `kind="hinted"` on the chosen mean_value
  signals and `"normal"` on the rest. `QuadFX4._post_connect_setup` currently
  hints **all four** channels — that would put four traces on every tune plot.
* `find_ar` / `find_a2rp` use `upd_photocurrent_calc` (the `usxLAX:USAXS:upd`
  swait that converts counts+gain → photocurrent). With the FX4 the reading
  *is* photocurrent, so these plans **simplify**: use
  `fx4.current1.mean_value` for both the wide and the fine scan, and the
  `scaler0.kind`/`select_channels([])` plot-suppression dance goes away.
* `tune_guard_slits.py` uses the older `TuneAxis` API with
  `signal_name=UPD_SIGNAL.chname.get()` (`:103`, `:247`) — that reads the
  scaler channel *name PV*. Needs a plain string `"UPD"` instead.
* `plans_tune.py:108,137,211,240` — only `scaler0.preset_time`; mechanical.

### 4.3 `uascan` (`plans/uascan_plan.py`) — step USAXS

* Prologue `bps.mv(...)` at `:141` sets `scaler0.count/preset_time/count_mode`
  plus the four `*_controls.auto.mode` values → FX4 scaler-mode config call.
* `read_devices` (`:172`) lists `scaler0` plus eight `auto.gain`/`auto.reqrange`
  signals. Becomes the two `mean_value` signals (`UPD`, `I0`) plus diagnostics
  (`em_range`, `num_averaged`, `ring_overflows`). The gain signals go away
  entirely — nothing consumes them (§2.1).
* **Drop `TRD` and `I00` from the scan.** `quiet_detectors = [I00, trd]`
  (`:184-187`) existed because `scaler0` swept up every channel whether you
  wanted it or not. FX4 channels are read explicitly, so they simply are not
  listed — and TRD would be railed anyway at UPD's range (§2.3.2). Most of the
  `quiet_detectors` / `new_kinds` / `original_kinds` bookkeeping at `:184-210`
  can go with it.
* Inner loop `:298` sets `scaler0.preset_time` per point (dynamic time) →
  `fx4.averaging_time` **and** `fx42.averaging_time`, both quantised.
* `:316` `bps.trigger(scaler0, group=…)` → trigger both boxes in the same
  group, then one `bps.wait`.
* Epilogue `:327` restores `count_mode` → drop / replace.
* `_md["hints"]` (`:230`) names `["a_stage_r", "I0"]`; keeps working if we keep
  the name `I0` (§3.4).

### 4.4 The rest of the `scaler0` touchpoints

Mostly housekeeping that can be **left alone** if `scaler0` stays installed
(recommended, see §6):

`mode_changes.py:183`, `resets.py:59`, `sample_rotator_plans.py:121-122`,
`sample_imaging.py:27`, `plans_usaxs.py:332,512,609`, `test_plan.py`,
`filter_plans.py:38-42` and `move_instrument.py:39-43` (both build their **own**
`ScalerCH` at module scope — harmless, but note they bypass `oregistry`).

`resets.py:81-84` sets `kind` on `TRD`/`I0`/`I00`/`upd_controls` — must be
updated to the FX4 signals or it will `AttributeError` once the names move.

---

## 5. Phase 2 — transmission, Phase 3 — fly scan, Phase 4 — data

### 5.0 SAXS / WAXS normalisation — a real gap (Q7)

**In scope for Sunday, with a known compromise.**

Today `scaler1` (`usxLAX:vsc:c1`) is **hardware-gated by the area-detector
exposure**: the I0 V/F frequency is split into `scaler0` (free) and `scaler1`
(gated), and the gated count is the per-frame normalisation. It reaches the data
three ways — `terms.SAXS_WAXS.I0_gated` (`plans_user_facing.py:325,577`), the
`I0_cts_gated` NDAttribute, and the NXcanSAS `/entry/control/integral` hardlink
(§1.4).

**The FX4 has no equivalent.** There is no frequency to split and no hardware
gate wired to the detector exposure.

*Sunday approach (agreed):* software-trigger `fx42` Current1 with
`AveragingTime ≈ the image exposure time`, started next to the detector
acquisition. The start jitter is small compared with the exposure, so the ratio
is good enough for observation. Implementation:

* set `fx42.averaging_time = quantize_count_time(terms.SAXS.acquire_time)`
  where the plans currently set `scaler1.preset_time`;
* trigger `fx42` immediately before `areaDetectorAcquire`, read its
  `mean_value` into `terms.SAXS_WAXS.I0_gated` where
  `scaler1.channels.chan02.s.get()` is read today;
* keep the `attributes.xml` name **`I0_cts_gated`** so the
  `/entry/control/integral` hardlink and the reduction path keep working
  unchanged — only the units change, and `counting_chain` says so.

> ### 📌 TODO (Jan) — plan during the shutdown
> **Sort out proper gating for SAXS/WAXS image normalisation.** The software
> trigger above is a stopgap: the integration window is only approximately the
> exposure window, so it drifts with detector dead time, multi-image series
> (`terms.SAXS.num_images > 1`), and any acquire-period overhead. Options to
> evaluate: feed the detector exposure/trigger output into an FX4 digital input
> and run that channel in bulb mode (one pulse per frame — this would also give
> *per-frame* normalisation for image series, which the current single gated
> count does not); or keep a small gated counter alongside the FX4 purely for
> this purpose. Needs hardware, hence shutdown.

### 5.1 Transmission (`plans/sample_transmission.py`)

Same shape in both `measure_USAXS_Transmission` (`:39`) and
`measure_SAXS_Transmission` (`:150`):

```python
bps.mv(scaler0.preset_time, T)            → both boxes, quantised
scaler0.select_channels(["I0", "TRD"])    → drop (kind helper)
no_run_trigger_and_wait([scaler0])        → no_run_trigger_and_wait([fx4, fx42])
s = scaler0.read(); secs = s["scaler0_time"]["value"]
                                          → averaging_time (and cross-check num_averaged*sample_time)
_tr_diode = s["TRD"]["value"]  # counts    → amps
```

The saturation test `_tr_diode > secs * TR_MAX_ALLOWED_COUNTS` (`:194`) becomes a
current-vs-range-top test in pA — and note it currently multiplies by `secs`
because counts scale with time. **The FX4 mean does not**, so the `* secs` must
come out or the threshold moves with count time.

Storage (`:225`, and `plans_user_facing.py:577-586`): write the pA value into
`terms.SAXS_WAXS.{diode,I0}_transmission` and **`1.0` into the matching
`*_gain` PVs**. Any downstream code that still divides by gain then gets the
right answer, and the transmission is simply `diode / I0` as §2.1 says. Do *not*
put the FX4 range index in `*_gain` — a reader that divides by it would be
silently wrong by orders of magnitude. If the range is wanted for diagnostics it
belongs in a new field, not in `*_gain`.

**Channel switching (§2.3).** Both transmission plans measure TRD, so they must
put `usxFX4:FX4:seq01:channel` at **4** before autoscaling and back to **1**
afterwards. Both are called from inside `USAXSscanStep` (`plans_usaxs.py:235`)
and `Flyscan` (`:488`) immediately before the scan, so a missed restore means the
whole subsequent USAXS scan autoranges on the wrong channel — put the restore in
a `finally`, not just on the success path. `measure_SAXS_Transmission` has the
same requirement and additionally runs inside `saxsExp`.

This also removes the `*_controls.femto.gain.get()` calls
(`sample_transmission.py:228,232`, `plans_user_facing.py:581,585`), which would
otherwise `AttributeError` — there is no Femto on an FX4 channel.

### 5.2 Fly scan (`plans/fly_scan_plan.py`)

The trajectory, busy record, suspender/checkpoint logic and HDF5 threading are
**unchanged**. What changes:

1. Before arming: `fx4_flyscan_mode(fx4, npts)` and the same for `fx42`, with
   `npts = flyscan_trajectories.num_pulse_positions.get()` (+ margin).
2. Arm the time series (`TSControl = "Erase/Start"` on each used channel), then
   `acquire = 1`, **then** fire the busy record. Ordering matters: the
   electrometer must be running before the first strobe.
3. After `bps.wait(group=g)`: `acquire = 0`, then harvest
   `current{n}.ts_mean_value`, `ts_total`, `ts_sigma`, and
   `ts_current_point`.
4. `progress_reporting._report_` reads `struck.elapsed_real_time` /
   `struck.current_channel` (`:104,:107`) → FX4 `Current1:TSCurrentPoint`
   (and `num_averaged` as the live per-pulse health check, §cheatsheet add-on).
5. `plans_usaxs.py:587` compares `num_pulse_positions` against
   `struck.current_channel` to warn about missed points → same comparison
   against `ts_current_point`.
6. `plans_usaxs.py:507-530` sets up autocount-mode scaler autoranging during
   the fly scan (`FlyScanAutoscaleTime = 0.025`) — that whole block is the
   *old* in-flight autoranging mechanism, which also drove the now-obsolete
   gain-change-array patch. **Delete this block.** In-flight autoranging is
   handled by `usxFX4:FX4:seq01:` itself; the plan only has to put it in
   auto mode before the sweep and record `lurange` before/after.
7. **Check `RingOverflows == 0`** after every fly scan and warn.

#### Commissioning the PSO gate — find the working VPR (the long pole)

The one thing that cannot be desk-planned: *under what conditions does the FX4
register every PSO pulse?* Two effects push in opposite directions (§8/§10 of
the setup doc) — too low a VPR floods the WebSocket link and **drops** edges,
too high a VPR cannot **resolve** the HIGH strobe and **merges** neighbouring
exposures. Both look like "missed pulses" in `TSCurrentPoint`.

They are distinguishable, which makes this a quick bisection rather than a hunt:

| symptom | cause | fix |
|---|---|---|
| fewer points, `NumAveraged` roughly normal | dropped in transit | **raise** VPR |
| fewer points, `NumAveraged` ≈ 2× normal on the short ones | merged exposures | **lower** VPR, or widen the strobe |

Procedure — run a short trajectory (a few hundred pulses) at VPR ∈ {5, 10, 20,
50}, and for each record `Current1:TSCurrentPoint` against
`usxAERO:pm1:NumPulses`, plus `RingOverflows` and the spread of
`NumAveraged_RBV`. Pick the **largest** VPR that captures 100 % with margin,
then verify at full length (8000 pulses) and with **both boxes streaming at
once** — the two FX4s share one host, and the throughput limit is a property of
that host, so a VPR that works for one box alone may not work for two.

Worth scoping the PSO strobe at D1 while doing this: the minimum safe strobe is
3-5 × SampleTime, so the measured width directly predicts the VPR ceiling.
Widening the strobe in the Aerotech PSO config is the other lever if the
window between "drops" and "merges" turns out to be uncomfortably narrow.

**No parallel-running safety net.** An earlier draft proposed leaving the Struck
armed alongside the FX4 for cross-calibration. The rewiring (Q10) makes that
impossible — with the diodes on the FX4 the Struck has nothing to count. See §6
for what replaces it: validation against an archived standard.

Leave the `struck` device declared in `devices.yml` regardless. It costs nothing
idle and keeps a partial rollback cheap.

### 5.3 Phase 4 — the four file formats (§1.4)

Everything here is additive and self-describing: old files stay readable, new
files announce themselves. **One marker, same two names, all four formats:**

```
counting_chain = "FX4"      # absent or "SCALER" ⇒ the old chain
config_version = "2.0"
```

#### (1) Fly-scan HDF5 — `ADconfigs/Flyscan_config/saveFlyData.xml`

Bump `<saveFlyData version="2.0">` and the `config_version` attribute. Under
`entry/flyScan` (positioner fields `AR_*` unchanged):

```
@counting_chain = "FX4"
upd_current   [n] pA  ← usxFX4:FX4:Current1:TSMeanValue    @units="pA"   ← the data
upd_sigma     [n] pA  ← Current1:TSSigma   (spread within pulse, not SEM)
upd_total     [n]     ← Current1:TSTotal   (for N, below)
trd_current   [n] pA  ← usxFX4:FX4:Current4:TSMeanValue
I0_current    [n] pA  ← usxFX42:FX4:Current1:TSMeanValue     ← the normalisation
I0_sigma, I0_total
I00_current   [n] pA  ← usxFX42:FX4:Current2:TSMeanValue
n_points              ← Current1:TSCurrentPoint   (length_limit source, replaces mca_channels)
channel_time  [n] s   ← DERIVED (I0_total/I0_current)*sample_time  — diagnostic, NOT normalisation
sample_time, values_per_read          ← so channel_time can be re-derived
ring_overflows_fx4, ring_overflows_fx42   ← must be 0 or the means are biased
fx4_range_upd, fx4_range_trd, fx42_range_I0   ← DIAGNOSTIC ONLY (§2.1), nothing
                                                consumes these; they exist so a
                                                railed range is visible after the fact
```

`saveFlyData.py` computes nothing today — it is a pure PV→HDF5 mapper. So
`channel_time` needs either a small post-processing hook in `saveFlyData.py`, or
leave it out and let reduction derive it from `*_total`/`*_current`/`sample_time`,
all of which are in the file. **Recommend deriving it in the writer** so the
field has the same *meaning* as the old clock array and reduction needs no new
arithmetic.

`length_limit="mca_channels"` becomes `length_limit="n_points"`; the `signal`
attribute moves from `mca3` to `upd_current`. `EPICS_CA_MAX_ARRAY_BYTES` must
cover 8000 doubles × ~6 arrays × 2 boxes.

The `usxLAX:USAXSfly:<det>:{mcsChan,ampGain,ampReqGain}` gain-change arrays are
**dropped** — that patch has not been used in a long time and is not being
carried forward. Record `lurange` before and after the sweep and leave it there.

#### (2)+(3) SAXS / WAXS -- DONE (offline)

`ADconfigs/{SAXS,WAXS}_config/attributes.xml` and the two layout files now
carry the FX4 chain. Decisions worth knowing on the reduction side:

* **`I0_cts_gated` keeps its name, and now sources `Current1:Total_RBV`** --
  the sum of samples in the reading, i.e. the scaler-like integral. That is the
  semantically right thing behind `/entry/control/integral` (an NXmonitor
  integral, not a mean), and it means the `layout.xml` hardlink needed no
  change at all. Absolute charge is `I0_cts_gated x FX4_SampleTime`, in pA.s.
  `MeanValue_RBV` is exposed separately as `I0_current`.
  *Using `Total` rather than `MeanValue` also makes normalisation robust to a
  varying exposure time, which the software-triggered window (section 5.0) will
  have.*
* Added: `I0_current`, `I00_current`, `FX4_SampleTime`, `I0_range`
  (diagnostic), `FX4_RingOverflows`; WAXS additionally gets `TR_cts_gated` and
  `TR_current` from `usxFX4:FX4:Current4`.
* The old-chain attributes (`I0_cts`, `I00_cts`, `TR_cts`, `scaler_freq`,
  `*_gain`) are **commented out, not deleted** -- one uncomment each to roll
  back. Nothing feeds them after the rewire, and a stale value is worse than an
  absent one.
* `I000_cts` is untouched: it comes from `usxLAX:vsc:c2`, a different scaler,
  outside this conversion (section 1.5).
* `counting_chain = "FX4"` and `config_version = "2.0"` added to both layouts as
  constants under `/entry`.
* ⚠️ Re-run `ADconfigs/WAXS_config/copy_attributes_to_template.py` before
  deploying, so the template's `NXcollection` matches the new attribute list.

#### (4) uascan HDF5 — `callbacks/nxwriter_usaxs.py`

Written from the primary stream, so §3.4's naming decision determines the
layout. Add `counting_chain`/`config_version` in `write_entry()` alongside the
existing `config_version = "1.0"` class attribute, and stamp
`md["counting_chain"]` in the plans so it also lands in `bluesky_metadata`.

#### Deployment

`ADconfigs/` is now in the repo but the IOCs read from
`/share1/AreaDetectorConfig/`. Keep the repo copy authoritative and deploy from
it; add a short `ADconfigs/README.md` saying so, plus a note that
`Flyscan_config/saveFlyData.xml` here supersedes the stale
`src/usaxs/usaxs_flyscan_support/saveFlyData_EXAMPLE.xml` (which should be
deleted or clearly marked obsolete).

## 6. Rollback, and how we know the new chain is right

**Decided (Q10): branch switch.** The hardware is rewired, so a runtime
`COUNTING_CHAIN` switch would be a lie — there is nothing for `scaler0` to count.
Edits go in place on `fx4-conversion`; rollback is `git checkout main`, restart,
and *rewire*. No `counting.py` abstraction layer, which removes roughly a day of
work from §9.

The old chain is therefore not available for side-by-side comparison — once the
diodes are on the FX4, `scaler0` and the Struck read nothing.

### Validation: the standard reference material

The hardware swap happens before testing and the instrument is in operations, so
the acceptance test is the routine one: **measure the standard reference
material and require it to look exactly the same.** Anything else means
something is wrong. You have the standards and the archived reductions already.

Two things worth being explicit about, because they are the failure modes a
"looks the same" test can miss:

* **A pure scale error passes a shape check.** `diode / I0` is a ratio, so a
  common scale factor on both channels cancels: the *shape* of I(q) comes out
  right while the absolute intensity does not. Your SRM is on absolute scale, so
  it catches this — provided the absolute level is checked and not just the
  curve shape. If the absolute scale needs work, that is a commissioning task
  with time before the next user run, not a Sunday blocker; what matters on
  Sunday is understanding *why* a level is off, not necessarily fixing it.
* **A unit error is a factor of 10¹².** Confirm early that
  `MeanValue_RBV` is in pA and not A (§2.1, bench script §7).

The rollback window is **weeks**, not hours: Sunday decides "same or better,
keep going" versus "switch back and rethink", and there is time for either. That
takes most of the schedule pressure off §9 — the plan below is ordered by risk
rather than by a deadline.

### What a rollback actually costs

Because there is no software switch, keep the deletions conservative:

* **Do not delete** `scaler0`/`scaler1`/`struck` from the YAML on this branch.
  Leave the devices declared and merely unused. They cost nothing when idle and
  make a partial rollback (e.g. SAXS/WAXS back on scalers while USAXS stays on
  FX4) a small edit instead of a revert.
* **Do** drop the scaler0 `I000` channel, `I000_femto_amplifier` and
  `I000_photocurrent_calc` (§1.5) — genuinely dead.
* Keep commits small and phase-shaped (§9) so a single phase can be reverted
  without taking the others with it.

## 7. Bench script — please run this on a machine with EPICS access

I cannot reach the softIOC from here (the FX4 *device* answers on
`10.54.122.170:80`, but channel access to `usxFX4:` does not resolve). These are
all read-only except one harmless single acquisition. Output of the whole thing
pasted back unlocks Q4b, Q5b and the §3.1 device-layer detail.

```bash
# ── 1. THE BIG ONE: what does the autorange sequence program expose? (Q4b) ──
dbl "usxFX4:FX4:seq01:*"

# ── 2. TS records: on the stats plugin, or a separate TS plugin? (§3.1) ──
dbl "usxFX4:FX4:Current1:*" | grep -i ts
caget usxFX4:FX4:Current1:TSMeanValue.NELM     # max fly-scan points, want >= 8000

# ── 3. Enum strings — confirm the indices match the cheatsheet ──
caget -d 31 usxFX4:FX4:TriggerMode
caget -d 31 usxFX4:FX4:TriggerPolarity
caget -d 31 usxFX4:FX4:AcquireMode
caget -d 31 usxFX4:FX4:Range

# ── 4. Is FX42 alive, and does it look the same? ──
caget usxFX42:FX4:Model usxFX42:FX4:Firmware
dbl "usxFX42:FX4:seq01:*" | head          # does it have an autoranger yet?

# ── 5. PSO strobe width — sets the fly-scan VPR ceiling (§3.3) ──
dbl "usxAERO:pm1:*" | grep -i "pulse\|width"
caget usxAERO:pm1:PulseWidth usxAERO:pm1:NumPulses

# ── 6. UNITS: is MeanValue in pA or A?  (a factor of 1e12, §2.1) ──
caget usxFX4:FX4:Current1:MeanValue_RBV       # with beam: plausible in pA? in A?
caget usxFX4:FX4:ch1_CurrentScale usxFX4:FX4:Current1:MeanValue_RBV.EGU

# ── 7. Present state, for the record ──
caget usxFX4:FX4:ValuesPerRead usxFX4:FX4:SampleTime_RBV \
      usxFX4:FX4:AveragingTime usxFX4:FX4:RingOverflows \
      usxFX4:FX4:Current1:EnableCallbacks usxFX4:FX4:Current1:CallbacksBlock
```

**One live test** (needs beam off or shutter closed; ~10 s, restores nothing —
just note what the settings were first from step 6):

```bash
# Does CallbacksBlock=Yes make Acquire wait for MeanValue?  (the whole step-scan
# trigger model rests on this)
caput usxFX4:FX4:TriggerMode "Free run"
caput usxFX4:FX4:AcquireMode Single
caput usxFX4:FX4:ValuesPerRead 100
caput usxFX4:FX4:Current1:EnableCallbacks Enable
caput usxFX4:FX4:Current1:CallbacksBlock  Yes
caput usxFX4:FX4:AveragingTime 3.0
time caput -w 20 usxFX4:FX4:Acquire 1          # should take ~3 s, not return instantly
caget usxFX4:FX4:NumAveraged_RBV usxFX4:FX4:RingOverflows
#   expect NumAveraged ~ 3000 at VPR=100, RingOverflows unchanged

caput usxFX4:FX4:AveragingTime 10.0
time caput -w 30 usxFX4:FX4:Acquire 1
caget usxFX4:FX4:NumAveraged_RBV usxFX4:FX4:RingOverflows
#   expect ~10000 and STILL no new overflow — confirms VPR=100 gives a 10 s ceiling
```

Also useful, whenever a fly scan next runs with the FX4 in bulb mode: confirm
`TSTotal / TSMeanValue` really equals the per-pulse sample count by comparing
against `camonitor usxFX4:FX4:NumAveraged_RBV`. The `channel_time` derivation
(§5.3) rests on it, though it is no longer on the normalisation path.

## 8. Questions

### Resolved

| # | Answer | Consequence |
|---|--------|-------------|
| Q1 | TRD = `fx4` **Current4**, expected to move | channel map lives in `iconfig.yml`, not code (§1.3) |
| Q2 | I0 on `fx42` Current1, **fixed manual range** Sunday | autoscale loop runs on `fx4` only; autorange-vs-fixed is config-driven (§4.1) |
| Q3 | I00 → `fx42` Current2 | but §1.5 — scaler0 I000 droppable, **scaler2 I000 is in use**, leave it |
| Q4 | seq program `usxFX4:FX4:seq01:`, PV list received | close port of `AmplifierAutoDevice`; `gain`/`gainN`/`vfc`/`lucounts`/`lurate` gone, `channel`/`current`/`modeRdbk`/`speed` new (§4.1) |
| Q4b | gain-change-array patch obsolete | **dropped** from the fly-scan file (§5.3); real task is PSO/VPR commissioning (§5.2) |
| Q5 | raise VPR, RING_SIZE stays 10000 | VPR=100 step (10 s ceiling), VPR=10 fly — different per mode, no IOC restart (§3.3) |
| Q6 | ≤5-6 s/point today, raise VPR for long ones | inside the VPR=100 ceiling; skew mitigation in §2.2 |
| Q7 | no gated equivalent — software-trigger `fx42` at ≈ image time | §5.0, **plus a shutdown TODO for proper gating** |
| Q8 | **FX4 value is gain-independent, in pA** | no gain bookkeeping anywhere; transmission and reduction are just `diode / I0`; ranges recorded as diagnostics only (§2.1) |
| Q9 | keep `UPD`, `I0`, `I00`, `TRD` | names stable everywhere; `counting_chain` marker carries the unit change (§1.4) |
| Q10 | **branch switch**, no runtime switch | no abstraction layer; but **no parallel validation** either — see §6 |
| Q13 | SAXS/WAXS in scope for Sunday | all four file formats in Phase 4 |
| Q14 | **one range per FX4, shared by all 4 channels**; use `seq01:channel` = 1 (UPD) / 4 (TRD) | new §2.3 — channel selection is now a Bluesky responsibility; autoscale must serialise per box and *reject* two autoranged channels on one box |
| Q15 | swap before testing; standard reference material is the test; weeks to decide | §6 — check absolute level, not just curve shape |
| Q16 | one dark at highest gain, revisit after tests | implement the simple version; keep the 5-range sweep available (§4.1) |
| Q17 | autoranging tuned, manual EPICS tweak if needed | one tuned set for all modes |
| Q19 | **UPD dark only**; TRD dark not needed for now | store UPD's dark in `seq01:bkgN`, skip TRD (§4.1). A later autoranger revision may hold all 4 channels' darks — revisit then |
| Q18 | **remove the setpoint writes** | delete 4 `gainU`/`gainD` write blocks + their save/restore (§4.1); IOC owns the thresholds |

### Open

**Q12. `ADconfigs/` as source of truth?** IOCs read
`/share1/AreaDetectorConfig/`. Can the repo copy be authoritative and deployed
from there, and can the stale
`src/usaxs/usaxs_flyscan_support/saveFlyData_EXAMPLE.xml` be deleted?

**Q11 (minor). Idle mode.** Plans park `scaler0` in `AutoCount` when idle for the
GUI. FX4 equivalent is free-running with the `…Ave` display PVs. Want an explicit
idle config the plans restore the same way?

## 9. Order of work

**Constraint that drives everything: there is no instrument access until
Sunday, and beamtime is the scarce resource, not coding time.** So the goal for
the next two days is to arrive on Sunday with nothing left to *write* -- only
things to *check and tweak*.

### Design rule for everything written offline

Anything that might turn out wrong on Sunday should be a **config value or a
defensive fallback, not a code edit**. Specifically:

* channel map in `iconfig.yml`, never a literal in a plan;
* enum values written as strings (`"Free run"`, `"Ext. bulb"`) so a menu-order
  surprise does not matter;
* range full scale parsed from the `Range` label, returning `None` and falling
  back to absolute backstops rather than guessing
  (`utils/fx4_ranges.py`);
* thresholds as ophyd `Signal`s so they can be changed live from the console;
* the TS record suffixes are the one place a live surprise means a real edit
  (section 3.1) -- so keep them in one class, not scattered.

### Offline: can be finished before Sunday

| | status |
|---|---|
| Phase 0 device layer: `QuadFX4`, `FX4AutorangeDevice`, `FX4DetectorControls` | ✅ done (`2c48e0f`) |
| `quantize_count_time`, ring-buffer helpers, tests | ✅ done |
| `fx4_setup.py`: mode plans, `select_fx4_channel`, `group_controls_by_box` | ✅ done |
| Fraction-of-full-scale thresholds + `fx4_ranges.py` | ✅ done |
| SAXS/WAXS `attributes.xml` + `layout.xml` v2.0 | ✅ done |
| `saveFlyData.xml` v2.0 (+ `channel_time` in `saveFlyData.py`) | **next** |
| Device/config YAML: `fx4`/`fx42` entries, autorange devices, channel map, baseline labels | todo |
| `fx4_autorange_plan.py`: autoscale + `measure_background` in pA | todo |
| Tune plans (8), `tune_guard_slits` | todo |
| `uascan` | todo |
| Transmission (both), with the `channel=4` switch in a `finally` | todo |
| Fly-scan plan: arm TS, harvest, progress reporting off `ts_current_point` | todo |
| SAXS/WAXS plans: software-triggered `fx42` I0 (section 5.0) | todo |
| Delete `gainU`/`gainD` writes + `setpoint_up/down` signals (Q18) | todo |
| Drop scaler0 `I000`, `I000_femto_amplifier`, `I000_photocurrent_calc` | todo |
| `SKILL.md`, `CLAUDE.md`, `ADconfigs/README.md` | todo |

### Needs the instrument: keep this list short

1. **Bench script (section 7)** -- pA units, TS record names, `Range` enum
   labels, PSO strobe width. 15 minutes, and it is the input to everything
   below.
2. **PSO/VPR commissioning (section 5.2)** -- the only genuinely empirical
   task. Bisect VPR against captured-pulse count, with both boxes streaming.
3. **Threshold tuning** -- `min_fraction`/`max_fraction` are live `Signal`s, so
   this is console typing, not editing.
4. **Validation** against the standard reference material (section 6).
5. **Regenerate** `src/usaxs/qserver/existing_plans_and_devices.yaml` -- needs a
   live session.

### If Sunday goes badly

The rollback window is weeks (section 6). A fly scan that is not working on
Sunday is a delay, not a failure: step scans, tuning and transmission are
independent of the PSO question and can be validated on their own.
