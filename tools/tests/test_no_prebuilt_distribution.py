"""Regression tests for the source-only distribution stance (BUG-004).

This is a private fork. Two prebuilt-distribution paths pointed at unavailable
targets and were removed:

  (a) the release workflow's "Publish to PyPI" step uploaded distribution name
      `habanero`, which is owned by an unrelated PyPI project (the Crossref
      client) — a tagged release would 403; and
  (b) `dylib_fetch.ensure_dylib()` auto-downloaded a prebuilt framework from
      GitHub Releases that are not published, so it always 404'd.

The dylib now resolves from `make build` output (or an explicit override) only.
These tests guard against either path being reintroduced.
"""

from __future__ import annotations

import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HABANERO_PKG = os.path.join(REPO_ROOT, "habanero")
RELEASE_YML = os.path.join(REPO_ROOT, ".github", "workflows", "release.yml")

# Tokens that only appear when a PyPI publish step is present.
PYPI_MARKERS = ("twine", "Publish to PyPI", "PYPI_TOKEN")


def test_release_workflow_has_no_pypi_publish() -> None:
    """The release workflow must not publish to PyPI (dist name is taken)."""
    with open(RELEASE_YML, encoding="utf-8") as f:
        content = f.read()
    found = [marker for marker in PYPI_MARKERS if marker in content]
    assert not found, (
        f"release.yml still references PyPI publishing {found} — the `habanero` "
        "dist name is owned by another project on PyPI, so this 403s on upload"
    )


def test_no_dylib_autodownload_module() -> None:
    """The auto-download module must be gone (source-only build)."""
    assert not os.path.exists(os.path.join(HABANERO_PKG, "dylib_fetch.py")), (
        "habanero/dylib_fetch.py still exists — the prebuilt-dylib download path "
        "404s against unpublished Releases; the dylib comes from `make build`"
    )


def test_no_ensure_dylib_references_in_package() -> None:
    """No package module may import or call the removed download helper."""
    offenders = []
    for root, _dirs, files in os.walk(HABANERO_PKG):
        for name in files:
            if not name.endswith(".py"):
                continue
            path = os.path.join(root, name)
            with open(path, encoding="utf-8") as f:
                text = f.read()
            if "ensure_dylib" in text or "dylib_fetch" in text:
                offenders.append(os.path.relpath(path, REPO_ROOT))
    assert not offenders, (
        f"{offenders} still reference the removed auto-download — resolve the "
        "dylib from `make build` output instead"
    )
