"""Regression tests for app_eval module/search-path resolution (BUG-006, BUG-007).

Both bugs lived in ``habanero/mcp_eval_compiler.py`` — the path that lets a compiled
eval ``@testable import`` the running app's own Swift module and resolve its
transitive dependencies.

BUG-007: the products resolver hardcoded ``Build/Products/Debug-iphonesimulator``, so
an app built under any other configuration (e.g. the Shift "Shift Dev" scheme →
``Dev`` config → ``Dev-iphonesimulator``) was invisible. These tests pin that every
``*-iphonesimulator`` product dir is discovered while device (``*-iphoneos``) and
unsuffixed config dirs stay excluded.

BUG-006: ``_xcframework_sim_search_paths`` added every xcframework slice whose name
contained "simulator" (grabbing tvOS/watchOS slices) and added framework ``-F`` for
mutually-exclusive xcframework variants the app never links. For a Sentry-linked app
that surfaced ``SentryWithoutUIKit``, whose headers import back into ``Sentry`` — a
cyclic Clang module that aborts the compile. These tests pin the iOS-slice filter,
the "skip variants once a package framework is in products" rule, and the generated
Clang-module-graph helpers (``_generated_modulemaps`` / ``_umbrella_include_dirs``).
"""

from __future__ import annotations

import os

from habanero import mcp_eval_compiler as ec


def _mk(*parts: str) -> str:
    """Create a directory tree and return its leaf path."""
    path = os.path.join(*parts)
    os.makedirs(path, exist_ok=True)
    return path


def _touch(*parts: str, content: str = "") -> str:
    """Create a file (and its parent dirs) and return its path."""
    path = os.path.join(*parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)
    return path


def test_sim_products_dirs_globs_all_simulator_configs(tmp_path) -> None:
    """Every ``<Config>-iphonesimulator`` dir is returned; device + unsuffixed
    configs are excluded."""
    base = str(tmp_path)
    debug_sim = _mk(base, "Build", "Products", "Debug-iphonesimulator")
    dev_sim = _mk(base, "Build", "Products", "Dev-iphonesimulator")
    _mk(base, "Build", "Products", "Dev-iphoneos")  # device slice — excluded
    _mk(base, "Build", "Products", "Release")  # no sdk suffix — excluded

    found = set(ec._sim_products_dirs(base))

    assert found == {debug_sim, dev_sim}


def test_find_all_products_dirs_picks_up_non_debug_config(tmp_path) -> None:
    """The Dev-iphonesimulator build (BUG-007's repro) is discovered under the
    standard DerivedData/<Project-hash>/Build/Products layout."""
    dd_root = str(tmp_path)
    project = _mk(dd_root, "MyApp-abc123")
    dev_sim = _mk(project, "Build", "Products", "Dev-iphonesimulator")
    debug_sim = _mk(project, "Build", "Products", "Debug-iphonesimulator")

    found = set(ec._find_all_products_dirs(dd_root))

    assert dev_sim in found, "non-Debug config dir must be discovered (BUG-007)"
    assert debug_sim in found


def test_find_all_products_dirs_worktree_isolated_layout(tmp_path) -> None:
    """A worktree-isolated DerivedData holds Build/Products directly at its root."""
    dd_root = str(tmp_path)
    dev_sim = _mk(dd_root, "Build", "Products", "Dev-iphonesimulator")

    assert dev_sim in ec._find_all_products_dirs(dd_root)


def test_find_app_module_resolves_non_debug_config(tmp_path, monkeypatch) -> None:
    """End to end: a scheme whose only build is a non-Debug config still resolves
    to its module name + products dir (would return None before BUG-007's fix)."""
    dd_root = str(tmp_path)
    scheme = "PytestEvalApp"
    dev_sim = _mk(dd_root, f"{scheme}-hash", "Build", "Products", "Dev-iphonesimulator")
    _mk(dev_sim, f"{scheme}.swiftmodule")

    # Point the resolver's default-DerivedData search at our hermetic tree.
    monkeypatch.setattr(os.path, "expanduser", lambda p: dd_root if "DerivedData" in p else p)

    module_dir, binary_dir, module_name = ec._find_app_module(None, scheme)

    assert module_name == scheme
    assert module_dir == dev_sim


# ---- BUG-006: xcframework slice selection + Clang module-graph helpers ----


def _products_dir(dd_root: str, config: str = "Debug") -> str:
    return _mk(dd_root, "Build", "Products", f"{config}-iphonesimulator")


