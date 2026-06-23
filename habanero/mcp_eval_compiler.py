"""Compile Swift source into a dylib for injection into a running simulator app.

Handles SDK detection, app module resolution, and swiftc invocation.
Each compilation produces a uniquely-named dylib to avoid dlopen caching."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import tempfile
import time

# Persistent temp dir for eval artifacts
EVAL_DIR = os.path.join(tempfile.gettempdir(), "pepper-eval")

# PepperEvalSDK.swift — compiled alongside eval code for Pepper.* API access
_REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SDK_PATH = os.path.join(_REPO_DIR, "dylib", "eval", "PepperEvalSDK.swift")
os.makedirs(EVAL_DIR, exist_ok=True)

# swiftc timeout. The first eval against a large app cold-builds its whole Clang
# module cache (Firebase, Sentry, …), which runs well past the trivial-case ~2s.
_COMPILE_TIMEOUT = 120

# REPL wrapper template — user writes an expression, we wrap it
REPL_TEMPLATE = """\
import Foundation
import UIKit
import SwiftUI
{app_import}

// Retain the last result string so its pointer stays valid after return.
private var __pepperLastResult: UnsafeMutablePointer<CChar>?

@_cdecl("pepper_eval")
public func pepperEval() -> UnsafePointer<CChar> {{
    // Free previous result
    __pepperLastResult.map {{ free($0) }}
    let __result: Any = {{
        {code}
    }}()
    let __str = String(describing: __result)
    __pepperLastResult = strdup(__str)
    return UnsafePointer(__pepperLastResult!)
}}
"""

# Full mode template — user writes complete function body
FULL_TEMPLATE = """\
import Foundation
import UIKit
import SwiftUI
{app_import}

