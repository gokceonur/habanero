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

### BUG-003 — No dev-dependency spec: documented test/lint gates fail out-of-box
- **Status:** OPEN
- **Severity:** low
- **Area:** `pyproject.toml` / `requirements.txt`, `Makefile` (`py-test`/`lint-py`/`check`), README
- **Filed:** 2026-06-22
- **Symptom:** a fresh contributor can't run the documented quality gates: `make
  py-test` → `No module named pytest`, `make lint-py` → `ruff: command not found`,
  `make typecheck` needs pyright. None of pytest/ruff/pyright are declared anywhere
  (`requirements.txt` is runtime-only: `mcp` / `textual` / `websockets`).
- **Repro:** clean clone → `make py-test` (or `make check`) without a manually
  pre-provisioned dev toolchain.
- **Expected:** one documented step installs the dev toolchain so the Makefile gates run.
- **Notes:** found while verifying BUG-001 (had to hand-provision a throwaway venv
  with pytest to run the suite). Fix: add `[project.optional-dependencies] dev =
  ["pytest", "ruff", "pyright"]` (or a `requirements-dev.txt`) and point the
  Makefile/README at it (`pip install -e ".[dev]"`). Pin versions for reproducibility.

### BUG-004 — `release.yml` PyPI publish + dylib auto-download point at unavailable targets
- **Status:** OPEN
- **Severity:** low
- **Area:** `.github/workflows/release.yml`, `habanero/dylib_fetch.py`
- **Filed:** 2026-06-22
- **Symptom:** (a) the "Publish to PyPI" job twine-uploads distribution name
  `habanero`, which is already an existing PyPI project (the Crossref API client),
  so a tag-push release would 403 on upload. (b) `dylib_fetch.ensure_dylib()` now
  resolves prebuilt frameworks from `gokceonur/habanero` GitHub Releases, which
  don't exist yet — auto-download 404s and falls back to "build from source".
- **Repro:** (a) push a version tag → release workflow PyPI step. (b) on a machine
  with no local `make build`, import a path that calls `ensure_dylib()`.
- **Expected:** a tagged release publishes cleanly and pip-only installs can fetch a
  prebuilt dylib.
- **Notes:** found during the BUG-002 rename. (a) rename the PyPI dist (e.g.
  `habanero-ios`) or drop/disable the PyPI publish step — this is a private fork, so
  local editable install may be all we need. (b) either cut a `gokceonur/habanero`
  Release shipping `Habanero.framework.zip`, or make build-from-source the only
  supported path and remove the download code. Local dev is unaffected today (the
  dev-build path resolves before any download).

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

### BUG-002 — Internal `pepper`/`Pepper` identifiers survive the rebrand (cosmetic + future-coupling)
- **Status:** FIXED (branch `fix/bug-002-deep-rename`)
- **Severity:** low
- **Area:** package dir, CLI `prog`/usage, `PEPPER_*` env contract, `Pepper.framework`,
  `~/.pepper/`, log subsystem, Bonjour service type, `dylib_fetch` repo.
- **Filed:** 2026-06-22
- **Symptom:** the command surface was renamed (`habanero-mcp`/`habanero-ctl`/MCP
  server `habanero`) but internals still said pepper: `habanero-ctl --help` printed
  `usage: pepper-ctl …`; import package `pepper_ios`; dylib `Pepper.framework`; env
  contract `PEPPER_*`; shared state `~/.pepper/`.
- **Expected:** a fully self-consistent `habanero` identity.
- **Fix (renamed surfaces):**
  - **Python package** `pepper_ios/` → `habanero/` (`git mv`, history preserved);
    fixed `importlib.resources.files("habanero")`, `pyproject` `packages` + entry
    points, ruff per-file globs, every external `pepper_ios` import (tools/, scripts/,
    .github/, tests). Internal `pepper_*.py` module **filenames kept** (intra-package
    imports are relative; renaming them is churn with no identity payoff).
  - **CLI** argparse `prog`/description/epilog in `ctl.py`, `test_runner.py`, the
    `FastMCP("habanero")` server name, module/log identity in `mcp_server.py`.
  - **Env contract — back-compat shim:** the Swift dylib now reads `HABANERO_<X>`
    first and falls back to legacy `PEPPER_<X>` via a single `habaneroEnv()` helper
    (all 6 runtime reads: ADAPTER/SKIP_PERMISSIONS/PORT/SIM_UDID/AUTO_DISMISS_DIALOGS/
    SAFE_MODE/OBSERVE_PORT). Every emit site emits **both** names (`Makefile`,
    `mcp_build.py`, `test_lifecycle.py`, `ci.sh`, `real-app-smoke.sh`, `inject-xcode-scheme.py`).
    Python reads `HABANERO_DYLIB_PATH`/`HABANERO_ROOT`/`HABANERO_DEBUG` with legacy
    fallback. Compilation-condition flags (`-DPEPPER_CONTROL`/`-DPEPPER`/`PEPPER_HAS_ADAPTER`)
    left unchanged (internal build flags, not the env contract).
  - **Framework** `Pepper.framework` → `Habanero.framework` (build-dylib.sh +
    build-xcframework.sh: output dir, `-module-name`, swiftmodule, bridging header,
    `-install_name @rpath/Habanero.framework/Habanero`, Info.plist
    CFBundleName/Executable/Identifier=`com.habanero.control`; Python `_find_dylib`,
    `pepper_common`, `dylib_fetch` FRAMEWORK_NAME + binary name; Makefile DYLIB_PATH;
    CI scripts; release.yml asset; embed-pepper.sh; the in-dylib `strstr(…,"Habanero.framework")`
    image filter). C entry symbol `PepperBootstrap` **kept** (internal dyld entry).
  - **Log subsystem** `com.pepper.control` → `com.habanero.control` (PepperAppConfig
    default + 2 direct `os_log_create` + console self-filter guard + Makefile `logs`
    predicate). DispatchQueue labels kept (debug-only, not log-filtered).
  - **Bonjour service type** `_pepper._tcp.` → `_habanero._tcp.` in lockstep
    (Swift advertiser + Python `dns-sd` browser + test-app `NSBonjourServices`).
  - **`dylib_fetch` GITHUB_REPO** `skwallace36/Pepper` → `gokceonur/habanero`;
    release.yml public repo + mcp-registry/smithery manifests repointed.
  - **`~/.pepper/` → `~/.habanero/` read-both** via `habanero_home_dir()` (adapters,
    scripts, tools, usage log, frameworks cache, chrome-profile): prefers
    `~/.habanero`, falls back to legacy `~/.pepper` **per-subpath** when present —
    never moves/deletes the populated legacy dir.
  - Docs (README/DYLIB.md/TOOLS.md/TROUBLESHOOTING.md/CLAUDE.md/babysit) rebranded.
- **Deliberately kept (internal, not identity-facing):** internal Swift type names
  (`PepperPlane`, `PepperLoader`, …), the `PepperBootstrap`/`_PepperAdapterShim`
  symbols, internal `pepper_*.py`/`pepper_keyWindow`/`pepperEquals` symbols,
  `/tmp/pepper-*` IPC paths, the `PepperTestApp` fixture (project/scheme/bundle
  `com.pepper.testapp`), `tools/pepper-*` dev wrapper filenames + `scripts/pepper-task`
  + `.pepper-kill`, host-orchestration vars (`PEPPER_AGENT_TYPE`/`PEPPER_MAX_SIMS`/
  `PEPPER_CONNECT`/…) read only by `scripts/`. Renaming these is churn with no
  identity payoff and (for the IPC/contract names) regression risk.
- **Verified green:** `make build` → `build/Habanero.framework/Habanero` (install_name
  `@rpath/Habanero.framework/Habanero`, module `Habanero`); `habanero-ctl --help`
  shows habanero (0 `pepper-ctl`); all 3 entry points + FastMCP `habanero`/33 tools;
  `make test-deploy` injected the test app on a booted iPhone 15 (26.5), `habanero-ctl
  --port 8869 ping` → `pong`, `look` → full screen dump; `pytest tools/tests` 150
  passed; `make unit-test` 148 passed. Pre-existing (not regression): 3 `E501` in
  `pepper_format.py` (also present on `main`; file unchanged here).