def _xcframework_slice(
    dd_root: str, pkg: str, variant: str, slice_name: str,
    *, framework: str | None = None, headers: bool = False,
) -> str:
    """Create one SourcePackages/artifacts xcframework slice; return its path."""
    slice_dir = _mk(
        dd_root, "SourcePackages", "artifacts", pkg, variant,
        f"{variant}.xcframework", slice_name,
    )
    if framework:
        _mk(slice_dir, f"{framework}.framework")
    if headers:
        _touch(slice_dir, "Headers", "module.modulemap", content="module X {}")
    return slice_dir


def test_xcframework_search_paths_takes_ios_sim_slice_only(tmp_path) -> None:
    """Only ``ios-*-simulator`` slices are taken; tvos/watchos/xros are excluded
    (the old "name contains simulator" match grabbed Sentry's tvOS slice)."""
    dd = str(tmp_path)
    products = _products_dir(dd)
    ios = _xcframework_slice(dd, "apollo", "Apollo", "ios-arm64_x86_64-simulator", framework="Apollo")
    _xcframework_slice(dd, "apollo", "Apollo", "tvos-arm64_x86_64-simulator", framework="Apollo")
    _xcframework_slice(dd, "apollo", "Apollo", "watchos-arm64_x86_64-simulator", framework="Apollo")

    frame_paths = [f for f, _ in ec._xcframework_sim_search_paths(products) if f]

    assert frame_paths == [ios]


def test_xcframework_search_paths_skips_variant_when_package_framework_in_products(tmp_path) -> None:
    """BUG-006 core: once Xcode copies one of a package's frameworks into products,
    none of that package's variant framework slices are added — so an unused variant
    like ``SentryWithoutUIKit`` never becomes visible to trigger the cyclic module."""
    dd = str(tmp_path)
    products = _products_dir(dd, config="Dev")
    _mk(products, "Sentry.framework")  # Xcode copied the linked Sentry-Dynamic here
    _xcframework_slice(dd, "sentry-cocoa", "Sentry-Dynamic",
                       "ios-arm64_x86_64-simulator", framework="Sentry")
    without = _xcframework_slice(dd, "sentry-cocoa", "Sentry-WithoutUIKitOrAppKit",
                                 "ios-arm64_x86_64-simulator", framework="SentryWithoutUIKit")

    frame_paths = [f for f, _ in ec._xcframework_sim_search_paths(products) if f]

    assert frame_paths == []
    assert without not in frame_paths  # the cyclic variant is not exposed


def test_xcframework_search_paths_keeps_standalone_binary_framework(tmp_path) -> None:
    """A package with no framework in products (a genuine standalone binary
    xcframework, e.g. Apollo) still contributes its ios-sim framework ``-F``."""
    dd = str(tmp_path)
    products = _products_dir(dd)  # empty — Xcode copied nothing
    ios = _xcframework_slice(dd, "apollo-ios", "Apollo",
                             "ios-arm64_x86_64-simulator", framework="Apollo")

    frame_paths = [f for f, _ in ec._xcframework_sim_search_paths(products) if f]

    assert frame_paths == [ios]


def test_xcframework_search_paths_keeps_bare_header_slice(tmp_path) -> None:
    """A bare-headers slice (``Headers/`` but no ``.framework``) is returned as an
    ``-I``, independent of the variant-skip rule."""
    dd = str(tmp_path)
    products = _products_dir(dd)
    slice_dir = _xcframework_slice(dd, "somelib", "SomeLib",
                                   "ios-arm64_x86_64-simulator", headers=True)

    include_paths = [i for _, i in ec._xcframework_sim_search_paths(products) if i]

    assert include_paths == [os.path.join(slice_dir, "Headers")]


def test_xcframework_search_paths_empty_without_artifacts(tmp_path) -> None:
    """No ``SourcePackages/artifacts`` (e.g. PepperTestApp) → no extra search paths."""
    products = _products_dir(str(tmp_path))
    assert ec._xcframework_sim_search_paths(products) == []


def _gmm_dir(dd_root: str) -> str:
    return _mk(dd_root, "Build", "Intermediates.noindex", "GeneratedModuleMaps-iphonesimulator")


def test_generated_modulemaps_globs_modulemaps(tmp_path) -> None:
    """Every ``*.modulemap`` under GeneratedModuleMaps is returned; other files aren't."""
    dd = str(tmp_path)
    products = _products_dir(dd)
    gmm = _gmm_dir(dd)
    foo = _touch(gmm, "FirebaseCore.modulemap", content="module FirebaseCore {}")
    bar = _touch(gmm, "GoogleUtilities-NSData.modulemap", content="module X {}")
    _touch(gmm, "notamodulemap.txt", content="ignore me")

    assert ec._generated_modulemaps(products) == sorted([foo, bar])


