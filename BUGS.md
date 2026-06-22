# Habanero — Bug Log

Habanero is our fork of [skwallace36/Pepper](https://github.com/skwallace36/Pepper):
an iOS-simulator dylib-injection MCP that gives agents eyes and hands inside a
running app.

This file is the **working bug queue** for the fork. When an agent notices a
defect while *using* the Habanero MCP tools (or building/installing it), it
appends an entry here instead of fixing it inline. A separate fix-agent then
picks entries off the top, fixes them on a `fix/<slug>` branch, and flips the
status to `FIXED` (with the commit/PR).

## How to file a bug

Copy the template, give it the next `BUG-NNN` id, fill every field. Keep it
self-contained: a fix-agent should be able to reproduce and fix from the entry
alone, without the original session's context.

```
### BUG-NNN — <one-line title>
- **Status:** OPEN | IN-PROGRESS | FIXED | WONTFIX
- **Severity:** blocker | high | medium | low
- **Area:** <mcp tool name(s) / file(s) — e.g. `look`, `pepper_ios/mcp_build.py`, dylib>
- **Filed:** YYYY-MM-DD
- **Symptom:** what went wrong (observed behavior).
- **Repro:** exact steps / command to trigger it.
- **Expected:** what should happen instead.
- **Notes:** root-cause hypothesis, relevant code refs, workaround in place (if any).
```

---

## Open

### BUG-001 — Source / editable install fails: force-include of gitignored `.claude/skills`
- **Status:** WORKED-AROUND (proper fix pending)
- **Severity:** high
- **Area:** `pyproject.toml`, `pepper_ios/mcp_prompts.py`
- **Filed:** 2026-06-22
- **Symptom:** `pip install -e .` / `pipx install --editable .` on a fresh clone
  aborts with `FileNotFoundError: Forced include not found: <repo>/.claude/skills`.
- **Repro:** `git clone <fork> && pipx install --editable ./habanero`.
- **Expected:** a clean checkout installs from source without error.
- **Notes:** `.claude/` is gitignored (`.gitignore:39`), so `.claude/skills` is
  absent from any clone, yet `[tool.hatch.build.targets.wheel.force-include]` and
  the sdist force-include both point at it. Upstream only gets away with it on
  the PyPI publish path where the dir exists locally. **Workaround applied:** both
  force-include tables removed from `pyproject.toml`. Consequence: skill-prompts
  are no longer bundled into a built wheel — `mcp_prompts.py` still falls back to
  `<repo>/.claude/skills` at runtime, but that path is also gitignored, so
  skill-prompts are effectively unavailable in this fork until fixed.
  **Proper fix:** relocate skill sources into the tracked tree (e.g. an in-repo
  `pepper_ios/skills/` that is committed) and bundle from there, OR un-gitignore
  just `.claude/skills/`. Then restore the (now build-safe) force-include.

### BUG-002 — Internal `pepper`/`Pepper` identifiers survive the rebrand (cosmetic + future-coupling)
- **Status:** OPEN
- **Severity:** low
- **Area:** `pepper_ios/` package dir, CLI `prog`/description strings, `PEPPER_*`
  env vars, `Pepper.framework` dylib name, `~/.pepper/` config dir.
- **Filed:** 2026-06-22
- **Symptom:** the command surface is renamed (`habanero-mcp` / `habanero-ctl` /
  MCP server `habanero`), but internals still say pepper: `habanero-ctl --help`
  prints `usage: pepper-ctl …`; the import package is `pepper_ios`; the dylib is
  `Pepper.framework`; env contract is `PEPPER_PORT` / `PEPPER_SIM_UDID` /
  `PEPPER_ADAPTER` / `PEPPER_DYLIB_PATH`; shared state lives in `~/.pepper/`.
- **Repro:** `habanero-ctl --help` (see `pepper-ctl` in usage).
- **Expected:** a fully self-consistent `habanero` identity.
- **Notes:** intentionally deferred — the `PEPPER_*` env vars + `Pepper.framework`
  name are a **contract shared between the Python side and the Swift dylib**;
  renaming them requires changing both sides in lockstep (loader, `mcp_build.py`,
  `Makefile`, `tools/build-dylib.sh`, every `dylib/**` reader). Do this as one
  atomic "deep rename" change, not piecemeal. Low-risk subset that can land first:
  argparse `prog=`/description strings + user-facing log text.

## Fixed

_(none yet)_
