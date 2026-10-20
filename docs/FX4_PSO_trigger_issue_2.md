# FX4 gate input: minimum detectable PSO pulse width is ~1 ms and does not scale with the ADC sample rate

**Status:** open, root cause located, remedy needs a decision by the device
vendor and/or the driver maintainer.
**Site:** Advanced Photon Source, beamline 12-ID-E (USAXS instrument).
**Last updated:** 2026-10-20.
**Supersedes the conclusion of** `FX4_PSO_trigger_issue.md` §0 — that document
remains the record of the original measurement, but its stated root cause
("the device reports the gate on the ADC output sample cadence") has now been
disproved by direct experiment. Everything in this document is self-contained.

---

## 1. What we are asking

In externally-gated ("Ext. bulb") mode, the FX4 reliably registers a TTL gate
pulse on digital input **D1** only when the pulse is **≥ ~1 ms wide**. Narrower
pulses are captured with probability ≈ *width* / 1 ms. We have established that
this limit is **independent of every acquisition rate the EPICS driver can
set**, and that it comes from the digital input being read on a ~1 kHz polled
path that is architecturally separate from the ADC data path.

Two questions follow, one for each audience:

- **For Pyramid Technical Consultants (§7):** is the ~1 kHz polling of
  `/fx4/gpio_0/22/readback` inherent, or configurable? Is there a path by which
  D1 edges are latched in hardware (eCAP, PRU) and delivered with the ADC
  stream?
- **For the `quadEM` / `drvFX4` maintainer (§8):** `drvFX4` subscribes to D1
  through its plain GPIO readback node. Was a faster or edge-latched node
  considered, and would the driver accept gate data from one?

The cost of the present behaviour is ~5 % dead time in a continuous-scanning
experiment, and it sets a floor on how finely a sweep can be divided (§9).

---

## 2. System under discussion

| Item | Value |
|---|---|
| Device | Pyramid Technical Consultants **FX4** 4-channel electrometer, ×2 |
| Firmware | `26.06.181604`, identical on both units |
| IP addresses | `10.54.122.170` (UPD, TRD), `10.54.122.171` (I0, I00) |
| Control software | EPICS `quadEM` module, `drvFX4` driver (WebSocket + MessagePack) |
| Driver source date | `drvFX4.cpp` 2026-07-20 |
| IOCs | `usxFX4`, `usxFX42`; both last restarted 2026-10-19 |
| Gate source | Aerotech Automation1, position-synchronised output (PSO) |

### Signal path

- **Pulse Research Lab PRL-414B** 1:4 fan-out, 50 Ω back-terminated TTL line
  driver, ~2 ns edges. One output per FX4, so both units see the *same* pulse
  train.
- 50 Ω feed-through terminator at the D1 end → measured **2.5 V** HIGH, within
  the 3.3 V input spec and above threshold. (Unterminated, this driver gives
  4.4–5 V, which would over-drive the input.)
- Rear-panel DB9 expansion connector, **pin 1 = D1**, pin 9 = ground.
- The signal **idles LOW and strobes HIGH**. With `TriggerPolarity = Negative`
  the measurement intervals are the LOW periods *between* strobes, so the HIGH
  strobe is pure dead time — which is why its width matters.

### Current device configuration (read live, both units identical, 2026-10-20)

| Node | Value |
|---|---|
| `/fx4/digital_expansion/d1/user_label` | `PSO` |
| `/fx4/digital_expansion/d1/mode` | **`input`** |
| `/fx4/digital_expansion/d1/pull_mode` | `down` |
| `/fx4/gpio_0/22/debounce_enable/value` | `0` (disabled) |
| `/fx4/adc/conversion_frequency` | `100000` (100 kHz) |
| `/fx4/adc/sample_frequency/value` | `1000` (set from `ValuesPerRead`) |
| `/fx4/pruss/packet_inbox/poll_frequency` | **`1000`** |
| `/fx4/pruss/packet_inbox/packet_size` | `5` |
| `/fx4/pruss/packet_inbox/buffer_size` | `16384` |
| `/fx4/pruss/packet_inbox/overrun` | `25` |
| `/epics_server/poll/rate` | `50` (CA server only — not on the gate path) |

The device's own web UI labels `/fx4/gpio_0/22/readback` as **"PSO Readback"**
and `/fx4/gpio_0/23/readback` as "D2 Readback", confirming the pin mapping
`d1 ↔ gpio_0/22`.

