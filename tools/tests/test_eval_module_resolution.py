"""Regression tests for app_eval products-dir resolution (BUG-007).

BUG-007 lived in ``habanero/mcp_eval_compiler.py``'s products resolver — the path
that lets a compiled eval ``@testable import`` the running app's own Swift module.
The resolver hardcoded ``Build/Products/Debug-iphonesimulator``, so an app built
under any other configuration (e.g. the Shift "Shift Dev" scheme → ``Dev`` config →
``Dev-iphonesimulator``) was invisible and eval could not find the app's
``.swiftmodule``. These tests pin that every ``*-iphonesimulator`` product dir is
discovered while device (``*-iphoneos``) and unsuffixed config dirs stay excluded.
"""

from __future__ import annotations

import os

from habanero import mcp_eval_compiler as ec


def _mk(*parts: str) -> str:
    """Create a directory tree and return its leaf path."""
    path = os.path.join(*parts)
    os.makedirs(path, exist_ok=True)
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
