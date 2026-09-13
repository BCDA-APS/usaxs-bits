# Safety and escalation

This document is deliberately mostly blank. It covers judgment calls about
running a real X-ray beamline autonomously — only beamline staff can decide
these, not something derivable from the code. Sections below give the one
or two facts the code *does* establish, so staff filling this in aren't
starting from nothing.

## What already protects you automatically

- **Suspenders**: `suspend_FE_shutter` and `suspend_BeamInHutch` are wired
  onto `USAXSscan`, `saxsExp`, and `waxsExp` in `startup.py`. If the
  front-end shutter closes or the beam-in-hutch check fails mid-scan, the
  RunEngine pauses those three plans automatically and resumes when clear —
  AIda does not need to detect a beam drop and react during one of them.
  **Tuning, mode-change, and housekeeping plans are not suspender-protected**
  — see [02-plans-catalog.md](02-plans-catalog.md).
- **PSS shutters** (`FE_shutter`, `mono_shutter`) are a hardware/personnel
  safety interlock system, not a plan-level abstraction — they cannot be
  forced open by a plan bug, but a plan can find them unexpectedly closed
  (see the suspenders above).
- `usaxs.utils.obsidian` has `recordBeamDump`/`recordBeamRecovery` helpers
  used elsewhere in this codebase to log beam-loss events to the shared
  Obsidian notebook — worth knowing they exist if you need to find or
  cross-reference a beam-dump record, though the underlying policy for
  *when a human should be told* is not encoded there.

## <!-- PLACEHOLDER --> Actions AIda must never take autonomously

<!-- List specific plans, devices, or PV writes that require explicit human
     confirmation before AIda submits/executes them (e.g. opening a PSS
     shutter override, anything that moves a stage outside its normal
     tuned range, deleting/overwriting data). -->

## <!-- PLACEHOLDER --> When to pause and ask a human

<!-- Conditions under which AIda should stop and wait rather than retry or
     work around a problem itself — e.g. repeated tune failures, a suspender
     trip lasting longer than N minutes, an unrecognized error from the
     queue server, a sample-handling ambiguity. -->

## <!-- PLACEHOLDER --> Who to contact and how

<!-- Escalation path: who is on call, how to reach them (phone/Slack/other),
     and what information AIda should include when escalating. -->

## <!-- PLACEHOLDER --> Beam-dump / recovery behavior

<!-- What AIda should do to the running queue when a beam dump is detected
     (let the suspender pause it and wait? cancel the queue? something
     else?), and what "recovered" should mean before resuming unattended
     operation. -->

## <!-- PLACEHOLDER --> Abort/interrupt policy

<!-- Which in-flight plans are safe for AIda to abort on its own judgment
     vs. which must be allowed to finish or require a human to abort. Note
     from CLAUDE.md, relevant to whoever fills this in: `RE.abort()` and
     Ctrl-C do not run the plans' own after-run cleanup steps automatically
     — if that matters for your answer here, say what should run manually
     afterward. -->
