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

### BUG-001 — Source / editable install fails: force-include of gitignored `.claude/skills`
- **Status:** FIXED (branch `fix/bug-001-skill-bundling`)
- **Severity:** high
- **Area:** `pyproject.toml`, `pepper_ios/mcp_prompts.py`, `pepper_ios/skills/`
- **Filed:** 2026-06-22
- **Symptom:** `pip install -e .` / `pipx install --editable .` on a fresh clone
  aborted with `FileNotFoundError: Forced include not found: <repo>/.claude/skills`.
- **Repro:** `git clone <fork> && pipx install --editable ./habanero`.
- **Expected:** a clean checkout installs from source without error.
- **Notes:** `.claude/` is gitignored (`.gitignore:39`), so `.claude/skills` was
  absent from any clone, yet `[tool.hatch.build.targets.wheel.force-include]` and
  the sdist force-include both pointed at it. Upstream only got away with it on
  the PyPI publish path where the dir exists locally. The prior workaround
  deleted both force-include tables, which un-broke install but left skill-prompts
  unbundled — and since `.claude/skills/` was never committed in this fork, the
  runtime fallback also resolved nothing, so `explore_app` / `babysit` prompts
  were unavailable.
- **Fix:** relocated skill sources into the tracked package tree at
  `pepper_ios/skills/explore-app/SKILL.md` and `pepper_ios/skills/babysit/SKILL.md`.
  Hatchling bundles them automatically via the existing `packages = ["pepper_ios"]`
  wheel inclusion (no `force-include` — pointing one at the same in-tree path
  collides with the default package inclusion and fails the build). `mcp_prompts.
  _read_skill` already resolves `pepper_ios/skills/<dir>/SKILL.md` via
  `importlib.resources`, so packaged prompts now load; the `.claude/skills` dev
  fallback is retained for upstream-layout parity. Added regression test
  `tools/tests/test_skill_bundling.py` (fails on the unbundled state, passes now).
  Verified: clean-clone `pipx install --editable` succeeds; a built wheel contains
  both SKILL.md files; `make py-test` green (150 passed).
