---
name: babysit
description: Proactive health monitoring, drift detection, and issue management for the Habanero project.
---

# Babysit

Proactively watch over the Habanero project: keep the toolchain healthy, catch
drift between the Python tool layer and the Swift dylib, and triage defects into
the bug log instead of fixing them inline.

This is a steady-state custodian loop, not a one-shot task. Each pass should
leave the repo in a known-good state or with a clearly filed issue.

## What to watch

1. **Build health.** `make build` compiles the dylib cleanly
   (`build/Pepper.framework/Pepper`). A broken build blocks everything else —
   surface it first.
2. **Test health.** `make py-test` (Python tool layer) and `make unit-test`
   (Swift Foundation-level) are green. `make lint-py` and `make typecheck` pass.
3. **Tool ↔ handler parity.** Every MCP tool has a matching dylib handler
   (`make check-tools`). A tool with no handler — or a handler with no tool — is
   drift; file it.
4. **Runtime sanity.** When a sim is injected, `habanero-ctl --port <PORT> ping`
   returns `pong` and `look` returns a coherent screen. `list-instances`
   auto-discovers live injected sims and their ports.
5. **Kill switch.** Respect `.pepper-kill`: if present, stand down — do not drive
   the app or mutate shared state.

## Procedure

1. **Check the gates** above in order. Stop at the first hard failure (build,
   then tests, then parity) and report it — do not pile changes on a red base.
2. **Detect drift.** Compare the tool surface against the dylib handlers and the
   generated coverage/command manifests. Note anything out of sync.
3. **Triage, don't fix.** When you find a defect while monitoring, append a
   self-contained entry to `BUGS.md` using the template there (next `BUG-NNN`
   id, every field filled) so a fix-agent can reproduce it without your context.
   Reserve inline fixes for the trivial and obviously safe.
4. **Report.** Summarize current health (green/red per gate), any drift, and any
   bugs filed this pass.

## Boundaries

- Do not touch `~/.pepper/` shared data.
- Do not commit directly to `main`; custodial fixes go on a `fix/<slug>` branch.
- Prefer filing a bug over a risky inline change — the bug log is the queue.