@_cdecl("pepper_eval")
public func pepperEval() -> UnsafePointer<CChar> {{
{code}
}}
"""


def _detect_sdk() -> tuple[str, str, str]:
    """Detect simulator SDK path, target triple, and architecture."""
    arch = subprocess.check_output(["uname", "-m"]).decode().strip()
    sdk_name = "iphonesimulator"
    sdk_path = subprocess.check_output(
        ["xcrun", "--sdk", sdk_name, "--show-sdk-path"]
    ).decode().strip()
    sdk_ver = subprocess.check_output(
        ["xcrun", "--sdk", sdk_name, "--show-sdk-version"]
    ).decode().strip()
    ios_ver = sdk_ver.split(".")[0] + ".0"

    target = f"arm64-apple-ios{ios_ver}-simulator" if arch == "arm64" else f"x86_64-apple-ios{ios_ver}-simulator"

    return sdk_path, target, arch


def _find_app_module(bundle_id: str | None, scheme: str | None) -> tuple[str | None, str | None, str | None]:
    """Find the app's .swiftmodule and binary from DerivedData.

    Scans every DerivedData-* worktree in /tmp plus the default Xcode
    DerivedData, collects all products dirs that contain a matching
    .swiftmodule, and picks the most recently modified. This matters when
    multiple worktrees have built the same scheme — the first match isn't
    necessarily the build the user is currently running, and picking a
    stale/partial DerivedData can yield empty dependency frameworks (e.g.
    Lottie.framework with no .swiftinterface, causing 'missing required
    module' errors).

    Returns (module_dir, binary_dir, module_name) or (None, None, None) if
    not found.
    """
    if not scheme and not bundle_id:
        return None, None, None

    # Collect every DerivedData root, then every products dir under them.
    search_dirs: list[str] = []
    try:
        for entry in os.scandir("/tmp"):
            if entry.name.startswith("DerivedData-") and entry.is_dir():
                search_dirs.append(entry.path)
    except OSError:
        pass

    default_dd = os.path.expanduser("~/Library/Developer/Xcode/DerivedData")
    if os.path.isdir(default_dd):
        search_dirs.append(default_dd)

    # For each products dir, look for a matching .swiftmodule and record its
    # mtime. Pick the newest.
    candidates: list[tuple[float, str, str]] = []  # (mtime, products_dir, module_name)
    for dd_root in search_dirs:
        for products_dir in _find_all_products_dirs(dd_root):
            if scheme:
                sm = os.path.join(products_dir, f"{scheme}.swiftmodule")
                if os.path.isdir(sm):
                    try:
                        candidates.append((os.path.getmtime(sm), products_dir, scheme))
                        continue
                    except OSError:
                        pass
            try:
                for entry in os.scandir(products_dir):
                    if entry.name.endswith(".swiftmodule") and entry.is_dir():
                        mod_name = entry.name.removesuffix(".swiftmodule")
                        if not scheme or mod_name == scheme:
                            try:
                                candidates.append((entry.stat().st_mtime, products_dir, mod_name))
                            except OSError:
                                pass
            except OSError:
                continue

    if not candidates:
        return None, None, None

    candidates.sort(reverse=True)  # newest first
    _, products_dir, mod_name = candidates[0]
    return products_dir, products_dir, mod_name


def _dd_root(products_dir: str) -> str:
    """DerivedData root for a products dir (.../Build/Products/<config> → up × 3)."""
    return os.path.abspath(os.path.join(products_dir, "..", "..", ".."))


def _product_framework_names(products_dir: str) -> set[str]:
    """Names (sans `.framework`) of every framework Xcode copied into products."""
    try:
        return {
            e.name.removesuffix(".framework")
            for e in os.scandir(products_dir)
            if e.is_dir() and e.name.endswith(".framework")
        }
    except OSError:
        return set()


def _ios_sim_slices(pkg_dir: str) -> list[tuple[str, list[str], str | None]]:
    """iOS-simulator xcframework slices under one SourcePackages/artifacts/<pkg>.

    Returns (slice_path, framework_names, headers_dir_or_None) per slice. Only
    `ios-*-simulator` slices are taken — matching any name containing "simulator"
    grabbed tvos-/watchos-/xros- slices (e.g. Sentry's tvOS SentryWithoutUIKit).
    """
    out: list[tuple[str, list[str], str | None]] = []
    try:
        name_entries = list(os.scandir(pkg_dir))
    except OSError:
        return out
    for name_entry in name_entries:
        if not name_entry.is_dir():
            continue
        try:
            xcf_entries = list(os.scandir(name_entry.path))
        except OSError:
            continue
        for xcf_entry in xcf_entries:
            if not xcf_entry.is_dir() or not xcf_entry.name.endswith(".xcframework"):
                continue
            try:
                slice_entries = list(os.scandir(xcf_entry.path))
            except OSError:
                continue
            for s in slice_entries:
                if not s.is_dir() or not (s.name.startswith("ios-") and s.name.endswith("-simulator")):
                    continue
                try:
                    fw_names = [
                        e.name.removesuffix(".framework")
                        for e in os.scandir(s.path)
                        if e.is_dir() and e.name.endswith(".framework")
                    ]
                except OSError:
                    fw_names = []
                headers = os.path.join(s.path, "Headers")
                out.append((s.path, fw_names, headers if os.path.isdir(headers) else None))
    return out


def _xcframework_sim_search_paths(products_dir: str) -> list[tuple[str | None, str | None]]:
    """Return (framework_search_path, header_search_path) tuples for the
    iOS-simulator slice of every xcframework under SourcePackages/artifacts.

    Handles both layouts:
    - Framework slice: <slice>/Foo.framework → add <slice> as -F
    - Bare-headers slice: <slice>/Headers/module.modulemap → add <slice>/Headers as -I

    Skips a package's framework slices once Xcode has copied one of that package's
    frameworks into Build/Products (already on -F). A package such as sentry-cocoa
    ships several mutually exclusive xcframework variants (Sentry-Dynamic,
    Sentry-WithoutUIKitOrAppKit, …); the app links exactly one. Exposing the others
    surfaces modules the app never links — and Sentry's headers guard a
    `#if __has_include(<SentryWithoutUIKit/…>)` block that, once the variant is
    visible, imports back into Sentry: a cyclic module that aborts the compile
    (BUG-006). Bare-header slices are always kept.

    products_dir is .../Build/Products/<Config>-iphonesimulator; SourcePackages
    is a sibling of Build.
    """
    results: list[tuple[str | None, str | None]] = []
    artifacts = os.path.join(_dd_root(products_dir), "SourcePackages", "artifacts")
    if not os.path.isdir(artifacts):
        return results
    product_frameworks = _product_framework_names(products_dir)
    try:
        pkg_entries = list(os.scandir(artifacts))
    except OSError:
        return results
    for pkg_entry in pkg_entries:
        if not pkg_entry.is_dir():
            continue
        slices = _ios_sim_slices(pkg_entry.path)
        # Did Xcode already resolve this package by copying a framework to products?
        package_in_products = any(
            fw in product_frameworks for _, fw_names, _ in slices for fw in fw_names
        )
        for slice_path, fw_names, headers in slices:
            frame_path = slice_path if (fw_names and not package_in_products) else None
            if frame_path or headers:
                results.append((frame_path, headers))
    return results


def _generated_modulemaps(products_dir: str) -> list[str]:
    """Clang modulemaps Xcode generated for the app's SwiftPM Clang targets.

    Live at <DD>/Build/Intermediates.noindex/GeneratedModuleMaps-iphonesimulator/.
    A standalone `@testable import` of an app that links SwiftPM Clang modules
    (Firebase, GoogleUtilities, …) fails with `missing required module 'X'` unless
    each generated modulemap is handed to Clang via -fmodule-map-file. Returns the
    modulemap paths; empty when the app has none (e.g. PepperTestApp).
    """
    gmm = os.path.join(
        _dd_root(products_dir),
        "Build", "Intermediates.noindex", "GeneratedModuleMaps-iphonesimulator",
    )
    try:
        return sorted(e.path for e in os.scandir(gmm) if e.name.endswith(".modulemap"))
    except OSError:
        return []


def _umbrella_include_dirs(products_dir: str) -> list[str]:
    """Header search roots derived from each generated modulemap's umbrella.

    A generated modulemap names an absolute umbrella header, e.g.
    .../firebase-ios-sdk/FirebaseCore/Sources/Public/FirebaseCore/FirebaseCore.h.
    The umbrella then `#import <FirebaseCore/FIRApp.h>`, which resolves only with
    the public-header root (.../Public) on Clang's search path. Returns the
    umbrella's dir and its parent for each modulemap, deduped. Empty when none.
    """
    roots: set[str] = set()
    for mm in _generated_modulemaps(products_dir):
        try:
            with open(mm) as f:
                text = f.read()
        except OSError:
            continue
        for m in re.finditer(r'umbrella(?:\s+header)?\s+"([^"]+)"', text):
            d = os.path.dirname(m.group(1))
            roots.add(d)
            roots.add(os.path.dirname(d))
    return sorted(p for p in roots if p and os.path.isdir(p))


def _sim_products_dirs(base: str) -> list[str]:
    """Return every Build/Products/*-iphonesimulator dir directly under *base*.

    Globs all simulator product dirs, not just Debug-iphonesimulator: a scheme
    can map to any build configuration, so the built .swiftmodule lands in
    <Config>-iphonesimulator (e.g. the Shift "Shift Dev" scheme → "Dev" config
    → Dev-iphonesimulator). Hardcoding the Debug- prefix missed those builds
    entirely (BUG-007).
    """
    products = os.path.join(base, "Build", "Products")
    found = []
    try:
        for entry in os.scandir(products):
            if entry.is_dir() and entry.name.endswith("-iphonesimulator"):
                found.append(entry.path)
    except OSError:
        pass
    return found


def _find_all_products_dirs(dd_root: str) -> list[str]:
    """Find all Build/Products/*-iphonesimulator dirs under a DerivedData root."""
    results = []
    # dd_root itself may hold Build/Products (worktree-isolated DerivedData)
    results.extend(_sim_products_dirs(dd_root))
    # DerivedData structure: DerivedData/ProjectName-hash/Build/Products/<Config>-iphonesimulator/
    try:
        for entry in os.scandir(dd_root):
            if entry.is_dir():
                results.extend(_sim_products_dirs(entry.path))
    except OSError:
        pass
    return results


def _swiftc_cmd(
    source_path: str,
    dylib_path: str,
    sdk_path: str,
    target: str,
    module_dir: str | None,
) -> list[str]:
    """Assemble the swiftc invocation that compiles an eval source into a dylib.

    With module_dir set, adds the search paths and Clang module-graph flags that
    let the source `@testable import` the app module and resolve its transitive
    SwiftPM/xcframework dependencies. Pass module_dir=None to compile without the
    app import (the fallback path).
    """
    cmd = [
        "xcrun", "-sdk", "iphonesimulator", "swiftc",
        "-target", target,
        "-sdk", sdk_path,
        "-emit-library",
        "-o", dylib_path,
        "-Onone",
        "-enable-testing",
        "-framework", "UIKit",
        "-framework", "Foundation",
        "-framework", "SwiftUI",
    ]

    # Allow unresolved symbols — they'll resolve at dlopen time from the host process
    cmd.extend(["-Xlinker", "-undefined", "-Xlinker", "dynamic_lookup"])

    # Resolve the app module and its transitive dependency graph. `@testable import`
    # of the app pulls in everything it links, which swiftc must resolve or the
    # compile fails ("missing required module 'X'"). SPM ships deps in several
    # layouts, so fan out:
    #   -I/-F <products>                standalone .swiftmodule + framework products
    #   -F <products>/PackageFrameworks SPM-built framework products
    #   -F <slice> / -I <slice>/Headers xcframework iOS-sim slices
    #   -Xcc -fmodule-map-file=<map>    Xcode-generated Clang modulemaps (Firebase, …)
    #   -Xcc -I<root>                   public-header roots those modulemaps include
    # The last two reconstruct the explicit Clang-module graph Xcode builds; without
    # them an app linking SwiftPM Clang modules fails to compile standalone (BUG-006).
    if module_dir:
        cmd.extend(["-I", module_dir, "-F", module_dir])
        package_fw = os.path.join(module_dir, "PackageFrameworks")
        if os.path.isdir(package_fw):
            cmd.extend(["-F", package_fw])
        for frame_path, include_path in _xcframework_sim_search_paths(module_dir):
            if frame_path:
                cmd.extend(["-F", frame_path])
            if include_path:
                cmd.extend(["-I", include_path])
        for modulemap in _generated_modulemaps(module_dir):
            cmd.extend(["-Xcc", f"-fmodule-map-file={modulemap}"])
        for include_root in _umbrella_include_dirs(module_dir):
            cmd.extend(["-Xcc", f"-I{include_root}"])

    # Include PepperEvalSDK for Pepper.* API access
    if os.path.exists(_SDK_PATH):
        cmd.append(_SDK_PATH)

    cmd.append(source_path)
    return cmd


def compile_eval(
    code: str,
    mode: str = "expr",
    bundle_id: str | None = None,
    scheme: str | None = None,
    sim_udid: str | None = None,
) -> tuple[bool, str, str | None]:
    """Compile Swift code into a dylib for eval injection.

    Args:
        code: Swift source code (expression for mode=expr, function body for mode=full)
        mode: "expr" wraps in REPL template, "full" uses code as pepperEval body
        bundle_id: App bundle ID for module resolution
        scheme: Xcode scheme name for module resolution
        sim_udid: Simulator UDID (for placing dylib in accessible location)

    Returns:
        (success, dylib_path_or_error, compile_output)
    """
    sdk_path, target, arch = _detect_sdk()
    module_dir, binary_dir, module_name = _find_app_module(bundle_id, scheme)

    def _attempt(with_app_module: bool) -> tuple[bool, str, str | None]:
        app_import = (
            f"@testable import {module_name}" if (with_app_module and module_name) else ""
        )
        if mode == "expr":
            source = REPL_TEMPLATE.format(app_import=app_import, code=code)
        else:
            indented = "\n".join("    " + line for line in code.splitlines())
            source = FULL_TEMPLATE.format(app_import=app_import, code=indented)

        # Unique name based on content hash + timestamp
        code_hash = hashlib.md5(source.encode()).hexdigest()[:8]
        timestamp = int(time.time() * 1000) % 100000
        dylib_name = f"pepper_eval_{code_hash}_{timestamp}"
        source_path = os.path.join(EVAL_DIR, f"{dylib_name}.swift")
        dylib_path = os.path.join(EVAL_DIR, f"{dylib_name}.dylib")
        with open(source_path, "w") as f:
            f.write(source)

        cmd = _swiftc_cmd(
            source_path, dylib_path, sdk_path, target,
            module_dir if with_app_module else None,
        )
        start = time.time()
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=_COMPILE_TIMEOUT)
        elapsed_ms = int((time.time() - start) * 1000)

        if result.returncode != 0:
            error_output = result.stderr.strip() or result.stdout.strip()
            # Clean up error paths for readability
            error_output = error_output.replace(EVAL_DIR + "/", "")
            return False, f"Compilation failed ({elapsed_ms}ms):\n{error_output}", None

        if not os.path.exists(dylib_path):
            return False, "Compiler returned success but dylib not found", None

        dylib_size = os.path.getsize(dylib_path)
        final_path = dylib_path
        # If sim_udid provided, copy to simulator's tmp dir for accessibility
        if sim_udid:
            sim_tmp = _sim_tmp_dir(sim_udid)
            if sim_tmp:
                sim_dylib = os.path.join(sim_tmp, f"{dylib_name}.dylib")
                subprocess.run(["cp", dylib_path, sim_dylib], check=True)
                final_path = sim_dylib
        return True, final_path, f"Compiled in {elapsed_ms}ms ({dylib_size} bytes)"

    # Primary attempt: `@testable import <App>` when the app module resolved.
    ok, path_or_err, info = _attempt(with_app_module=True)
    if ok or not module_name:
        return ok, path_or_err, info

    # Fallback: a few apps link a dependency whose Clang-module graph can't be
    # reconstructed standalone. Retry without the app import so generic evals — the
    # ones that don't touch the app's own types — still run instead of hard-failing.
    ok_fb, path_fb, info_fb = _attempt(with_app_module=False)
    if ok_fb:
        note = (
            f"Compiled WITHOUT `@testable import {module_name}` — the app module "
            f"could not be resolved standalone, so the app's own types are "
            f"unavailable in this eval. {info_fb}"
        )
        return True, path_fb, note
    # Both failed: the with-import error is the informative one — return it.
    return ok, path_or_err, info


def _sim_tmp_dir(udid: str) -> str | None:
    """Get the simulator's /tmp directory on the host filesystem."""
    try:
        result = subprocess.run(
            ["xcrun", "simctl", "get_app_container", udid, "com.apple.Preferences", "data"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            # Container path like /Users/.../data/Containers/Data/Application/UUID
            # Simulator tmp is at the device root: .../data/../../../tmp
            container = result.stdout.strip()
            # Navigate to device root
            parts = container.split("/")
            # Find "data" directory at device level
            for i, part in enumerate(parts):
                if part == "Containers":
                    device_root = "/".join(parts[:i])
                    tmp_dir = os.path.join(device_root, "tmp")
                    os.makedirs(tmp_dir, exist_ok=True)
                    return tmp_dir
    except (subprocess.SubprocessError, OSError):
        pass

    # Fallback: use shared /tmp (works for simulators since they share filesystem)
    return EVAL_DIR
