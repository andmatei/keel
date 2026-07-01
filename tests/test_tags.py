"""Tests for tag validation and round-trip."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from keel.manifest import (
    ProjectManifest,
    ProjectMeta,
    load_project_manifest,
    save_project_manifest,
)
from keel.tags import format_tags, tag_color


def test_tags_default_empty() -> None:
    m = ProjectMeta(name="foo", description="d", created=date(2026, 1, 1))
    assert m.tags == []


def test_tags_valid_simple() -> None:
    m = ProjectMeta(name="foo", description="d", created=date(2026, 1, 1), tags=["api", "research"])
    assert m.tags == ["api", "research"]


def test_tags_lowercased() -> None:
    m = ProjectMeta(name="foo", description="d", created=date(2026, 1, 1), tags=["API", "Research"])
    assert m.tags == ["api", "research"]


def test_tags_deduplicated() -> None:
    m = ProjectMeta(
        name="foo", description="d", created=date(2026, 1, 1), tags=["api", "api", "web"]
    )
    assert m.tags == ["api", "web"]


def test_tags_rejects_spaces() -> None:
    with pytest.raises(ValidationError, match="tag"):
        ProjectMeta(name="foo", description="d", created=date(2026, 1, 1), tags=["has space"])


def test_tags_rejects_special_chars() -> None:
    with pytest.raises(ValidationError, match="tag"):
        ProjectMeta(name="foo", description="d", created=date(2026, 1, 1), tags=["no@special"])


def test_tags_rejects_trailing_hyphen() -> None:
    with pytest.raises(ValidationError, match="tag"):
        ProjectMeta(name="foo", description="d", created=date(2026, 1, 1), tags=["bad-"])


def test_tags_rejects_leading_hyphen() -> None:
    with pytest.raises(ValidationError, match="tag"):
        ProjectMeta(name="foo", description="d", created=date(2026, 1, 1), tags=["-bad"])


def test_tags_accepts_single_char() -> None:
    m = ProjectMeta(name="foo", description="d", created=date(2026, 1, 1), tags=["a"])
    assert m.tags == ["a"]


def test_tags_accepts_hyphens_in_middle() -> None:
    m = ProjectMeta(name="foo", description="d", created=date(2026, 1, 1), tags=["needs-review"])
    assert m.tags == ["needs-review"]


def test_tags_rejects_too_long() -> None:
    with pytest.raises(ValidationError, match="tag"):
        ProjectMeta(name="foo", description="d", created=date(2026, 1, 1), tags=["a" * 51])


def test_tags_rejects_empty_string() -> None:
    with pytest.raises(ValidationError, match="tag"):
        ProjectMeta(name="foo", description="d", created=date(2026, 1, 1), tags=[""])


def test_tags_toml_roundtrip(tmp_path) -> None:
    path = tmp_path / "project.toml"
    original = ProjectManifest(
        project=ProjectMeta(
            name="foo", description="d", created=date(2026, 1, 1), tags=["api", "webhook"]
        ),
    )
    save_project_manifest(path, original)
    loaded = load_project_manifest(path)
    assert loaded.project.tags == ["api", "webhook"]


def test_tags_toml_roundtrip_empty(tmp_path) -> None:
    path = tmp_path / "project.toml"
    original = ProjectManifest(
        project=ProjectMeta(name="foo", description="d", created=date(2026, 1, 1)),
    )
    save_project_manifest(path, original)
    text = path.read_text()
    assert "tags" not in text
    loaded = load_project_manifest(path)
    assert loaded.project.tags == []


def test_tags_toml_load_missing_key(tmp_path) -> None:
    """Old manifests without tags key load fine with empty default."""
    path = tmp_path / "project.toml"
    path.write_text('[project]\nname = "old"\ndescription = "d"\ncreated = 2026-01-01\n')
    loaded = load_project_manifest(path)
    assert loaded.project.tags == []


def test_tag_color_deterministic() -> None:
    c1 = tag_color("api")
    c2 = tag_color("api")
    assert c1 == c2


def test_tag_color_different_tags_can_differ() -> None:
    colors = {tag_color(t) for t in ["api", "web", "research", "infra", "docs", "ci", "ml", "db"]}
    assert len(colors) > 1


def test_format_tags_empty() -> None:
    assert format_tags([]) == ""


def test_format_tags_single() -> None:
    result = format_tags(["api"])
    assert "api" in result


def test_format_tags_multiple() -> None:
    result = format_tags(["api", "webhook"])
    assert "api" in result
    assert "webhook" in result
