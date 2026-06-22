"""Regression tests for the CI lint scope (BUG-005).

CI's "Lint Python (ruff)" step used to run ``ruff check`` over ``tools/`` and the
two generator scripts only — it omitted the ``habanero/`` package, while both
local gates (``make lint-py`` and ``scripts/pre-commit``) lint it. So lint
problems inside ``habanero/`` passed CI while failing locally (three pre-existing
``E501`` in ``habanero/pepper_format.py`` demonstrated the split).

``test_ci_ruff_*`` pin the invariant that CI lints *at least* what the local
``make lint-py`` gate lints, so a path checked locally can never silently escape
CI again. (It is a superset, not an exact match: ``scripts/pre-commit`` already
runs a deliberately narrower scope, so the three gates are not identical by
design.) ``test_system_dialog_probe_message_unchanged`` guards that wrapping the
three long string literals under the line-length limit left the runtime string
byte-identical.
"""

from __future__ import annotations

import os
import re

import habanero.pepper_format as pf

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CI_YML = os.path.join(REPO_ROOT, ".github", "workflows", "ci.yml")
MAKEFILE = os.path.join(REPO_ROOT, "Makefile")

# The exact line the look formatters emit for an inconclusive system-dialog probe.
SYSTEM_DIALOG_PROBE_LINE = (
    "  ⚠ system_dialog_probe_inconclusive — Simulator.app is backgrounded; "
    "focus it and re-run app_look if you expect a system dialog"
)


def _ruff_check_paths(text: str) -> list[str]:
    """Return the path arguments of the first ``ruff check`` invocation in *text*."""
    match = re.search(r"ruff check\s+([^\n]*)", text)
    assert match, "no `ruff check` invocation found"
    # Drop ruff's own flags (e.g. --fix, --quiet); keep the path tokens.
    return [tok for tok in match.group(1).split() if not tok.startswith("-")]


def test_ci_ruff_step_lints_habanero_package() -> None:
    """CI must lint the habanero/ package, not just tools/ and the scripts."""
    with open(CI_YML, encoding="utf-8") as f:
        paths = _ruff_check_paths(f.read())
    assert "habanero/" in paths, (
        f"ci.yml `ruff check` scope {paths} omits `habanero/` — lint problems in "
        "the package escape CI while failing `make lint-py` and `scripts/pre-commit`"
    )


def test_ci_ruff_scope_covers_make_lint_py() -> None:
    """CI's ruff scope must be a superset of the `make lint-py` scope.

    The real invariant is CI ⊇ local gate: anything linted locally must also be
    linted on CI. It is not exact equality — `scripts/pre-commit` runs a narrower
    scope on purpose — so pinning CI == Makefile would couple unrelated paths.
    """
    with open(CI_YML, encoding="utf-8") as f:
        ci_paths = _ruff_check_paths(f.read())
    with open(MAKEFILE, encoding="utf-8") as f:
        make_paths = _ruff_check_paths(f.read())
    missing = set(make_paths) - set(ci_paths)
    assert not missing, (
        f"CI ruff scope {ci_paths} omits {sorted(missing)} that `make lint-py` "
        f"lints {make_paths} — those paths are checked locally but escape CI"
    )


def test_system_dialog_probe_message_unchanged() -> None:
    """Wrapping the long literals left the emitted probe line byte-identical.

    Exercises the ``system_dialog_unknown`` branch in all three look formatters —
    the formatters that hold the three wrapped strings — and asserts the runtime
    output is unchanged. (``test_pepper_format.py`` does not cover this branch.)
    """
    resp = {"status": "ok", "data": {"screen": "X", "rows": [], "system_dialog_unknown": True}}
    pf._prev_compact_text = set()  # isolate the compact formatter's diff state
    for formatter in (pf.format_look, pf.format_look_slim, pf.format_look_compact):
        assert SYSTEM_DIALOG_PROBE_LINE in formatter(resp), (
            f"{formatter.__name__} no longer emits the verbatim probe line — the "
            "wrapped string literal must stay byte-identical"
        )
