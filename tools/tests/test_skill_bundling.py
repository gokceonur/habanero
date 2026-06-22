"""Regression tests for skill-prompt bundling (BUG-001).

Skill sources must live in the tracked package tree (`pepper_ios/skills/<name>/
SKILL.md`) so they ship inside the wheel and resolve at runtime via
`importlib.resources`. The previous state force-included the gitignored
`.claude/skills` path, which broke `pip install -e .` on a fresh clone and left
the skills unbundled.

These tests assert the package-data path is present and that
`mcp_prompts._read_skill` resolves real content from it.
"""

from __future__ import annotations

from importlib import resources

import pytest

import pepper_ios.mcp_prompts as mp

# Skill directory names declared in mcp_prompts._SKILLS.
SKILL_DIRS = [skill_dir for (_, _, skill_dir, _) in mp._SKILLS]


@pytest.mark.parametrize("skill_dir", SKILL_DIRS)
def test_skill_md_bundled_in_package(skill_dir: str) -> None:
    """Each declared skill has a SKILL.md under the packaged `pepper_ios/skills/`.

    This is the path a built wheel exposes; resolving it via importlib.resources
    proves the file is part of the package, not just present in a dev checkout.
    """
    packaged = resources.files("pepper_ios") / "skills" / skill_dir / "SKILL.md"
    assert packaged.is_file(), (
        f"{skill_dir}/SKILL.md is not bundled under pepper_ios/skills/ — "
        "skill-prompts will be unavailable in a clean install"
    )


@pytest.mark.parametrize("skill_dir", SKILL_DIRS)
def test_read_skill_resolves_content(skill_dir: str) -> None:
    """`_read_skill` returns non-empty content with the YAML frontmatter stripped."""
    content = mp._read_skill(skill_dir)
    assert content is not None, f"_read_skill({skill_dir!r}) returned None"
    assert content.strip(), f"_read_skill({skill_dir!r}) returned empty content"
    # Frontmatter must be stripped: body should not start with the `---` fence.
    assert not content.lstrip().startswith("---"), (
        "YAML frontmatter was not stripped from SKILL.md"
    )


def test_at_least_one_skill_declared() -> None:
    """Guard against an empty _SKILLS list silently passing the parametrized tests."""
    assert SKILL_DIRS, "no skills declared in mcp_prompts._SKILLS"
