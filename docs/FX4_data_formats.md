# USAXS data formats after the FX4 conversion

**For whoever writes or updates the data reduction.**

The counting chain at 12-ID-E changed on 2026-09-26 from Femto amplifier +
V/F converter + scaler to **FX4 electrometers**. Four file formats carry
counting-chain data and all four changed. This file is the old→new map.

The single most important consequence:

> **Detector values are now gain-independent picoamps, not counts.**
> There is no amplifier gain to divide by, no per-range gain table, and for
> the fly scan no dwell-time term either. `I(q)` comes from
> `upd_current / I0_current` directly.

Some field names survived the change **with different units and meaning**
(`UPD` and `I0` in the step-scan file are the worst offenders). You cannot
tell the chain from the field names. Branch on `counting_chain`.

---

## 1. How to tell which chain produced a file

Every format declares `counting_chain`. `"FX4"` means picoamps; **absent**
means the old scaler chain and counts. Nothing else should be used for this
test.

| format | where `counting_chain` lives |
|---|---|
| fly scan | `/entry/flyScan/counting_chain` |
| SAXS frame | `/entry/counting_chain` |
| WAXS frame | `/entry/counting_chain` |
| step scan (uascan) | `/entry/instrument/bluesky/metadata/counting_chain` |

```python
def is_fx4(h5):
    """True if this file came from the FX4 chain (picoamps)."""
    for path in ("/entry/flyScan/counting_chain",
                 "/entry/counting_chain",
                 "/entry/instrument/bluesky/metadata/counting_chain"):
        if path in h5:
            v = h5[path][()]
            if isinstance(v, bytes):
                v = v.decode()
            return str(v).strip() == "FX4"
    return False        # absent -> old scaler chain
```

### Version numbers — read this before using them

There are **two unrelated** version numbers in play. Only the first tracks
the counting chain.

| field | meaning | old | new |
|---|---|---|---|
| `config_version` (fly scan, SAXS, WAXS) | counting-chain config version | `1.2` | **`2.0`** |
| `program_name@config_version` (step scan) | the NeXus *writer's* schema version, set by `nxwriter_usaxs.py` | `1.0` | `1.0` — **unchanged** |

The step-scan file's `1.0` is not a mistake and did not move with this
conversion; it describes the NeXus layout, not the detectors. **Do not branch
on it.** The step-scan file's only chain marker is `counting_chain`.

The fly-scan file also carries the version as a root attribute of the XML
map it was written from: `<saveFlyData version="2.0">`.

---

## 2. Fly scan — `<sample>_NNNN.h5`

Written by `usaxs_flyscan_support/saveFlyData.py` from the PV map in
`ADconfigs/Flyscan_config/saveFlyData.xml`. Arrays live in `/entry/flyScan/`.

### Detector arrays

| old (scaler / Struck 3820) | new (FX4) | notes |
|---|---|---|
| `mca1` | — **gone** | was the 50 MHz clock; the dwell divisor |
| `mca2` | `I0_current` | pA, mean over the PSO interval |
| `mca3` | `upd_current` | pA, mean over the PSO interval |
| — | `upd_sigma`, `I0_sigma` | per-interval standard deviation |
| — | `upd_total`, `I0_total` | sum of samples in the interval |
| — | `I00_current` | pA; nothing connected yet |
| — | `channel_time` | **derived**, diagnostic only (see below) |

### Supporting fields

| old | new | notes |
|---|---|---|
| `mca_clock_frequency`, `mca_channels*` | `sample_time`, `values_per_read` | FX4 timing |
| `upd_gain0..4` | — **gone** | reading is gain-independent |
| `DLPCA200_*`, `DDPCA300_*`, `I00_gain*` | — **gone** | no Femto amplifiers |
| `upd_bkg0..4`, `upd_bkgErr0..4` | same names, kept | dark currents, now in pA |
| `changes_*_ampGain`, `changes_*_mcsChan` | — **gone** | no gain-change bookkeeping |
| — | `ring_overflows`, `ring_overflows_I0` | **check these are 0** |
| — | `fx4_range`, `fx42_range` | FX4 `Range` labels, diagnostic |
| — | `upd_lurange`, `upd_autorange_channel` | sequence-program state |
| `n_points` | `n_points` | now from the FX4 time series |

### Reduction

```
I(q)  =  upd_current / I0_current
```

No gain term. No dwell-time term. The Struck accumulated counts, so
`mca2`/`mca3` had to be divided by `mca1`; `TSMeanValue` is already an average
over the interval and both electrometers share the same PSO gate, so the ratio
is valid point by point with no timing correction.