def test_generated_modulemaps_empty_when_absent(tmp_path) -> None:
    """An app with no generated modulemaps (PepperTestApp) yields an empty list."""
    products = _products_dir(str(tmp_path))
    assert ec._generated_modulemaps(products) == []


def test_umbrella_include_dirs_derives_public_header_roots(tmp_path) -> None:
    """For ``umbrella header .../<Pkg>/Public/<Pkg>/<Pkg>.h`` the include roots are
    the header's dir and its parent (so ``#import <Pkg/Other.h>`` resolves)."""
    dd = str(tmp_path)
    products = _products_dir(dd)
    gmm = _gmm_dir(dd)
    pub = _mk(dd, "SourcePackages", "checkouts", "pkg", "Sources", "Public", "Pkg")
    umbrella = _touch(pub, "Pkg.h")
    _touch(gmm, "Pkg.modulemap",
           content=f'module Pkg {{\n  umbrella header "{umbrella}"\n  export *\n}}\n')

    roots = ec._umbrella_include_dirs(products)

    assert pub in roots                   # dir holding the umbrella header
    assert os.path.dirname(pub) in roots  # its parent — the public-header root


def test_umbrella_include_dirs_skips_nonexistent_dirs(tmp_path) -> None:
    """Derived include roots that don't exist on disk are filtered out."""
    dd = str(tmp_path)
    products = _products_dir(dd)
    gmm = _gmm_dir(dd)
    _touch(gmm, "Ghost.modulemap",
           content='module Ghost {\n  umbrella header "/nope/Ghost/Ghost.h"\n}\n')

    assert ec._umbrella_include_dirs(products) == []


# ---- BUG-006: compile_eval best-effort fallback (drops the app import on failure) ----


def _fake_sdk():
    return ("/sdk", "arm64-apple-ios18.0-simulator", "arm64")


def _stub_run(returncode: int, *, make_dylib: bool):
    """Build a subprocess.run stub that reports *returncode* and optionally writes
    the requested ``-o`` dylib."""

    class _Result:
        pass

    def run(cmd, capture_output, text, timeout):
        r = _Result()
        r.returncode = returncode
        r.stderr = "" if returncode == 0 else "cyclic dependency in module 'Sentry'"
        r.stdout = ""
        if make_dylib:
            with open(cmd[cmd.index("-o") + 1], "w") as fh:
                fh.write("dylib")
        return r

    return run


def test_compile_eval_falls_back_without_app_import(monkeypatch) -> None:
    """When the ``@testable import`` compile fails, compile_eval retries without the
    app import so generic evals still run instead of hard-failing (BUG-006)."""
    monkeypatch.setattr(ec, "_detect_sdk", _fake_sdk)
    monkeypatch.setattr(ec, "_find_app_module",
                        lambda b, s: ("/fake/products", "/fake/products", "FakeApp"))

    saw_app_import: list[bool] = []

    def run(cmd, capture_output, text, timeout):
        with open(cmd[-1]) as f:
            has_import = "@testable import FakeApp" in f.read()
        saw_app_import.append(has_import)
        # fail the with-import attempt; succeed (and emit the dylib) without it
        return _stub_run(1 if has_import else 0, make_dylib=not has_import)(
            cmd, capture_output, text, timeout)

    monkeypatch.setattr(ec.subprocess, "run", run)

    ok, path, info = ec.compile_eval(code="1+1", mode="expr", bundle_id="x", scheme="FakeApp")

    assert ok is True
    assert saw_app_import == [True, False]  # with-import first, then the fallback
    assert info is not None and "WITHOUT `@testable import FakeApp`" in info


def test_compile_eval_no_fallback_when_app_import_succeeds(monkeypatch) -> None:
    """A clean app-import compile happens exactly once — the fallback is failure-only."""
    monkeypatch.setattr(ec, "_detect_sdk", _fake_sdk)
    monkeypatch.setattr(ec, "_find_app_module",
                        lambda b, s: ("/fake/products", "/fake/products", "FakeApp"))

    runs: list[str] = []

    def run(cmd, capture_output, text, timeout):
        runs.append(cmd[-1])
        return _stub_run(0, make_dylib=True)(cmd, capture_output, text, timeout)

    monkeypatch.setattr(ec.subprocess, "run", run)

    ok, path, info = ec.compile_eval(code="1+1", mode="expr", bundle_id="x", scheme="FakeApp")

    assert ok is True
    assert len(runs) == 1
    assert info is not None and "WITHOUT" not in info