---

## 3. The original symptom (2026-09-27)

A fixed 4000-pulse train over a ~90 s sweep, mean interval 22.5 ms. Only the
PSO pulse **width** was varied; spacing was unchanged (`FixedCount = 1`, so
width and period are independent). Captured intervals read from the driver's
own counter.

| Pulse width (µs) | Captured (of 4000) | Fraction |
|---|---|---|
| 400 | 1600 | 0.40 |
| 800 | 3200 | 0.80 |
| 1000 | 3800 | 0.95 |
| **1200** | **4000** | **1.00** |

`captured ≈ 4000 × (width / 1000 µs)`, saturating at ~1 ms. This is the
signature of a **periodically sampled level**: a pulse of width *w* covers a
sampling instant with probability *w*/*T* for *w* < *T*. The data give
*T* ≈ 1 ms.

Supporting observation: the two units miss *different* pulses from the same
fan-out (e.g. 889 vs 887 in one run) until the width is sufficient, after which
both reach 4000. The sampling is therefore per-unit and asynchronous, not a
common upstream loss.

---

## 4. The decisive experiment (2026-10-20)

The previous working hypothesis was that the gate is reported on the ADC
**output sample cadence**, i.e. at `100 kHz / ValuesPerRead`. That predicts the
minimum width scales with `ValuesPerRead`:

| `ValuesPerRead` | ADC output rate | predicted minimum width |
|---|---|---|
| 50 | 2 kHz | ~1500–2500 µs |
| 5 | 20 kHz | ~150–250 µs |

**Test:** both FX4s were run simultaneously on the same pulse train, one at
`ValuesPerRead = 50` and the other at `ValuesPerRead = 5` — a 10× difference in
ADC output rate — and the pulse width was scanned.

**Result:** both units behaved the same, and **both still required 1200 µs** to
capture all 4000 pulses.

**Conclusion:** the gate detection limit is entirely independent of
`ValuesPerRead`, and therefore of `/fx4/adc/sample_frequency`. The hypothesis in
`FX4_PSO_trigger_issue.md` §0 is wrong.

---

## 5. Root cause: the gate and the ADCs are different subsystems

### 5.1 The driver reads D1 through its plain GPIO register

`drvFX4.h:107-113` — the driver opens exactly five subscriptions:

```cpp
static inline const std::array<std::string, FX4_NUM_CHANS>
    ADC_PATHS = {
        "/fx4/adc/channel_1/value",
        "/fx4/adc/channel_2/value",
        "/fx4/adc/channel_3/value",
        "/fx4/adc/channel_4/value"
    };
static inline const std::string GATE_PATH = "/fx4/gpio_0/22/readback/value";
```

`ValuesPerRead` reaches the device by exactly one route — the `SetValuesPerRead`
calcout in `db/FX4.template:100`:

```
record(calcout, "$(P)$(R)SetValuesPerRead") {
    field(INPA, "$(P)$(R)ValuesPerRead CP")
    field(CALC, "100000/A")
    field(OUT,  "$(FXP)/fx4/adc/sample_frequency/value")
}
```

That node is inside the **`/fx4/adc/`** subtree. The gate is **`/fx4/gpio_0/22`**
— a different peripheral. No record in the template and no line in the driver
makes anything under `/fx4/gpio_0/` depend on `ValuesPerRead`. **The
independence measured in §4 is structural, and is exactly what the code
predicts.**

### 5.2 D1 is in the slowest mode the device offers

`/fx4/digital_expansion/d1/mode` is set to **`input`**. The device exposes these
alternatives for the same pin:

```
/fx4/digital_expansion/d1/mode/{input, capture, encoder, pru_input, pru_output,
                                pwm, expression, output, permit, software_timer,
                                can_tx, uart_rx}
```

`input` is the plain memory-mapped GPIO register, published by a software poll.
`capture` and `pru_input` are the hardware-latched paths (§6).

### 5.3 The 1 kHz is a configured poll rate, not a measurement artefact

`/fx4/pruss/packet_inbox/poll_frequency` reads **exactly 1000** on both units,
is stable across repeated reads over several seconds (so it is configuration,
not a measured statistic), and — critically — **does not follow
`/fx4/adc/sample_frequency`**. During the §4 test the two ADC rates were 2 kHz
and 20 kHz while this value stayed at 1000 on both units.

A GPIO level published from a 1 kHz poll yields capture probability
`min(1, width / 1 ms)`, which reproduces §3 and §4 exactly.

---

## 6. What we ruled out

| Candidate | Status | Evidence |
|---|---|---|
| ADC sample rate (`ValuesPerRead`) | **Excluded** | §4 experiment; §5.1 code path |
| Input debounce filter | **Excluded** | `gpio_0/22/debounce_enable = 0` on both units |
| Signal integrity / level | **Excluded** | 2.5 V into 50 Ω, ~2 ns edges, measured |
| Upstream PSO fault | **Excluded** | Units miss *different* pulses from one fan-out (§3) |
| IOC ring buffer | **Excluded** | `RingOverflows = 0`; loss is on the device, before transmission |
| EPICS CA server rate | **Not on this path** | `/epics_server/poll/rate = 50` serves CA clients; the driver uses the WebSocket |

---

## 7. For Pyramid Technical Consultants — device and firmware

### 7.1 The central question

Is the ~1 kHz publication rate of `/fx4/gpio_0/22/readback` **inherent to the
`input` pin mode**, or is it configurable?

We could not determine from outside whether the 1 kHz sampling happens in the
Linux application polling the GPIO data register, or in the PRU with the
application draining the result at 1 kHz. **This distinction decides whether a
remedy is a setting or a firmware change**, so it is the single most useful
thing you can tell us.

One observation that bears on it: `/fx4/pruss/packet_inbox/packet_size` is **5**
while there are 4 ADC channels. If the 5th word carries status or digital-input
bits, then D1 transitions are already being captured in hardware at the
conversion rate and only their *exposure* through the `gpio_0` readback node is
slow — in which case the information we need already exists on the device.

### 7.2 Specific questions

1. At what rate is `/fx4/gpio_0/<n>/readback` sampled and published in pin mode
   `input`? Is that rate settable, and if so through which node?
2. Is `/fx4/pruss/packet_inbox/poll_frequency` writable in practice? EPICS
   `cainfo` reports it `read, write`, but your web UI renders it read-only, so
   we have not attempted a write on a production instrument. What would raising
   it to 2–5 kHz affect, and is it safe? (Note `overrun = 25` already.)
3. Does the PRU packet (`packet_size = 5`) include digital input state? If so,
   can that be exposed as a subscribable node, time-aligned with the ADC
   samples?
4. In pin mode **`capture`**, is D1 routed to an eCAP peripheral? The node tree
   exposes `/fx4/ecap_0` and `/fx4/ecap_2` in full — `capture_mode`, four
   events with independent rising/falling polarity, prescaler,
   `timestamp_counter_enable`. If D1 can be captured there, what is the
   minimum detectable pulse width, and how are the timestamps retrieved?
5. In pin mode **`pru_input`**, at what rate does the PRU sample the pin?
6. The `/fx4/data_acquisition/` subsystem offers `gating_enabled`,
   `gating_expression`, `acquisition_gated` and `start_trigger`/`stop_trigger`
   with rising/falling edges, and its `standalone_channels` list includes
   **PSO (`/fx4/digital_expansion/d1`)** alongside the four ADC channels and
   their per-channel `integrator` nodes. Is this gating performed in hardware?
   What is *its* minimum gate pulse width? This looks like the facility our
   application actually wants, and the EPICS driver does not use it at all.
7. Is there any mode in which D1 edges are **latched** (so that an arbitrarily
   narrow pulse sets a flag that is cleared on read), rather than sampled?

### 7.3 What "good" would look like for us

A 100–200 µs strobe detected with 100 % reliability. At our 22.5 ms mean
interval that reduces dead time from ~5 % to under 1 %, and more importantly
removes the floor on how finely we can divide a sweep.

---

## 8. For the `quadEM` / `drvFX4` maintainer

These are observations and questions, not bug reports — several may be
deliberate.

### 8.1 Gate source

`GATE_PATH` (`drvFX4.h:113`) is hard-coded to `/fx4/gpio_0/22/readback/value`.

- Was a faster or edge-latched device node evaluated? If Pyramid can expose one
  (§7.2), would the driver take the gate from it — ideally as a configurable
  path rather than a compile-time constant?
- Related: the hard-coded pin number assumes D1 is always `gpio_0/22`. That
  holds on our two units, but a configuration parameter would make the gate
  input selectable.

### 8.2 Gate events can be discarded with the ADC batch

In `onMessageEvent`, `eventList` is a function-local `std::multiset` built from
both the gate subscription and the ADC caches. Three paths discard it wholesale:

- **`drvFX4.cpp:456`** — `if (adcCache_[0].empty()) goto done;`. An update
  message that carries gate transitions but no channel-1 ADC samples loses
  every gate event in that message.
- **`drvFX4.cpp:486-494`** — when the four channels hold unequal sample counts
  and `synchronized_` is still false, all four caches are cleared and the
  whole `eventList` is dropped, gate events included.
- Once `synchronized_` becomes true, unequal counts are tolerated but only
  `minSize` samples are consumed per pass, so a channel skew persists in the
  caches (cleared only in `setAcquire`, `drvFX4.cpp:637`).

Is it intended that gate transitions are coupled to the presence of ADC data in
the same message? Buffering gate events across messages would decouple them.

### 8.3 Cross-subsystem timestamp ordering

`drvFX4.cpp:436` inserts gate events keyed on the GPIO subscription timestamp;
`drvFX4.cpp:522` inserts ADC events keyed on the channel-1 timestamp. They are
merged by `operator<` on `timeStamp` alone (`drvFX4.h:50`). Given that the two
streams originate in different device subsystems (§5.1), how comparable are
their timestamps? Exposure boundaries can only be as good as the coarser of the
two, and the existing diagnostic print at `drvFX4.cpp:438-441` ("Gate event …
ADC1 last time=…") suggests this has been looked at before.

### 8.4 `Ext. trigger` as an alternative

`drvFX4.cpp:534-556`: `QETriggerModeExtTrigger` starts on one edge and
integrates a fixed `numAverage_` samples, ignoring the closing edge. It still
has to see that one edge through the same 1 kHz path, so it does not avoid the
limit — but it would make the exposure length independent of strobe width, so a
missed edge would drop a point instead of merging two. Is that a supported way
to use the device for this kind of scan?

---

## 9. Impact and present workaround

`usxAERO:pm1:PulseLength = 1200` µs, `PulsePeriod = 1250` µs, `NumPulses = 4000`.
This gives 4000/4000 on both units.

Against a 22.5 ms mean interval that is **~5 % dead time**, and proportionally
more on the shortest intervals of the sweep. It does **not bias** the result:
the recorded quantity is a mean current over each interval, both electrometers
take the same gate, and the true per-interval duration is recovered and
recorded for every point. The cost is lost angular coverage and a floor on
sweep granularity.

We attempted to reduce the strobe to 600 µs on the strength of the (incorrect)
`ValuesPerRead` hypothesis. That is what the §4 test was, and it failed — hence
this document.

---

## 10. Possible remedies, ranked

| # | Remedy | Requires | Expected gain |
|---|---|---|---|
| 1 | Move D1 to `capture` (eCAP) or `pru_input` and have `drvFX4` read the gate from there | Pyramid to confirm the path + a driver change | Sub-µs; removes the limit entirely |
| 2 | Raise the GPIO publication rate (`poll_frequency` or equivalent) | Pyramid to confirm it is safe and supported | Linear: 2 kHz → ~600 µs, 5 kHz → ~250 µs |
| 3 | Use `/fx4/data_acquisition/` device-side gating with PSO as an acquisition channel and the per-channel hardware integrators | Significant driver work; Pyramid to confirm semantics | Hardware-timed; also removes software gating entirely |
| 4 | Keep the 1200 µs workaround | Nothing | None — ~5 % dead time, no bias |

Option 1 is the correct architecture. Option 2 is the cheapest thing that would
meet our immediate need. Option 3 looks like what the device was designed for.

---

## 11. Reproduction

### 11.1 The width scan

Aerotech Automation1 PSO configuration; vary only `FixedOnTime`:

```
PsoWaveformConfigureMode(axis, PsoWaveformMode.Pulse)
PsoWaveformConfigurePulseFixedTotalTime(axis, <period>)   ; µs
PsoWaveformConfigurePulseFixedOnTime(axis,   <width>)     ; µs  <-- varied
PsoWaveformConfigurePulseFixedCount(axis, 1)              ; one pulse per event
PsoDistanceConfigureAllowedEventDirection(axis, <dir>)
```

FX4 setup, then one sweep per width, comparing captured against emitted:

```bash
caput usxFX4:FX4:TriggerMode     "Ext. bulb"
caput usxFX4:FX4:TriggerPolarity Negative
caput usxFX4:FX4:AcquireMode     Continuous
# arm the time series, acquire, run the sweep, then:
caget usxFX4:FX4:Current1:TS:TSCurrentPoint   # captured
caget usxAERO:pm1:NumPulses                   # emitted
caget usxFX4:FX4:RingOverflows                # must stay 0
```

To separate *merged* exposures from *dropped* ones: a merged interval reports
`NumAveraged_RBV` roughly double its neighbours. `asynSetTraceMask("FX4",0,0x9)`
logs individual gate events.

### 11.2 The `ValuesPerRead` independence test (§4)

Set the two units to widely different rates and scan the width on both at once:

```bash
caput usxFX4:FX4:ValuesPerRead  50     # 2 kHz output
caput usxFX42:FX4:ValuesPerRead 5      # 20 kHz output
caget 10.54.122.170:/fx4/adc/sample_frequency/value   # confirm 2000
caget 10.54.122.171:/fx4/adc/sample_frequency/value   # confirm 20000
```

Both units will need the same ~1200 µs.

### 11.3 Reading the device node tree

Every device node is reachable over Channel Access as `<ip>:<node-path>`, and
the full tree can be dumped from the web UI bundle:

```bash
caget -t 10.54.122.171:/fx4/pruss/packet_inbox/poll_frequency
caget -t 10.54.122.171:/fx4/digital_expansion/d1/mode
cainfo    10.54.122.171:/fx4/pruss/packet_inbox/poll_frequency

curl -s http://10.54.122.171/ \
  | grep -oE "/fx4/[a-zA-Z0-9_/]*" | sort -u     # 2172 paths
```

---

## 12. Reference

**Driver source** —
`/net/s12dserv/xorApps/epics/synApps_6_3/support/quadEM-FX4/quadEMApp/FX4Src/`

| Location | What |
|---|---|
| `drvFX4.h:107-113` | `ADC_PATHS`, `GATE_PATH` — the five subscriptions |
| `drvFX4.h:50` | `operator<` — the ADC/gate merge key |
| `drvFX4.cpp:311-327` | `sendSubscribeEvent` |
| `drvFX4.cpp:424-441` | gate event decode and insert |
| `drvFX4.cpp:456` | `adcCache_[0].empty()` early return |
| `drvFX4.cpp:486-494` | unsynchronised-channel cache clear |
| `drvFX4.cpp:526-566` | the merged event dispatch loop (bulb/trigger/gate) |
| `drvFX4.cpp:588-622` | `setAcquireParams` — `NumAverage` from `AveragingTime` |
| `db/FX4.template:100-104` | `SetValuesPerRead` → `/fx4/adc/sample_frequency` |

**Related documents in this repository**

- `FX4_PSO_trigger_issue.md` — the original report and the 2026-09-27
  measurement. Its §0 root-cause conclusion is superseded by this document.
- `FX4_PSO_flyscan_setup.md` — operational setup; §8 (minimum strobe width) and
  §10 (`ValuesPerRead` throughput).
- `FX4_config_cheatsheet.md` — the two FX4 operating configurations.
- `../PLAN.md` §5.2 — fly-scan conversion status.

---

## 13. Open actions on our side

1. **Correct the code and docs that encode the disproved model.** Added
   2026-10-13 on the `ValuesPerRead` hypothesis and now known to be wrong:
   `utils/count_time.min_strobe_width_us()` and `MIN_STROBE_SAMPLE_PERIODS`
   (scale the floor with VPR — should be a single VPR-independent constant),
   the warning threshold in `plans/fly_scan_plan._check_strobe_width()`, the
   `DEFAULT_FLYSCAN_VPR` docstring in `plans/fx4_setup.py`, and the
   corresponding passages in `FX4_PSO_flyscan_setup.md` §8/§10,
   `FX4_config_cheatsheet.md` and `PLAN.md` §5.2. In particular the original
   advice in §8 of the setup document — *"do not try to fix this by lowering
   VPR"* — was **correct** and the 2026-09-30 note that superseded it should be
   withdrawn.
2. `ValuesPerRead` is, once again, purely a throughput/time-resolution choice
   with no coupling to the strobe. The "prefer higher, watch the link load"
   rule applies; `ValuesPerRead = 1` is still known to drop samples.
3. Put §7 to Pyramid and §8 to the driver maintainer.
