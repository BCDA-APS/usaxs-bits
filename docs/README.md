# USAXS docs

Documentation for the USAXS / SAXS / WAXS Bluesky instrument at APS 12-ID-E.

## AIda orientation docs (`docs/aida/`)

Standalone reference material for the AIda agent, which operates the
instrument through the bluesky-queueserver MCP tools and has weak/no access
to this repo's source. See **[aida/README.md](aida/README.md)** for the
terminology glossary, plan catalog, device guide, and safety placeholders.

## FX4 electrometers (the counting chain since 2026-09)

UPD, I0, I00 and TRD read out through two Pyramid FX4 electrometers. Start with
the cheat sheet; the two issue documents are for discussion with the vendor and
the `quadEM` maintainer.

- **[FX4_config_cheatsheet.md](FX4_config_cheatsheet.md)** — the two operating
  configurations (fixed-time counting, PSO-gated fly scan) and the PVs for each.
- **[FX4_PSO_flyscan_setup.md](FX4_PSO_flyscan_setup.md)** — full explanation of
  the fly-scan mode, PV table, hardware facts.
- **[FX4_data_formats.md](FX4_data_formats.md)** — what the FX4 chain writes
  into each of the four file formats, and how it maps onto the old Struck fields.
- **⭐ [FX4_PSO_trigger_issue_2.md](FX4_PSO_trigger_issue_2.md)** — **current**
  open issue: the gate input only registers PSO strobes ≥ ~1 ms, and this does
  *not* scale with `ValuesPerRead`. Root cause located (the gate is a GPIO
  register in a separate device subsystem, polled at ~1 kHz); carries the
  questions for Pyramid and for the `quadEM`/`drvFX4` maintainer, and the
  remedies. Self-contained.
- [FX4_PSO_trigger_issue.md](FX4_PSO_trigger_issue.md) — **superseded.** The
  original 2026-09-27 measurement, still valid and quoted by its successor; its
  stated root cause is not.
- **[FX4_Sunday_commissioning.md](FX4_Sunday_commissioning.md)** — the
  stage-by-stage commissioning runbook and its results table.

Conversion status and remaining work: `../PLAN.md`.

## Queue-monitor GUI (`usaxs-qmonitor`)

The custom queue-monitor GUI built on bluesky-widgets + bluesky-queueserver.

- **[usaxs-qmonitor-user-guide.md](usaxs-qmonitor-user-guide.md)** — what it is,
  how to install and launch it, and how each feature works (queue control,
  New User / New Sample, loading plan files, live plots, terminal).
- **[usaxs-qmonitor-testing-checklist.md](usaxs-qmonitor-testing-checklist.md)** —
  step-by-step checklist of what to verify **at the beamline** (the parts that
  could not be tested off-site), plus the local demo test.

Design/decision background lives at the repo root:
`../USAXS-GUI-PLAN.md` (architecture + decisions) and
`../USAXS-GUI-IMPLEMENTATION.md` (build plan + phase notes).
