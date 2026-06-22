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

### BUG-003 — No dev-dependency spec: documented test/lint gates fail out-of-box
- **Status:** FIXED (branch `fix/bug-003-dev-deps`)
- **Severity:** low
- **Area:** `pyproject.toml`, `Makefile` (`typecheck`), `README.md`, `tools/tests/`
- **Filed:** 2026-06-22
- **Symptom:** a fresh contributor can't run the documented quality gates: `make
  py-test` → `No module named pytest`, `make lint-py` → `ruff: command not found`,
  `make typecheck` needs a Node toolchain for `npx pyright`. None of pytest/ruff/pyright
  were declared anywhere (`requirements.txt` is runtime-only).
- **Expected:** one documented step installs the dev toolchain so the Makefile gates run.
- **Fix:**
  - Added `[project.optional-dependencies] dev = ["pytest~=9.1.1", "ruff~=0.15.18",
    "pyright~=1.1.410"]` to `pyproject.toml`. Compatible-release (`~=`) pins keep the
    gates reproducible — notably ruff, whose minor bumps add lint rules.
  - Repointed `make typecheck` from `npx --yes pyright` to the pip-provided `pyright`
    (the wrapper vendors its own Node via `nodeenv`), so the single `pip install -e
    ".[dev]"` step provisions all three gates with no separate system-Node requirement,
    and the analyzer version is pinned. CI's `npx --yes pyright` step left unchanged
    (the CI runner already has Node) to keep the diff tight.
  - Documented the one-step setup in README `## Development` (`pip install -e ".[dev]"`
    → `make py-test` / `lint-py` / `typecheck`).
  - Added regression test `tools/tests/test_dev_dependencies.py` (red on the
    undeclared state; asserts the `dev` extras declare + version-pin the three tools).
- **Verified green:** fresh venv → `pip install -e ".[dev]"` (editable install + dev
  toolchain resolve: pytest 9.1.1 / ruff 0.15.18 / pyright 1.1.410) → `make py-test`
  152 passed (150 baseline + 2 new), `make lint-py` runs (3 pre-existing `pepper_format.py`
  E501 only — present on `main`, new test file clean), `make typecheck` 0 errors.

### BUG-004 — `release.yml` PyPI publish + dylib auto-download point at unavailable targets
- **Status:** FIXED (branch `fix/bug-004-source-only-dist`)
- **Severity:** low
- **Area:** `.github/workflows/release.yml`, `habanero/dylib_fetch.py` (removed),
  `habanero/__init__.py`, `habanero/mcp_build.py`, `README.md`, `scripts/release.sh`
- **Filed:** 2026-06-22
- **Symptom:** (a) the "Publish to PyPI" job twine-uploaded dist name `habanero`,
  already owned by the Crossref client on PyPI → 403 on a tag-push release. (b)
  `dylib_fetch.ensure_dylib()` auto-downloaded a prebuilt framework from
  `gokceonur/habanero` Releases that aren't published → 404 → build-from-source.
- **Resolution:** private fork → source-only distribution (approved by Onur:
  disable PyPI publish + remove the auto-download).
- **Fix:**
  - Removed the "Publish to PyPI" step from `release.yml`. The GitHub Release steps
    (private + public) still ship `Habanero.framework.zip` as artifacts; `PYPI_TOKEN`
    is now an unused secret. Updated the stale PyPI mentions in `scripts/release.sh`.
  - Deleted `habanero/dylib_fetch.py` and both call sites: `__init__._find_dylib`
    drops the path-4 auto-download (now resolves env-override → packaged `_dylib/` →
    `make build` output, else `""`); `mcp_build` returns a clear build-from-source
    error when the dylib is absent instead of attempting a 404-ing download.
  - Fixed the README Quickstart (`pip install habanero` pulled the wrong PyPI
    project) → clone + `pip install -e . && make build`; added Xcode to the
    requirements. Refreshed a stale `pepper-ios on PyPI` comment in `mcp_tools_system.py`.
  - Added regression test `tools/tests/test_no_prebuilt_distribution.py` (asserts no
    PyPI publish in `release.yml`, no `dylib_fetch.py`, no `ensure_dylib`/`dylib_fetch`
    references in the package).
- **Verified green:** `make build` ok; full `pytest tools/tests` 153 passed (150
  baseline + 3 new); ruff clean (3 pre-existing `pepper_format.py` E501 only);
  `import habanero` + `_find_dylib()` resolves the local build path; `make test-deploy`
  injected on iPhone 15 (E4B5752B, 26.5), `habanero-ctl --port 8869 ping` → `pong`,
  `look` → full screen dump.
