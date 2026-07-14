# USAXS docs

Documentation for the USAXS / SAXS / WAXS Bluesky instrument at APS 12-ID-E.

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
