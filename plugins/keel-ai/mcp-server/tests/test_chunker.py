"""Tests for chunker — type-specific document splitting."""

from __future__ import annotations

import pytest

from chunker import chunk_markdown, chunk_decision, chunk_milestones_toml, chunk_document


class TestChunkMarkdown:
    def test_splits_on_h2_headings(self) -> None:
        md = "## Intro\n\nHello world.\n\n## Design\n\nSome design text.\n"
        chunks = chunk_markdown(md)
        assert len(chunks) == 2
        assert chunks[0]["section_heading"] == "## Intro"
        assert "Hello world." in chunks[0]["content"]
        assert chunks[1]["section_heading"] == "## Design"
        assert "Some design text." in chunks[1]["content"]

    def test_strips_yaml_frontmatter(self) -> None:
        md = "---\ntitle: Test\n---\n\n## Section\n\nBody text.\n"
        chunks = chunk_markdown(md)
        assert len(chunks) == 1
        assert "title: Test" not in chunks[0]["content"]
        assert "Body text." in chunks[0]["content"]

    def test_skips_empty_sections(self) -> None:
        md = "## Empty\n\n## Has Content\n\nReal content here.\n"
        chunks = chunk_markdown(md)
        assert len(chunks) == 1
        assert chunks[0]["section_heading"] == "## Has Content"

    def test_heading_only_section_skipped(self) -> None:
        md = "## Just a heading\n## Another\n\nWith body.\n"
        chunks = chunk_markdown(md)
        assert len(chunks) == 1
        assert chunks[0]["section_heading"] == "## Another"

    def test_chunk_index_sequential(self) -> None:
        md = "## A\n\nText A.\n\n## B\n\nText B.\n\n## C\n\nText C.\n"
        chunks = chunk_markdown(md)
        assert [c["chunk_index"] for c in chunks] == [0, 1, 2]

    def test_trailing_overlap(self) -> None:
        md = "## First\n\nFirst paragraph. First sentence two.\n\n## Second\n\nSecond paragraph.\n"
        chunks = chunk_markdown(md)
        assert len(chunks) == 2
        # First chunk should have overlap from second section
        assert "Second paragraph." in chunks[0]["content"] or chunks[0].get("overlap")

    def test_subsplit_on_h3_when_large(self) -> None:
        # Build a section over 800 tokens (~4 chars per token, so ~3200+ chars)
        long_h3_1 = "### Part A\n\n" + ("Word " * 500) + "\n\n"
        long_h3_2 = "### Part B\n\n" + ("Word " * 500) + "\n\n"
        md = f"## Big Section\n\n{long_h3_1}{long_h3_2}"
        chunks = chunk_markdown(md)
        assert len(chunks) >= 2
        assert chunks[0]["parent_heading"] == "## Big Section"

    def test_no_heading_document_single_chunk(self) -> None:
        md = "Just a paragraph of text without any headings.\n"
        chunks = chunk_markdown(md)
        assert len(chunks) == 1
        assert chunks[0]["section_heading"] is None

    def test_no_heading_document_large_splits_on_paragraphs(self) -> None:
        paragraphs = "\n\n".join(["Paragraph " + ("word " * 200) for _ in range(5)])
        chunks = chunk_markdown(paragraphs)
        assert len(chunks) >= 2

    def test_oversized_single_paragraph_is_split(self) -> None:
        giant = "x" * 8000  # ~2000 tokens, well above 800-token limit
        chunks = chunk_markdown(giant)
        assert len(chunks) >= 2
        for c in chunks:
            assert len(c["content"]) <= 3200 + 10  # _MAX_CHUNK_CHARS with small tolerance


class TestChunkDecision:
    def test_single_chunk_per_file(self) -> None:
        content = "---\ntitle: Use X\n---\n\n## Question\n\nShould we use X?\n\n## Decision\n\nYes.\n"
        chunks = chunk_decision(content, file_path="decisions/2026-01-01-use-x.md")
        assert len(chunks) == 1
        assert chunks[0]["chunk_index"] == 0
        assert chunks[0]["section_heading"] is None
        # Frontmatter stripped
        assert "title: Use X" not in chunks[0]["content"]

    def test_empty_decision_returns_empty(self) -> None:
        chunks = chunk_decision("", file_path="decisions/empty.md")
        assert chunks == []


class TestChunkMilestonesToml:
    def test_serializes_milestones_as_text(self) -> None:
        toml_content = '''
[[milestones]]
id = "m1"
title = "Foundation"
status = "active"
description = "Build the base"

[[milestones]]
id = "m2"
title = "Polish"
status = "planned"

[[tasks]]
id = "t1"
milestone = "m1"
title = "Setup"
status = "done"

[[tasks]]
id = "t2"
milestone = "m1"
title = "Build"
status = "active"
'''
        chunks = chunk_milestones_toml(toml_content)
        assert len(chunks) == 2
        assert "Foundation" in chunks[0]["content"]
        assert "active" in chunks[0]["content"]
        assert "1/2 done" in chunks[0]["content"] or "tasks" in chunks[0]["content"].lower()
        assert "Polish" in chunks[1]["content"]

    def test_empty_toml_returns_empty(self) -> None:
        chunks = chunk_milestones_toml("")
        assert chunks == []


class TestChunkDocument:
    def test_routes_markdown_by_extension(self) -> None:
        chunks = chunk_document("## Hello\n\nWorld.\n", file_path="design.md", doc_type="design")
        assert len(chunks) >= 1

    def test_routes_decision_files(self) -> None:
        content = "---\ntitle: X\n---\n\nDecision body.\n"
        chunks = chunk_document(content, file_path="decisions/2026-01-01-x.md", doc_type="decision")
        assert len(chunks) == 1

    def test_routes_milestones_toml(self) -> None:
        toml = '[[milestones]]\nid = "m1"\ntitle = "M"\nstatus = "done"\n'
        chunks = chunk_document(toml, file_path="milestones.toml", doc_type="milestones")
        assert len(chunks) >= 1

    def test_empty_document_returns_empty(self) -> None:
        chunks = chunk_document("", file_path="empty.md", doc_type="design")
        assert chunks == []

    def test_whitespace_only_returns_empty(self) -> None:
        chunks = chunk_document("   \n\n  ", file_path="blank.md", doc_type="design")
        assert chunks == []
