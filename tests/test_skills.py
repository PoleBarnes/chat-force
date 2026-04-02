"""Validate OpenClaw skill files.

Every skill in skills/ is a Markdown file with YAML frontmatter
that defines the skill's metadata. This module validates that all skills
are well-formed and consistent.
"""

from pathlib import Path

import yaml
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = PROJECT_ROOT / "skills"

REQUIRED_FRONTMATTER_FIELDS = {"name", "description", "triggers", "enabled_by_default", "category"}
VALID_CATEGORIES = {"marketing", "engineering", "operations", "meta"}


def _parse_skill_frontmatter(skill_path: Path) -> dict:
    """Extract YAML frontmatter from a skill markdown file."""
    text = skill_path.read_text(encoding="utf-8")
    # Frontmatter is delimited by --- lines
    if not text.startswith("---"):
        raise ValueError(f"{skill_path.name}: no YAML frontmatter found")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"{skill_path.name}: malformed frontmatter delimiters")
    return yaml.safe_load(parts[1])


def _get_skill_files() -> list[Path]:
    """Return all .md skill files (excluding README)."""
    return [
        f for f in sorted(SKILLS_DIR.glob("*.md"))
        if f.name.lower() != "readme.md"
    ]


# -------------------------------------------------------------------------
# Tests
# -------------------------------------------------------------------------


class TestSkillFrontmatter:
    """Test that every skill has valid YAML frontmatter with required fields."""

    @pytest.fixture
    def skill_files(self):
        files = _get_skill_files()
        assert len(files) > 0, "No skill files found in skills/"
        return files

    @pytest.fixture
    def parsed_skills(self, skill_files):
        return [(f, _parse_skill_frontmatter(f)) for f in skill_files]

    def test_skills_directory_exists(self):
        assert SKILLS_DIR.is_dir(), "skills/ directory does not exist"

    def test_at_least_seven_skills_exist(self, skill_files):
        # README.md is excluded, so we expect 7 actual skill files
        assert len(skill_files) >= 7, (
            f"Expected at least 7 skill files, found {len(skill_files)}: "
            f"{[f.name for f in skill_files]}"
        )

    def test_all_skills_have_valid_frontmatter(self, parsed_skills):
        """Every .md file must have parseable YAML frontmatter."""
        for skill_path, frontmatter in parsed_skills:
            assert isinstance(frontmatter, dict), (
                f"{skill_path.name}: frontmatter is not a dict"
            )

    def test_all_skills_have_required_fields(self, parsed_skills):
        """Each skill frontmatter must contain all required fields."""
        for skill_path, fm in parsed_skills:
            missing = REQUIRED_FRONTMATTER_FIELDS - set(fm.keys())
            assert not missing, (
                f"{skill_path.name}: missing required fields: {missing}"
            )

    def test_skill_names_are_unique(self, parsed_skills):
        """No two skills share the same name."""
        names = [fm["name"] for _, fm in parsed_skills]
        seen = set()
        duplicates = []
        for name in names:
            if name in seen:
                duplicates.append(name)
            seen.add(name)
        assert not duplicates, f"Duplicate skill names: {duplicates}"

    def test_skill_categories_are_valid(self, parsed_skills):
        """Categories must be one of the allowed values."""
        for skill_path, fm in parsed_skills:
            cat = fm.get("category", "")
            assert cat in VALID_CATEGORIES, (
                f"{skill_path.name}: invalid category '{cat}', "
                f"must be one of {VALID_CATEGORIES}"
            )

    def test_skill_triggers_are_lists(self, parsed_skills):
        """Each skill's triggers field must be a list."""
        for skill_path, fm in parsed_skills:
            triggers = fm.get("triggers")
            assert isinstance(triggers, list), (
                f"{skill_path.name}: 'triggers' must be a list, got {type(triggers).__name__}"
            )
            assert len(triggers) > 0, (
                f"{skill_path.name}: 'triggers' must have at least one entry"
            )

    def test_skill_enabled_by_default_is_boolean(self, parsed_skills):
        """The enabled_by_default field must be a boolean."""
        for skill_path, fm in parsed_skills:
            val = fm.get("enabled_by_default")
            assert isinstance(val, bool), (
                f"{skill_path.name}: 'enabled_by_default' must be bool, got {type(val).__name__}"
            )

    def test_skill_files_have_body_content(self, skill_files):
        """Each skill file must have body content after the frontmatter."""
        for skill_path in skill_files:
            text = skill_path.read_text(encoding="utf-8")
            parts = text.split("---", 2)
            body = parts[2].strip() if len(parts) >= 3 else ""
            assert len(body) > 50, (
                f"{skill_path.name}: body content is too short ({len(body)} chars)"
            )
