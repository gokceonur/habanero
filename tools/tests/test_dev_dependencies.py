"""Regression tests for the dev-dependency spec (BUG-003).

The documented quality gates (`make py-test` / `lint-py` / `typecheck`) need
pytest, ruff, and pyright. Those were never declared anywhere — `requirements.txt`
is runtime-only and `pyproject.toml` had no optional-dependencies group — so a
fresh contributor hit `No module named pytest` / `ruff: command not found`.

This test asserts the toolchain is declared under
`[project.optional-dependencies].dev`, so `pip install -e ".[dev]"` provisions
every gate in one step.
"""

from __future__ import annotations

import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PYPROJECT = os.path.join(REPO_ROOT, "pyproject.toml")

# The gates these back: pytest → py-test, ruff → lint-py, pyright → typecheck.
REQUIRED_DEV_TOOLS = {"pytest", "ruff", "pyright"}


def _req_name(requirement: str) -> str:
    """Extract the bare distribution name from a PEP 508 requirement string."""
    return re.split(r"[<>=!~;\[\s]", requirement.strip(), maxsplit=1)[0].lower()


def _dev_dependencies() -> list[str]:
    """Return the `[project.optional-dependencies].dev` list from pyproject.toml.

    Uses tomllib (3.11+) when available; falls back to a regex parse so the test
    still runs on the project's declared 3.10 floor.
    """
    if sys.version_info >= (3, 11):
        import tomllib

        with open(PYPROJECT, "rb") as f:
            data = tomllib.load(f)
        return data.get("project", {}).get("optional-dependencies", {}).get("dev", [])

    # 3.10 fallback: pull the `dev = [ ... ]` array out of the text.
    with open(PYPROJECT, encoding="utf-8") as f:
        text = f.read()
    match = re.search(r"^\s*dev\s*=\s*\[(.*?)\]", text, re.DOTALL | re.MULTILINE)
    if not match:
        return []
    return [item.strip() for item in re.findall(r'"([^"]+)"', match.group(1))]


def test_dev_extras_declare_gate_toolchain() -> None:
    """pytest, ruff, and pyright must all be declared in the `dev` extras."""
    declared = {_req_name(r) for r in _dev_dependencies()}
    missing = REQUIRED_DEV_TOOLS - declared
    assert not missing, (
        f"dev extras missing {sorted(missing)} — `pip install -e \".[dev]\"` won't "
        "provision the documented make gates (py-test/lint-py/typecheck)"
    )


def test_dev_extras_are_version_pinned() -> None:
    """Each gate tool carries a version constraint (reproducible toolchain)."""
    for requirement in _dev_dependencies():
        if _req_name(requirement) in REQUIRED_DEV_TOOLS:
            assert re.search(r"[<>=!~]", requirement), (
                f"{requirement!r} has no version constraint — pin it for reproducibility"
            )