`channel_time` is a **diagnostic, not part of normalisation**. It is derived
as `N[i] = I0_total[i] / I0_current[i]`, `dt[i] = N[i] * sample_time`, and is
useful for spotting stage-tuning jitter and for `sigma_mean = sigma / sqrt(N)`.

**Non-zero `ring_overflows` invalidates the means** — the driver discarded the
oldest samples and every mean is biased toward the end of its interval.

---

## 3. SAXS frame — Pilatus

`ADconfigs/SAXS_config/attributes.xml` + `hdf5_plugin/layout.xml`.
New attributes land under `/entry/Metadata/`.

| old (commented out, no longer recorded) | new | notes |
|---|---|---|
| `I0_cts`, `I0_gain` | `I0_cts_gated`, `I0_current` | sum of samples; mean pA |
| `I00_cts`, `I00_gain` | `I00_current` | pA |
| `scaler_freq` | `FX4_SampleTime` | seconds per sample |
| — | `Exp_time_gated` | integration window, s |
| — | `I0_range` | FX4 range label |
| — | `FX4_RingOverflows` | check 0 |
| — | `/entry/counting_chain`, `/entry/config_version` | `"FX4"`, `"2.0"` |

`/entry/control/integral` is a hardlink to `I0_cts_gated`, so NXcanSAS readers
that use the monitor value keep working unchanged.

Relationship, verified on real frames:

```
I0_cts_gated  =  I0_current [pA]  x  Exp_time_gated [s]  /  FX4_SampleTime [s]
```

i.e. `I0_cts_gated` is a **sum of samples**; multiply by `FX4_SampleTime` to
get pA·s.

---

## 4. WAXS frame — Eiger

`ADconfigs/WAXS_config/attributes.xml` + `hdf5_plugin/layout_waxs.xml`.
Everything in §3 applies, plus the transmission diode:

| old | new | notes |
|---|---|---|
| `TR_cts`, `TR_gain` | `TR_current` | transmission diode, pA |
| — | `TR_cts_gated` | **see the warning below** |

> ### ⚠ `TR_cts_gated` is not what its name says
>
> Only I0 is gated to the exposure. `start_gated_I0` operates on `fx42`
> (I0 and I00); the transmission diode is on `fx4` and is never gated.
> `TR_cts_gated` is therefore the `Total_RBV` left over from whatever
> `fx4` last acquired — in practice the 0.05 s autoscale read that precedes
> the exposure, **not** the exposure itself.
>
> Measured on a 3 s WAXS frame: `TR_cts_gated / TR_current = 50.0` exactly,
> i.e. 50 samples = 0.05 s, not 3000 samples = 3 s.
>
> **Use `TR_current`** (pA, gain-independent) — that is the transmission
> measurement and it is correct. Treat `TR_cts_gated` as meaningless until
> the attribute is renamed or removed.

---

## 5. Step scan (uascan) — `<sample>_NNNN.h5`

Written by `callbacks/nxwriter_usaxs.py`. Arrays live in `/entry/data/`.

| old | new | notes |
|---|---|---|
| `UPD` | `UPD` | **same name, counts → pA** |
| `I0` | `I0` | **same name, counts → pA** |
| gain PVs in metadata | — | reading is gain-independent |

This is the format most likely to be mis-reduced: the array names did not
change, only their units and meaning. There is no `config_version` bump to
warn you. **Test `/entry/instrument/bluesky/metadata/counting_chain`.**

`/entry/data/` also carries a large number of `fx4_*` / `fx42_*` housekeeping
fields (sums, beam positions, scales, offsets). These are the electrometers'
own aggregate outputs, recorded because the whole device is read at every
point. They are not needed for reduction and can be ignored.

---

## 6. Quick checklist for a reduction routine

1. Branch on `counting_chain`, never on field names or `program_name@config_version`.
2. If `"FX4"`: values are pA. Do **not** divide by any gain.
3. Fly scan: do **not** divide by a dwell time either. Check
   `ring_overflows == 0` and `ring_overflows_I0 == 0`.
4. SAXS/WAXS: use `I0_cts_gated` for the monitor (or `/entry/control/integral`),
   `TR_current` for transmission. Ignore `TR_cts_gated`.
5. Absolute scale: `diode / I0` is a ratio, so an error common to both channels
   cancels in the curve *shape* and shows up only in the absolute level. Check
   against a standard reference material, not by eye.

---

## See also

* `PLAN.md` §1.4 — why there are four formats
* `PLAN.md` §2.1 — counts → current, and where the factor of 1e12 could hide
* `docs/FX4_Sunday_commissioning.md` — commissioning status and results
* `ADconfigs/README.md` — deploying these files to the IOCs
