# keel-ai Phase 2: Vector-Powered Design Intelligence — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add semantic vector search to keel-ai so the design-sync agent (and other skills) can find relevant design document sections instead of reading everything, plus the `/scope-first` skill and custom action routing.

**Architecture:** An MCP server (`plugins/keel-ai/mcp-server/`) started by Claude Code per session connects to a shared Atlas local Docker container. The indexer module chunks design documents, embeds them via Voyage (through Grove), and upserts to MongoDB. Three MCP tools — `search`, `reindex`, `status` — expose the capability. Lazy initialization: server starts instantly, defers Docker and indexing to first tool call. The `/scope-first` skill and custom action routing are independent additions to the existing plugin.

**Tech Stack:** Python 3.11+ (mcp SDK, pymongo >= 4.7, voyageai), Docker Compose (Atlas local), Bash (hook updates)

**Spec:** `design/specs/2026-05-20-keel-ai-phase2-vector-search.md`

---

## File Structure

### MCP server (`plugins/keel-ai/mcp-server/`)

| File | Purpose |
|------|---------|
| `server.py` | FastMCP server: tool definitions, lazy Atlas init, Voyage client setup |
| `indexer.py` | Document chunking, embedding, upsert, orphan cleanup |
| `chunker.py` | Type-specific chunking strategies (markdown, TOML, decisions) |
| `atlas.py` | Atlas local Docker lifecycle, pymongo connection, index management |
| `docker-compose.yml` | Atlas local container with persistent volume |
| `requirements.txt` | pymongo, voyageai, mcp dependencies |

### Plugin updates

| File | Purpose |
|------|---------|
| `plugins/keel-ai/hooks/hooks.json` | Add `mcpServers` entry for keel-design-search |
| `plugins/keel-ai/hooks/session-start` | Trigger reindex after AGENTS.md generation |
| `plugins/keel-ai/agents/design-sync.md` | Updated to use search before reading full docs |
| `plugins/keel-ai/skills/scope-first/SKILL.md` | NEW: guided scope→design→plan→execute workflow |
| `plugins/keel-ai/skills/using-keel-ai/SKILL.md` | Updated to document /scope-first and search |

### Tests

| File | Purpose |
|------|---------|
| `plugins/keel-ai/mcp-server/tests/test_chunker.py` | Unit: markdown splitting, TOML serialization, frontmatter stripping, edge cases |
| `plugins/keel-ai/mcp-server/tests/test_indexer.py` | Unit: metadata prepending, batch sizing, content hash skipping, orphan cleanup |
| `plugins/keel-ai/mcp-server/tests/test_atlas.py` | Unit: Docker health check logic, index creation calls |
| `plugins/keel-ai/mcp-server/tests/test_server.py` | Unit: tool input validation, error handling, lazy init gating |
| `tests/hooks/test_match_triggers.py` | Existing file — add tests for custom action routing |

---

### Task 1: Document Chunker

**Files:**
- Create: `plugins/keel-ai/mcp-server/chunker.py`
- Create: `plugins/keel-ai/mcp-server/tests/__init__.py`
- Create: `plugins/keel-ai/mcp-server/tests/test_chunker.py`

This is a pure-Python module with no external dependencies — good starting point.

- [ ] **Step 1: Write failing tests for markdown chunking**

```python
# plugins/keel-ai/mcp-server/tests/__init__.py
# (empty)
```

```python
# plugins/keel-ai/mcp-server/tests/test_chunker.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd plugins/keel-ai/mcp-server && python -m pytest tests/test_chunker.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'chunker'`

- [ ] **Step 3: Implement the chunker module**

```python
# plugins/keel-ai/mcp-server/chunker.py
"""Type-specific document chunking for vector search indexing.

Splits design documents into chunks suitable for embedding. Each chunk is
a dict with: content, section_heading, parent_heading, chunk_index.
"""

from __future__ import annotations

import hashlib
import re

import tomllib


# Approximate token count: ~4 chars per token for English text.
_CHARS_PER_TOKEN = 4
_MAX_CHUNK_TOKENS = 800
_MAX_CHUNK_CHARS = _MAX_CHUNK_TOKENS * _CHARS_PER_TOKEN
_OVERLAP_SENTENCES = 2


def _estimate_tokens(text: str) -> int:
    return len(text) // _CHARS_PER_TOKEN


def _strip_frontmatter(text: str) -> str:
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            return text[end + 3:].lstrip("\n")
    return text


def _extract_overlap(text: str, max_sentences: int = _OVERLAP_SENTENCES) -> str:
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    overlap = sentences[:max_sentences]
    return " ".join(overlap) if overlap else ""


def _split_paragraphs(text: str, max_chars: int = _MAX_CHUNK_CHARS) -> list[str]:
    paragraphs = re.split(r'\n\n+', text.strip())
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for para in paragraphs:
        if current_len + len(para) > max_chars and current:
            chunks.append("\n\n".join(current))
            current = []
            current_len = 0
        current.append(para)
        current_len += len(para) + 2
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def chunk_markdown(text: str) -> list[dict]:
    text = _strip_frontmatter(text)
    if not text.strip():
        return []

    # Split into sections by ## headings
    h2_pattern = re.compile(r'^(## .+)$', re.MULTILINE)
    parts = h2_pattern.split(text)

    # parts alternates: [preamble, heading1, body1, heading2, body2, ...]
    sections: list[tuple[str | None, str]] = []

    # Handle preamble (text before first ##)
    if parts[0].strip():
        sections.append((None, parts[0].strip()))

    for i in range(1, len(parts), 2):
        heading = parts[i].strip()
        body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        sections.append((heading, body))

    chunks: list[dict] = []
    chunk_index = 0

    for sec_idx, (heading, body) in enumerate(sections):
        if not body:
            continue

        # Add trailing overlap from next section
        overlap = ""
        if sec_idx + 1 < len(sections):
            next_body = sections[sec_idx + 1][1]
            if next_body:
                overlap = _extract_overlap(next_body)

        content_with_overlap = body
        if overlap:
            content_with_overlap = body + "\n\n" + overlap

        if _estimate_tokens(body) <= _MAX_CHUNK_TOKENS:
            chunks.append({
                "section_heading": heading,
                "parent_heading": None,
                "content": content_with_overlap,
                "chunk_index": chunk_index,
            })
            chunk_index += 1
        else:
            # Try sub-splitting on ### headings
            sub_chunks = _subsplit_h3(heading, body, overlap)
            if sub_chunks:
                for sc in sub_chunks:
                    sc["chunk_index"] = chunk_index
                    chunk_index += 1
                chunks.extend(sub_chunks)
            else:
                # Fall back to paragraph splitting
                for part in _split_paragraphs(content_with_overlap):
                    chunks.append({
                        "section_heading": heading,
                        "parent_heading": None,
                        "content": part,
                        "chunk_index": chunk_index,
                    })
                    chunk_index += 1

    return chunks


def _subsplit_h3(parent_heading: str | None, body: str, overlap: str) -> list[dict] | None:
    h3_pattern = re.compile(r'^(### .+)$', re.MULTILINE)
    parts = h3_pattern.split(body)
    if len(parts) < 3:
        return None

    sub_chunks: list[dict] = []
    # Preamble before first ###
    if parts[0].strip():
        sub_chunks.append({
            "section_heading": parent_heading,
            "parent_heading": parent_heading,
            "content": parts[0].strip(),
        })

    for i in range(1, len(parts), 2):
        h3_heading = parts[i].strip()
        h3_body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        if not h3_body:
            continue
        content = f"{h3_heading}\n\n{h3_body}"
        # Add overlap to last sub-chunk only
        if i + 2 >= len(parts) and overlap:
            content = content + "\n\n" + overlap
        sub_chunks.append({
            "section_heading": h3_heading,
            "parent_heading": parent_heading,
            "content": content,
        })

    return sub_chunks if sub_chunks else None


def chunk_decision(content: str, *, file_path: str) -> list[dict]:
    text = _strip_frontmatter(content)
    if not text.strip():
        return []
    return [{
        "section_heading": None,
        "parent_heading": None,
        "content": text.strip(),
        "chunk_index": 0,
    }]


def chunk_milestones_toml(content: str) -> list[dict]:
    if not content.strip():
        return []
    try:
        data = tomllib.loads(content)
    except Exception:
        return []

    milestones = data.get("milestones", [])
    tasks = data.get("tasks", [])
    if not milestones:
        return []

    chunks: list[dict] = []
    for idx, ms in enumerate(milestones):
        ms_id = ms.get("id", "?")
        ms_tasks = [t for t in tasks if t.get("milestone") == ms_id]
        done_count = sum(1 for t in ms_tasks if t.get("status") == "done")
        total = len(ms_tasks)

        parts = [
            f"Milestone: {ms.get('title', ms_id)}",
            f"Status: {ms.get('status', 'unknown')}",
        ]
        if total > 0:
            parts.append(f"Tasks: {done_count}/{total} done")
        if ms.get("description"):
            parts.append(f"Description: {ms['description']}")

        chunks.append({
            "section_heading": None,
            "parent_heading": None,
            "content": " | ".join(parts),
            "chunk_index": idx,
        })

    return chunks


def chunk_document(content: str, *, file_path: str, doc_type: str) -> list[dict]:
    if not content.strip():
        return []

    if doc_type == "decision":
        return chunk_decision(content, file_path=file_path)
    if doc_type == "milestones" or file_path.endswith(".toml"):
        return chunk_milestones_toml(content)
    return chunk_markdown(content)


def content_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()[:12]


def prepend_metadata(text: str, *, project: str, doc_type: str) -> str:
    return f"[project: {project}] [type: {doc_type}] {text}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd plugins/keel-ai/mcp-server && python -m pytest tests/test_chunker.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add plugins/keel-ai/mcp-server/chunker.py plugins/keel-ai/mcp-server/tests/
git commit -m "feat(keel-ai): add document chunker for vector search indexing"
```

---

### Task 2: Atlas Local Docker Lifecycle

**Files:**
- Create: `plugins/keel-ai/mcp-server/atlas.py`
- Create: `plugins/keel-ai/mcp-server/docker-compose.yml`
- Create: `plugins/keel-ai/mcp-server/tests/test_atlas.py`

Manages the Docker container and pymongo connection. All Docker and MongoDB operations are behind methods that can be mocked in tests.

- [ ] **Step 1: Create docker-compose.yml**

```yaml
# plugins/keel-ai/mcp-server/docker-compose.yml
services:
  atlas-local:
    image: mongodb/mongodb-atlas-local
    container_name: keel-atlas-local
    ports:
      - "27117:27017"
    volumes:
      - keel-atlas-data:/data/db
    healthcheck:
      test: mongosh --quiet --port 27017 --eval "db.runCommand({ping:1})"
      interval: 5s
      retries: 3

volumes:
  keel-atlas-data:
```

- [ ] **Step 2: Write failing tests for atlas module**

```python
# plugins/keel-ai/mcp-server/tests/test_atlas.py
"""Tests for atlas — Docker lifecycle and MongoDB connection management."""

from __future__ import annotations

from unittest.mock import MagicMock, patch, call

import pytest

from atlas import AtlasLocal, MONGO_URI, DB_NAME, COLLECTION_NAME, VECTOR_INDEX_NAME


class TestAtlasLocalInit:
    def test_default_uri(self) -> None:
        a = AtlasLocal()
        assert a.uri == MONGO_URI

    def test_not_initialized_on_creation(self) -> None:
        a = AtlasLocal()
        assert a._client is None
        assert a._initialized is False


class TestEnsureRunning:
    @patch("atlas.subprocess.run")
    def test_skips_compose_when_healthy(self, mock_run) -> None:
        # docker inspect returns healthy
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='[{"State":{"Health":{"Status":"healthy"}}}]',
        )
        a = AtlasLocal()
        a._ensure_docker_running()
        # Should call docker inspect but NOT docker compose up
        calls = [c.args[0] for c in mock_run.call_args_list]
        assert any("inspect" in str(c) for c in calls)
        assert not any("compose" in str(c) and "up" in str(c) for c in calls)

    @patch("atlas.subprocess.run")
    def test_runs_compose_up_when_not_healthy(self, mock_run) -> None:
        # First call (inspect) returns non-zero, second call (compose up) succeeds
        mock_run.side_effect = [
            MagicMock(returncode=1, stdout=""),  # inspect fails
            MagicMock(returncode=0),  # compose up
        ]
        a = AtlasLocal()
        a._compose_file = "/fake/docker-compose.yml"
        a._ensure_docker_running()
        calls = [c.args[0] for c in mock_run.call_args_list]
        assert any("compose" in str(c) and "up" in str(c) for c in calls)


class TestEnsureIndexes:
    def test_creates_vector_index_when_missing(self) -> None:
        a = AtlasLocal()
        mock_coll = MagicMock()
        mock_coll.list_search_indexes.return_value = []
        a._ensure_vector_index(mock_coll)
        mock_coll.create_search_index.assert_called_once()

    def test_skips_vector_index_when_exists(self) -> None:
        a = AtlasLocal()
        mock_coll = MagicMock()
        mock_coll.list_search_indexes.return_value = [
            MagicMock(name=VECTOR_INDEX_NAME),
        ]
        # Simulate the index object having a "name" attribute
        mock_coll.list_search_indexes.return_value[0].__getitem__ = (
            lambda self, k: VECTOR_INDEX_NAME if k == "name" else None
        )
        a._ensure_vector_index(mock_coll)
        mock_coll.create_search_index.assert_not_called()


class TestGetCollection:
    def test_returns_collection_after_init(self) -> None:
        a = AtlasLocal()
        mock_client = MagicMock()
        a._client = mock_client
        a._initialized = True
        coll = a.get_collection()
        assert coll == mock_client[DB_NAME][COLLECTION_NAME]


class TestConnectionCleanup:
    def test_close_closes_client(self) -> None:
        a = AtlasLocal()
        mock_client = MagicMock()
        a._client = mock_client
        a.close()
        mock_client.close.assert_called_once()

    def test_close_noop_when_no_client(self) -> None:
        a = AtlasLocal()
        a.close()  # Should not raise
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd plugins/keel-ai/mcp-server && python -m pytest tests/test_atlas.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'atlas'`

- [ ] **Step 4: Implement the atlas module**

```python
# plugins/keel-ai/mcp-server/atlas.py
"""Atlas local Docker lifecycle and MongoDB connection management."""

from __future__ import annotations

import atexit
import json
import logging
import subprocess
import time
from pathlib import Path

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.operations import SearchIndexModel

_log = logging.getLogger(__name__)

MONGO_URI = "mongodb://localhost:27117/?serverSelectionTimeoutMS=5000"
DB_NAME = "keel_ai"
COLLECTION_NAME = "doc_chunks"
VECTOR_INDEX_NAME = "design_docs_index"
_COMPOSE_FILE = str(Path(__file__).parent / "docker-compose.yml")


class AtlasLocal:
    def __init__(self, uri: str = MONGO_URI) -> None:
        self.uri = uri
        self._client: MongoClient | None = None
        self._initialized: bool = False
        self._compose_file: str = _COMPOSE_FILE

    def initialize(self) -> str | None:
        """Lazy init: start Docker, connect, ensure indexes.

        Returns None on success, or a user-facing error string.
        """
        if self._initialized:
            return None

        err = self._ensure_docker_running()
        if err:
            return err

        try:
            self._client = MongoClient(self.uri)
            self._client.admin.command("ping")
        except Exception as exc:
            return f"Cannot connect to Atlas local at {self.uri}: {exc}"

        atexit.register(self.close)

        coll = self._client[DB_NAME][COLLECTION_NAME]
        self._ensure_compound_indexes(coll)
        self._ensure_vector_index(coll)
        self._initialized = True
        return None

    def get_collection(self) -> Collection:
        return self._client[DB_NAME][COLLECTION_NAME]

    def is_ready(self) -> bool:
        return self._initialized

    def health(self) -> dict:
        if not self._client:
            return {"connected": False, "reason": "not initialized"}
        try:
            self._client.admin.command("ping")
            return {"connected": True}
        except Exception as exc:
            return {"connected": False, "reason": str(exc)}

    def vector_index_status(self) -> str:
        if not self._client:
            return "not initialized"
        coll = self.get_collection()
        try:
            for idx in coll.list_search_indexes():
                if idx.get("name") == VECTOR_INDEX_NAME:
                    return idx.get("status", "UNKNOWN")
        except Exception:
            pass
        return "NOT_FOUND"

    def _ensure_docker_running(self) -> str | None:
        try:
            result = subprocess.run(
                ["docker", "inspect", "--format", "json", "keel-atlas-local"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                info = json.loads(result.stdout)
                if info and info[0].get("State", {}).get("Health", {}).get("Status") == "healthy":
                    return None
        except Exception:
            pass

        _log.info("Starting Atlas local via docker compose")
        try:
            subprocess.run(
                ["docker", "compose", "-f", self._compose_file, "up", "-d", "--wait"],
                capture_output=True, text=True, timeout=120,
            )
        except Exception as exc:
            return f"Failed to start Atlas local: {exc}"

        return None

    def _ensure_compound_indexes(self, coll: Collection) -> None:
        coll.create_index(
            [("project", 1), ("file_path", 1), ("chunk_index", 1)],
            unique=True,
        )
        coll.create_index([("project", 1), ("doc_type", 1)])

    def _ensure_vector_index(self, coll: Collection) -> None:
        try:
            existing = list(coll.list_search_indexes())
        except Exception:
            existing = []

        for idx in existing:
            if idx.get("name") == VECTOR_INDEX_NAME:
                _log.info("Vector search index already exists")
                return

        _log.info("Creating vector search index")
        coll.create_search_index(SearchIndexModel(
            name=VECTOR_INDEX_NAME,
            type="vectorSearch",
            definition={
                "fields": [
                    {"path": "embedding", "type": "vector",
                     "numDimensions": 512, "similarity": "cosine"},
                    {"path": "project", "type": "filter"},
                    {"path": "deliverable", "type": "filter"},
                    {"path": "doc_type", "type": "filter"},
                ],
            },
        ))
        self._wait_for_index_ready(coll)

    def _wait_for_index_ready(self, coll: Collection, timeout: float = 60) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                for idx in coll.list_search_indexes():
                    if idx.get("name") == VECTOR_INDEX_NAME:
                        if idx.get("status") == "READY":
                            return
            except Exception:
                pass
            time.sleep(1)
        _log.warning("Vector index did not reach READY within %ss", timeout)

    def close(self) -> None:
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd plugins/keel-ai/mcp-server && python -m pytest tests/test_atlas.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add plugins/keel-ai/mcp-server/atlas.py plugins/keel-ai/mcp-server/docker-compose.yml plugins/keel-ai/mcp-server/tests/test_atlas.py
git commit -m "feat(keel-ai): add Atlas local Docker lifecycle and connection management"
```

---

### Task 3: Indexer — Embedding, Upsert, Orphan Cleanup

**Files:**
- Create: `plugins/keel-ai/mcp-server/indexer.py`
- Create: `plugins/keel-ai/mcp-server/tests/test_indexer.py`

The indexer ties chunking to embedding and MongoDB writes. Tests mock Voyage and pymongo.

- [ ] **Step 1: Write failing tests for the indexer**

```python
# plugins/keel-ai/mcp-server/tests/test_indexer.py
"""Tests for indexer — embedding, upsert, orphan cleanup."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from indexer import Indexer, _batch_by_tokens


class TestBatchByTokens:
    def test_single_batch_when_small(self) -> None:
        texts = ["hello world", "foo bar"]
        batches = list(_batch_by_tokens(texts, max_count=128, max_tokens=320_000))
        assert len(batches) == 1
        assert batches[0] == ["hello world", "foo bar"]

    def test_splits_on_count_limit(self) -> None:
        texts = [f"text_{i}" for i in range(10)]
        batches = list(_batch_by_tokens(texts, max_count=3, max_tokens=320_000))
        assert len(batches) == 4  # 3, 3, 3, 1

    def test_splits_on_token_limit(self) -> None:
        # Each text is ~250 tokens (1000 chars / 4)
        texts = ["x" * 1000 for _ in range(5)]
        # With max_tokens=400, only 1 item per batch (~250 tokens each)
        batches = list(_batch_by_tokens(texts, max_count=128, max_tokens=400))
        assert len(batches) == 5


class TestIndexerMetadata:
    def test_prepends_metadata_to_content(self) -> None:
        idx = Indexer.__new__(Indexer)
        result = idx._prepare_for_embedding(
            "Some content", project="my-proj", doc_type="design"
        )
        assert result.startswith("[project: my-proj] [type: design]")
        assert "Some content" in result


class TestIndexerReindex:
    @patch("indexer.voyageai")
    def test_skips_unchanged_chunks(self, mock_voyage) -> None:
        mock_coll = MagicMock()
        mock_voyage_client = MagicMock()
        mock_voyage.Client.return_value = mock_voyage_client

        idx = Indexer(collection=mock_coll, voyage_client=mock_voyage_client)

        # Simulate existing chunk with matching hash
        mock_coll.find_one.return_value = {"content_hash": "sha256:abc123"}

        result = idx._should_skip_chunk("sha256:abc123")
        assert result is True

    @patch("indexer.voyageai")
    def test_embeds_new_chunks(self, mock_voyage) -> None:
        mock_coll = MagicMock()
        mock_voyage_client = MagicMock()
        mock_voyage_client.embed.return_value = MagicMock(embeddings=[[0.1] * 512])

        idx = Indexer(collection=mock_coll, voyage_client=mock_voyage_client)

        embeddings = idx._embed_texts(["hello world"])
        assert len(embeddings) == 1
        assert len(embeddings[0]) == 512
        mock_voyage_client.embed.assert_called_once_with(
            ["hello world"], model="voyage-3-lite", input_type="document",
        )


class TestOrphanCleanup:
    @patch("indexer.voyageai")
    def test_deletes_chunks_for_removed_files(self, mock_voyage) -> None:
        mock_coll = MagicMock()
        mock_voyage_client = MagicMock()

        idx = Indexer(collection=mock_coll, voyage_client=mock_voyage_client)

        # DB has chunks for files A and B; filesystem only has A
        mock_coll.distinct.return_value = ["design.md", "removed.md"]
        filesystem_files = {"design.md"}

        ops = idx._orphan_delete_ops("my-proj", filesystem_files, {})
        assert len(ops) >= 1
        # Should produce a DeleteMany for removed.md

    @patch("indexer.voyageai")
    def test_deletes_excess_chunks_for_shrunk_files(self, mock_voyage) -> None:
        mock_coll = MagicMock()
        mock_voyage_client = MagicMock()

        idx = Indexer(collection=mock_coll, voyage_client=mock_voyage_client)

        # DB has chunks for design.md; filesystem version now has fewer chunks
        mock_coll.distinct.return_value = ["design.md"]
        filesystem_files = {"design.md"}
        new_chunk_counts = {"design.md": 2}

        ops = idx._orphan_delete_ops("my-proj", filesystem_files, new_chunk_counts)
        # Should produce a DeleteMany for chunk_index >= 2
        assert len(ops) >= 1


class TestReindexLock:
    @patch("indexer.voyageai")
    def test_acquires_lock(self, mock_voyage) -> None:
        mock_coll = MagicMock()
        mock_voyage_client = MagicMock()

        idx = Indexer(collection=mock_coll, voyage_client=mock_voyage_client)

        lock_coll = MagicMock()
        lock_coll.find_one_and_update.return_value = {"_id": "proj", "locked": True}
        idx._lock_collection = lock_coll

        assert idx._acquire_lock("proj") is True
        lock_coll.find_one_and_update.assert_called_once()

    @patch("indexer.voyageai")
    def test_lock_fails_when_already_locked(self, mock_voyage) -> None:
        mock_coll = MagicMock()
        mock_voyage_client = MagicMock()

        idx = Indexer(collection=mock_coll, voyage_client=mock_voyage_client)

        lock_coll = MagicMock()
        # Simulate duplicate key error when lock already held
        from pymongo.errors import DuplicateKeyError
        lock_coll.find_one_and_update.side_effect = DuplicateKeyError("duplicate key")
        idx._lock_collection = lock_coll

        assert idx._acquire_lock("proj") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd plugins/keel-ai/mcp-server && python -m pytest tests/test_indexer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'indexer'`

- [ ] **Step 3: Implement the indexer module**

```python
# plugins/keel-ai/mcp-server/indexer.py
"""Document indexer: chunking, embedding, upsert, orphan cleanup."""

from __future__ import annotations

import logging
import subprocess
import time
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

import voyageai
from pymongo import DeleteMany, UpdateOne
from pymongo.collection import Collection

from chunker import chunk_document, content_hash, prepend_metadata

_log = logging.getLogger(__name__)

_CHARS_PER_TOKEN = 4
_MAX_BATCH_COUNT = 128
_MAX_BATCH_TOKENS = 320_000
_EMBED_MODEL = "voyage-3-lite"
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0

# Doc types and their file patterns
_DOC_PATTERNS: dict[str, list[str]] = {
    "scope": ["scope.md"],
    "design": ["design.md"],
    "milestones": ["milestones.toml"],
}
_DECISION_GLOB = "decisions/*.md"


def _batch_by_tokens(
    texts: list[str],
    max_count: int = _MAX_BATCH_COUNT,
    max_tokens: int = _MAX_BATCH_TOKENS,
) -> Iterator[list[str]]:
    batch: list[str] = []
    batch_tokens = 0
    for text in texts:
        text_tokens = len(text) // _CHARS_PER_TOKEN
        if batch and (len(batch) >= max_count or batch_tokens + text_tokens > max_tokens):
            yield batch
            batch = []
            batch_tokens = 0
        batch.append(text)
        batch_tokens += text_tokens
    if batch:
        yield batch


def _git_hash(project_dir: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5, cwd=project_dir,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


class Indexer:
    def __init__(
        self,
        collection: Collection,
        voyage_client: voyageai.Client,
    ) -> None:
        self._coll = collection
        self._voyage = voyage_client
        db = collection.database
        self._lock_collection = db["reindex_locks"]

    def reindex_project(
        self,
        project_name: str,
        project_dir: Path,
        *,
        full: bool = False,
        deliverable: str | None = None,
    ) -> dict:
        if not self._acquire_lock(project_name):
            return {"status": "skipped", "reason": "another reindex is running"}

        try:
            return self._do_reindex(project_name, project_dir, full=full, deliverable=deliverable)
        finally:
            self._release_lock(project_name)

    def _do_reindex(
        self,
        project_name: str,
        project_dir: Path,
        *,
        full: bool,
        deliverable: str | None,
    ) -> dict:
        if full:
            self._coll.delete_many({"project": project_name})

        files = self._discover_files(project_dir)
        git_h = _git_hash(project_dir)
        now = datetime.now(timezone.utc)

        indexed = 0
        skipped = 0
        failed_files: list[str] = []
        new_chunk_counts: dict[str, int] = {}

        for file_path, doc_type, abs_path in files:
            try:
                content = abs_path.read_text(encoding="utf-8")
            except Exception:
                failed_files.append(file_path)
                continue

            chunks = chunk_document(content, file_path=file_path, doc_type=doc_type)
            new_chunk_counts[file_path] = len(chunks)

            if not chunks:
                continue

            texts_to_embed: list[str] = []
            chunk_data: list[dict] = []

            for chunk in chunks:
                c_hash = content_hash(chunk["content"])
                if not full and self._chunk_unchanged(project_name, file_path, chunk["chunk_index"], c_hash):
                    skipped += 1
                    continue

                embed_text = self._prepare_for_embedding(
                    chunk["content"], project=project_name, doc_type=doc_type,
                )
                texts_to_embed.append(embed_text)
                chunk_data.append({
                    **chunk,
                    "project": project_name,
                    "deliverable": deliverable,
                    "doc_type": doc_type,
                    "file_path": file_path,
                    "content_hash": c_hash,
                    "token_count": len(chunk["content"]) // _CHARS_PER_TOKEN,
                    "git_hash": git_h,
                    "indexed_at": now,
                })

            if not texts_to_embed:
                continue

            try:
                embeddings = self._embed_texts(texts_to_embed)
            except Exception as exc:
                _log.error("Embedding failed for %s: %s", file_path, exc)
                failed_files.append(file_path)
                continue

            ops = []
            for cd, emb in zip(chunk_data, embeddings):
                cd["embedding"] = emb
                ops.append(UpdateOne(
                    {"project": cd["project"], "file_path": cd["file_path"],
                     "chunk_index": cd["chunk_index"]},
                    {"$set": cd},
                    upsert=True,
                ))
            if ops:
                self._coll.bulk_write(ops)
                indexed += len(ops)

        # Orphan cleanup
        filesystem_files = {f[0] for f in files}
        orphan_ops = self._orphan_delete_ops(project_name, filesystem_files, new_chunk_counts)
        orphans_removed = 0
        if orphan_ops:
            result = self._coll.bulk_write(orphan_ops)
            orphans_removed = result.deleted_count

        return {
            "status": "ok",
            "indexed": indexed,
            "skipped": skipped,
            "orphans_removed": orphans_removed,
            "failed_files": failed_files,
        }

    def _discover_files(self, project_dir: Path) -> list[tuple[str, str, Path]]:
        files: list[tuple[str, str, Path]] = []
        for doc_type, patterns in _DOC_PATTERNS.items():
            for pattern in patterns:
                p = project_dir / pattern
                if p.is_file():
                    files.append((pattern, doc_type, p))

        decisions_dir = project_dir / "decisions"
        if decisions_dir.is_dir():
            for p in sorted(decisions_dir.glob("*.md")):
                rel = f"decisions/{p.name}"
                files.append((rel, "decision", p))

        return files

    def _chunk_unchanged(
        self, project: str, file_path: str, chunk_index: int, new_hash: str,
    ) -> bool:
        existing = self._coll.find_one(
            {"project": project, "file_path": file_path, "chunk_index": chunk_index},
            {"content_hash": 1},
        )
        return existing is not None and existing.get("content_hash") == new_hash

    def _should_skip_chunk(self, existing_hash: str) -> bool:
        return True

    def _prepare_for_embedding(self, text: str, *, project: str, doc_type: str) -> str:
        return prepend_metadata(text, project=project, doc_type=doc_type)

    def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        all_embeddings: list[list[float]] = []
        for batch in _batch_by_tokens(texts):
            for attempt in range(_MAX_RETRIES):
                try:
                    result = self._voyage.embed(
                        batch, model=_EMBED_MODEL, input_type="document",
                    )
                    all_embeddings.extend(result.embeddings)
                    break
                except Exception as exc:
                    if attempt == _MAX_RETRIES - 1:
                        raise
                    delay = _RETRY_BASE_DELAY * (2 ** attempt)
                    _log.warning("Embed retry %d after error: %s", attempt + 1, exc)
                    time.sleep(delay)
        return all_embeddings

    def _orphan_delete_ops(
        self,
        project: str,
        filesystem_files: set[str],
        new_chunk_counts: dict[str, int],
    ) -> list:
        db_files = self._coll.distinct("file_path", {"project": project})
        ops = []

        for fp in db_files:
            if fp not in filesystem_files:
                ops.append(DeleteMany({"project": project, "file_path": fp}))
            elif fp in new_chunk_counts:
                count = new_chunk_counts[fp]
                ops.append(DeleteMany({
                    "project": project,
                    "file_path": fp,
                    "chunk_index": {"$gte": count},
                }))

        return ops

    def _acquire_lock(self, project: str) -> bool:
        try:
            self._lock_collection.find_one_and_update(
                {"_id": project, "locked": False},
                {"$set": {"locked": True}},
                upsert=True,
            )
            # upsert succeeds (new doc) or updates existing unlocked doc
            return True
        except Exception:
            # Duplicate key = another process already locked
            return False

    def _release_lock(self, project: str) -> None:
        self._lock_collection.update_one(
            {"_id": project},
            {"$set": {"locked": False}},
        )

    def search(
        self,
        query_embedding: list[float],
        *,
        project: str | None = None,
        deliverable: str | None = None,
        doc_type: str | None = None,
        limit: int = 5,
        num_candidates: int = 100,
        min_score: float = 0.3,
    ) -> list[dict]:
        filter_doc: dict = {}
        if project:
            filter_doc["project"] = project
        if deliverable:
            filter_doc["deliverable"] = deliverable
        if doc_type:
            filter_doc["doc_type"] = doc_type

        pipeline = [
            {"$vectorSearch": {
                "index": "design_docs_index",
                "path": "embedding",
                "queryVector": query_embedding,
                "numCandidates": num_candidates,
                "limit": limit,
                **({"filter": filter_doc} if filter_doc else {}),
            }},
            {"$project": {
                "score": {"$meta": "vectorSearchScore"},
                "project": 1, "file_path": 1, "section_heading": 1,
                "content": 1, "doc_type": 1, "chunk_index": 1,
                "token_count": 1, "deliverable": 1,
            }},
        ]
        results = list(self._coll.aggregate(pipeline))
        return [r for r in results if r.get("score", 0) >= min_score]

    def get_status(self, project: str | None = None) -> dict:
        query: dict = {}
        if project:
            query["project"] = project

        chunk_count = self._coll.count_documents(query)

        last_indexed = None
        latest = self._coll.find_one(query, sort=[("indexed_at", -1)])
        if latest and latest.get("indexed_at"):
            last_indexed = latest["indexed_at"].isoformat()

        return {
            "chunk_count": chunk_count,
            "last_indexed": last_indexed,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd plugins/keel-ai/mcp-server && python -m pytest tests/test_indexer.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add plugins/keel-ai/mcp-server/indexer.py plugins/keel-ai/mcp-server/tests/test_indexer.py
git commit -m "feat(keel-ai): add indexer with embedding, upsert, and orphan cleanup"
```

---

### Task 4: MCP Server — Tool Definitions

**Files:**
- Create: `plugins/keel-ai/mcp-server/server.py`
- Create: `plugins/keel-ai/mcp-server/requirements.txt`
- Create: `plugins/keel-ai/mcp-server/tests/test_server.py`

The FastMCP server exposes three tools: `search`, `reindex`, `status`. Lazy initialization on first tool call.

- [ ] **Step 1: Write failing tests for the server**

```python
# plugins/keel-ai/mcp-server/tests/test_server.py
"""Tests for server — MCP tool definitions and lazy init."""

from __future__ import annotations

from unittest.mock import MagicMock, patch, AsyncMock

import pytest


class TestSearchTool:
    def test_search_requires_query(self) -> None:
        from server import _validate_search_args
        with pytest.raises(ValueError, match="query"):
            _validate_search_args(query="", project=None)

    def test_search_defaults(self) -> None:
        from server import _validate_search_args
        args = _validate_search_args(query="architecture", project=None)
        assert args["limit"] == 5
        assert args["min_score"] == 0.3


class TestReindexTool:
    def test_reindex_defaults_to_current_project(self) -> None:
        from server import _resolve_reindex_scope
        scope = _resolve_reindex_scope(project=None, full=False)
        assert scope["full"] is False

    def test_reindex_all_flag(self) -> None:
        from server import _resolve_reindex_scope
        scope = _resolve_reindex_scope(project="all", full=True)
        assert scope["all_projects"] is True
        assert scope["full"] is True


class TestLazyInit:
    def test_not_initialized_at_import(self) -> None:
        from server import _state
        # State should be defined but not initialized
        assert hasattr(_state, "initialized")

    @patch("server._do_initialize")
    def test_ensure_initialized_calls_init_once(self, mock_init) -> None:
        from server import _state, _ensure_initialized
        _state.initialized = False
        mock_init.return_value = None
        _ensure_initialized()
        mock_init.assert_called_once()

    @patch("server._do_initialize")
    def test_ensure_initialized_skips_when_done(self, mock_init) -> None:
        from server import _state, _ensure_initialized
        _state.initialized = True
        _ensure_initialized()
        mock_init.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd plugins/keel-ai/mcp-server && python -m pytest tests/test_server.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'server'`

- [ ] **Step 3: Create requirements.txt**

```
# plugins/keel-ai/mcp-server/requirements.txt
mcp>=1.20
pymongo>=4.7
voyageai>=0.3
```

- [ ] **Step 4: Implement the server module**

```python
# plugins/keel-ai/mcp-server/server.py
"""MCP server for keel-ai vector search.

Exposes three tools: search, reindex, status. Lazy initialization —
registers tools immediately, defers Docker/indexing to first tool call.
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import voyageai
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from atlas import AtlasLocal
from indexer import Indexer

_log = logging.getLogger(__name__)

_EMBED_MODEL = "voyage-3-lite"
_DEFAULT_GROVE_URL = (
    "https://grove-gateway-prod.azure-api.net/grove-foundry-prod/voyage/v1"
)


@dataclass
class _ServerState:
    initialized: bool = False
    init_error: str | None = None
    atlas: AtlasLocal = field(default_factory=AtlasLocal)
    indexer: Indexer | None = None
    voyage_client: voyageai.Client | None = None


_state = _ServerState()

mcp_server = FastMCP(
    name="keel-design-search",
    instructions="Semantic search over keel project design documents.",
)


def _do_initialize() -> None:
    grove_key = os.environ.get("GROVE_API_KEY")
    if not grove_key:
        _state.init_error = "GROVE_API_KEY environment variable not set"
        return

    grove_url = os.environ.get("GROVE_VOYAGE_BASE_URL", _DEFAULT_GROVE_URL)
    try:
        _state.voyage_client = voyageai.Client(api_key=grove_key, base_url=grove_url)
    except Exception as exc:
        _state.init_error = f"Failed to create Voyage client: {exc}"
        return

    err = _state.atlas.initialize()
    if err:
        _state.init_error = err
        return

    _state.indexer = Indexer(
        collection=_state.atlas.get_collection(),
        voyage_client=_state.voyage_client,
    )
    _state.initialized = True


def _ensure_initialized() -> str | None:
    if _state.initialized:
        return None
    if _state.init_error:
        return _state.init_error
    _do_initialize()
    return _state.init_error


def _validate_search_args(
    query: str,
    project: str | None,
    deliverable: str | None = None,
    doc_type: str | None = None,
    limit: int = 5,
    min_score: float = 0.3,
) -> dict:
    if not query.strip():
        raise ValueError("query must not be empty")
    return {
        "query": query.strip(),
        "project": project,
        "deliverable": deliverable,
        "doc_type": doc_type,
        "limit": limit,
        "min_score": min_score,
    }


def _resolve_reindex_scope(
    project: str | None = None,
    full: bool = False,
) -> dict:
    return {
        "all_projects": project == "all",
        "project": None if project == "all" else project,
        "full": full,
    }


def _detect_project_dir() -> Path | None:
    """Detect the keel project directory from CWD."""
    cwd = Path.cwd()
    # Walk up looking for project.toml
    for parent in [cwd, *cwd.parents]:
        if (parent / "project.toml").is_file():
            return parent
    return None


def _detect_project_name() -> str | None:
    project_dir = _detect_project_dir()
    if project_dir:
        return project_dir.name
    return None


@mcp_server.tool(
    name="search",
    description="Search design documents by semantic similarity.",
    annotations=ToolAnnotations(readOnlyHint=True),
)
def search(
    query: str,
    project: str | None = None,
    deliverable: str | None = None,
    doc_type: str | None = None,
    limit: int = 5,
    min_score: float = 0.3,
) -> dict:
    err = _ensure_initialized()
    if err:
        return {"error": err}

    try:
        args = _validate_search_args(query, project, deliverable, doc_type, limit, min_score)
    except ValueError as exc:
        return {"error": str(exc)}

    if args["project"] is None:
        args["project"] = _detect_project_name()

    try:
        result = _state.voyage_client.embed(
            [args["query"]], model=_EMBED_MODEL, input_type="query",
        )
        query_vec = result.embeddings[0]
    except Exception as exc:
        return {"error": f"Failed to embed query (Voyage unreachable): {exc}"}

    results = _state.indexer.search(
        query_vec,
        project=args["project"],
        deliverable=args["deliverable"],
        doc_type=args["doc_type"],
        limit=args["limit"],
        min_score=args["min_score"],
    )

    return {
        "results": [
            {
                "score": r.get("score"),
                "project": r.get("project"),
                "file_path": r.get("file_path"),
                "section_heading": r.get("section_heading"),
                "doc_type": r.get("doc_type"),
                "chunk_index": r.get("chunk_index"),
                "content": r.get("content"),
                "token_count": r.get("token_count"),
            }
            for r in results
        ],
        "count": len(results),
    }


@mcp_server.tool(
    name="reindex",
    description="Re-index design documents for the current or all projects.",
    annotations=ToolAnnotations(idempotentHint=True),
)
def reindex(
    project: str | None = None,
    full: bool = False,
) -> dict:
    err = _ensure_initialized()
    if err:
        return {"error": err}

    scope = _resolve_reindex_scope(project, full)

    if scope["all_projects"]:
        return _reindex_all(full=scope["full"])

    proj_name = scope["project"] or _detect_project_name()
    if not proj_name:
        return {"error": "Cannot detect project. Pass project name explicitly."}

    proj_dir = _detect_project_dir()
    if not proj_dir:
        return {"error": f"Cannot find project directory for {proj_name}"}

    return _state.indexer.reindex_project(proj_name, proj_dir, full=scope["full"])


def _reindex_all(full: bool) -> dict:
    from keel.workspace import iter_projects

    results = {}
    for name, _manifest, _phase in iter_projects():
        from keel.workspace import project_dir as get_project_dir
        proj_dir = get_project_dir(name)
        results[name] = _state.indexer.reindex_project(name, proj_dir, full=full)
    return {"projects": results}


@mcp_server.tool(
    name="status",
    description="Show vector search index status and chunk statistics.",
    annotations=ToolAnnotations(readOnlyHint=True),
)
def status(project: str | None = None) -> dict:
    atlas_health = _state.atlas.health()
    index_status = _state.atlas.vector_index_status()

    result = {
        "atlas_local": atlas_health,
        "vector_index": index_status,
    }

    if _state.initialized and _state.indexer:
        proj = project or _detect_project_name()
        result["stats"] = _state.indexer.get_status(proj)
    else:
        err = _state.init_error or "not initialized"
        result["stats"] = {"error": err}

    return result


if __name__ == "__main__":
    mcp_server.run(transport="stdio")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd plugins/keel-ai/mcp-server && python -m pytest tests/test_server.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add plugins/keel-ai/mcp-server/server.py plugins/keel-ai/mcp-server/requirements.txt plugins/keel-ai/mcp-server/tests/test_server.py
git commit -m "feat(keel-ai): add MCP server with search, reindex, status tools"
```

---

### Task 5: Plugin Configuration — hooks.json MCP Entry

**Files:**
- Modify: `plugins/keel-ai/hooks/hooks.json`

Add the `mcpServers` block so Claude Code starts the MCP server per session.

- [ ] **Step 1: Update hooks.json**

Replace the contents of `plugins/keel-ai/hooks/hooks.json` with:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|clear|compact",
        "hooks": [
          {
            "type": "command",
            "command": "\"${CLAUDE_PLUGIN_ROOT}/hooks/session-start\"",
            "async": false,
            "timeout": 15
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "\"${CLAUDE_PLUGIN_ROOT}/hooks/post-tool-use\"",
            "async": true,
            "timeout": 10
          }
        ]
      }
    ]
  },
  "mcpServers": {
    "keel-design-search": {
      "command": "python",
      "args": ["${CLAUDE_PLUGIN_ROOT}/mcp-server/server.py"],
      "env": {
        "GROVE_API_KEY": "${GROVE_API_KEY}",
        "GROVE_VOYAGE_BASE_URL": "${GROVE_VOYAGE_BASE_URL}"
      }
    }
  }
}
```

- [ ] **Step 2: Verify JSON is valid**

Run: `python -c "import json; json.load(open('plugins/keel-ai/hooks/hooks.json'))"`
Expected: No error

- [ ] **Step 3: Commit**

```bash
git add plugins/keel-ai/hooks/hooks.json
git commit -m "feat(keel-ai): register MCP server in hooks.json"
```

---

### Task 6: SessionStart Hook Update — Trigger Reindex

**Files:**
- Modify: `plugins/keel-ai/hooks/session-start`

After AGENTS.md generation, trigger an incremental reindex via the MCP server's `reindex` tool. Since the MCP server handles lazy init, we just need to ensure the hook signals that reindexing should happen. The simplest approach: add a note to the session context that tells Claude Code to call `reindex` after startup.

- [ ] **Step 1: Update session-start hook**

Replace the contents of `plugins/keel-ai/hooks/session-start` with:

```bash
#!/usr/bin/env bash
# keel-ai SessionStart hook
# 1. Generate/update AGENTS.md and CLAUDE.md at the project root.
# 2. Output the using-keel-ai skill as additional session context.
# 3. Signal that design document index should be refreshed.
set -euo pipefail

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"

# Check if keel CLI is available.
command -v keel &>/dev/null || exit 0

# Check if we're inside a keel project.
SHOW_OUTPUT=$(keel show --brief --json 2>/dev/null) || exit 0
printf '%s' "$SHOW_OUTPUT" | grep -q '"name"' || exit 0

# Generate AGENTS.md + CLAUDE.md at the project root.
PROJECT_ROOT=$(printf '%s' "$SHOW_OUTPUT" \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['path'])" 2>/dev/null || echo "")
if [ -n "$PROJECT_ROOT" ]; then
    keel ai generate --output "$PROJECT_ROOT" 2>/dev/null || true
fi

# Read the using-keel-ai skill and output as additional context.
SKILL_FILE="$PLUGIN_ROOT/skills/using-keel-ai/SKILL.md"
[ -f "$SKILL_FILE" ] || exit 0

# Strip frontmatter, append reindex hint, and emit as hook JSON.
SKILL_CONTENT=$(awk '/^---$/{if(++c==2){found=1;next}}found' "$SKILL_FILE")
REINDEX_HINT="

## Session Startup
If the keel-design-search MCP server is available, call the reindex tool
to ensure the design document index is fresh for this session."

printf '%s\n%s' "$SKILL_CONTENT" "$REINDEX_HINT" \
    | python3 "$HOOK_DIR/hook_output.py"
```

- [ ] **Step 2: Verify hook is executable and valid**

Run: `bash -n plugins/keel-ai/hooks/session-start && echo "syntax ok"`
Expected: `syntax ok`

- [ ] **Step 3: Commit**

```bash
git add plugins/keel-ai/hooks/session-start
git commit -m "feat(keel-ai): signal reindex in session-start hook context"
```

---

### Task 7: Design-Sync Agent Update — Use Search

**Files:**
- Modify: `plugins/keel-ai/agents/design-sync.md`

Update the design-sync agent to use the MCP `search` tool before reading full documents.

- [ ] **Step 1: Update design-sync agent**

Replace the contents of `plugins/keel-ai/agents/design-sync.md` with:

```markdown
---
name: design-sync
description: |
  Check for drift between design documents and implementation.
  Lifecycle-aware: reads milestone/task state to understand what changed.
model: sonnet
tools: Read, Grep, Glob, Bash, Edit, Write
maxTurns: 20
---

# Design Sync Agent

You review a project's implementation state and compare it against the
design documents. Your job: find drift and either fix it or report it.

## Input

You will receive:
- **mode**: `lightweight`, `thorough`, or `check`
- **scope**: project name and optional deliverable

## Process

### 1. Read project state

```bash
keel show <project> --json
keel ai show-config --json --project <project>
```

### 2. Search for relevant design context

If the `keel-design-search` MCP server is available, use the `search`
tool to find relevant design sections before reading full documents.
This is faster and more targeted than reading everything.

```
search(query="<describe what changed>", project="<project>")
```

Use the search results to identify which sections of the design are
relevant to the current changes. Then read only those sections in full
using the Read tool for precise editing.

If the MCP server is not available, fall back to reading the design
documents directly:
- `scope.md` — boundaries and goals
- `design.md` — current technical approach
- `decisions/*.md` — past decisions
- `.keel/phase` — current phase

### 3. Read implementation state

Check code worktrees for recent changes:
```bash
git log --oneline -20  # in each worktree
git diff --stat HEAD~5  # recent changes
```

Read milestone/task state:
```bash
keel milestone list --json --project <project>
keel task list --json --project <project>
```

### 4. Compare and identify drift

For each relevant section of design.md, check:
- Does the implementation match what was designed?
- Were there decisions made during implementation that aren't recorded?
- Are there open questions in the design that have been answered by the code?
- Did the scope change implicitly (features added/removed)?

### 5. Mode-specific behavior

**lightweight** (after task completion):
- Focus on the area the completed task touched
- Read the task's diff (files changed)
- Apply targeted updates to design.md
- Small, focused changes — not a full rewrite

**thorough** (after milestone completion):
- Review all changes across the milestone's tasks
- Full design.md review: architecture, components, data flow, API surface
- Update decisions/ if implicit decisions were made
- Flag scope drift: "Implementation added X not in scope.md"

**check** (report only):
- Produce a drift report but make no edits
- Present findings and ask the user what to update

### 6. After editing design documents

If you modified design documents, call the `reindex` tool to update the
search index:

```
reindex(project="<project>")
```

### 7. Output

**For lightweight and thorough modes:**
- Edit design documents directly
- Commit changes with message: `docs: design-sync (<mode>) after <context>`
- Report what was changed

**For check mode:**
Summarize as:
- **Aligned**: what matches the design
- **Drifted**: what diverges (and how)
- **Missing from design**: built but not designed
- **Missing from code**: designed but not built
- **Decisions to record**: implicit decisions

Lead with what drifted, not with what's aligned. Keep it concise.

### 8. Guardrails

- In lightweight/thorough mode: edit design.md and decisions/ only. Never edit scope.md — flag scope drift for the user to decide.
- Never remove content from design.md. Update, add, or mark as outdated.
- If you're unsure about a change, flag it in check mode instead of editing.
```

- [ ] **Step 2: Commit**

```bash
git add plugins/keel-ai/agents/design-sync.md
git commit -m "feat(keel-ai): design-sync agent uses search before reading full docs"
```

---

### Task 8: Scope-First Skill

**Files:**
- Create: `plugins/keel-ai/skills/scope-first/SKILL.md`
- Modify: `plugins/keel-ai/skills/using-keel-ai/SKILL.md`

The `/scope-first` skill provides a guided workflow: scope → design → plan → execute. It delegates to configurable skills from the AI config.

- [ ] **Step 1: Create the scope-first skill**

```markdown
---
name: scope-first
description: |
  Guided scope-first workflow: scope → design → plan → execute.
  Detects where you are in the flow and delegates to the right skill.
  Triggers on "scope-first", "start from scope", "guided workflow".
context: fork
---

# Scope-First Workflow

A guided workflow that ensures work follows the scope → design → plan → execute sequence.

## Detection

Detect where the user is in the workflow by checking which artifacts exist:

1. Does `scope.md` exist? If not → start with scoping
2. Does `design.md` exist? If not → start with design
3. Does `milestones.toml` exist with tasks? If not → start with planning
4. Are there active tasks? → continue execution

```bash
keel show --brief --json
```

## Workflow Steps

### Step 1: Scope

If `scope.md` doesn't exist or the user wants to start fresh:

Delegate to the configured scope skill. Check the project's AI config:

```bash
keel ai show-config --json
```

Look at `skills.scope` (default: `writing-scopes`). Run that skill.

### Step 2: Design

If `scope.md` exists but `design.md` doesn't:

Delegate to the configured design skill. Look at `skills.design` (default: `writing-tech-designs`).

Before starting, use the `search` tool (if available) to find similar designs or decisions across other projects:

```
search(query="<project description>", project="all")
```

This surfaces patterns and prior art that can inform the design.

### Step 3: Plan

If both `scope.md` and `design.md` exist but no milestones:

Delegate to the configured plan skill. Look at `skills.plan` (default: `superpowers:writing-plans`).

### Step 4: Execute

If milestones and tasks exist:

Work through tasks in order. After each task completion, run `/design-sync --lightweight` to keep documents current. After each milestone completion, run `/design-sync --thorough`.

## Cross-Project Context

When available, use the `search` tool to find relevant prior decisions or design patterns across all indexed projects. This is particularly useful during the scope and design phases to avoid reinventing solutions.

## Key Principle

Never skip a step. If the user asks to "just start coding" but there's no scope document, guide them through scoping first. The workflow exists to prevent wasted work.
```

- [ ] **Step 2: Update using-keel-ai skill**

Replace the contents of `plugins/keel-ai/skills/using-keel-ai/SKILL.md` with:

```markdown
---
name: using-keel-ai
description: |
  Routing skill for keel-ai. Loaded at session start inside keel projects.
  Establishes AI workflow instructions based on project configuration.
  Do not invoke directly — injected automatically by keel-ai's SessionStart hook.
---

# keel-ai: AI-Assisted Scope-First Development

You are working in a keel-managed project. keel-ai provides lifecycle-aware
AI assistance. An AGENTS.md file has been generated at the project root with
the current state (CLAUDE.md points to it).

## Available Skills

### /scope-first
Guided scope-first workflow: scope → design → plan → execute. Detects where
you are in the flow and delegates to the right skill. Use this when starting
new work or when unsure what step comes next.

### /design-sync
Check for drift between design documents and implementation. Three modes:

- `/design-sync` — auto-detect mode from context
- `/design-sync --lightweight` — targeted update (after task completion)
- `/design-sync --thorough` — full review (after milestone completion)
- `/design-sync --check` — report drift without making changes

### /generate
Regenerate the AGENTS.md and CLAUDE.md files mid-session. Use after making
changes to project configuration or structure.

## Vector Search

The `keel-design-search` MCP server provides semantic search across project
design documents. When available, use the `search` tool to find relevant
design sections, decisions, and patterns — both within this project and
across all indexed projects.

## Workflow

Follow the AI Workflow instructions in AGENTS.md. keel-ai's PostToolUse
hook automatically injects follow-up instructions when lifecycle transitions
happen (e.g. `keel task done`, `keel milestone done`). Follow those
instructions when they appear.

The default lifecycle triggers design-sync and code-review after task and
milestone completion. These can be customized in `[extensions.ai.triggers]`
in project.toml.

## Key Files

- `AGENTS.md` — generated artifact index + workflow instructions (regenerated each session)
- `CLAUDE.md` — pointer to AGENTS.md (for Claude Code compatibility)
- `project.toml` — project manifest with `[extensions.ai]` config
- `scope.md` — project scope (boundaries and success criteria)
- `design.md` — living technical design
- `decisions/` — one file per decision record
- `milestones.toml` — milestone and task tracking
```

- [ ] **Step 3: Commit**

```bash
git add plugins/keel-ai/skills/scope-first/SKILL.md plugins/keel-ai/skills/using-keel-ai/SKILL.md
git commit -m "feat(keel-ai): add /scope-first skill and update skill routing"
```

---

### Task 9: Custom Action Routing

**Files:**
- Modify: `plugins/keel-ai/hooks/match_triggers.py`
- Modify: `tests/hooks/test_match_triggers.py` (or create if doesn't exist)

The `match_triggers.py` already handles unknown actions with a generic fallback (lines 46-47). Verify this works correctly and add tests.

- [ ] **Step 1: Check if hook tests exist**

Run: `ls tests/hooks/`

- [ ] **Step 2: Write tests for custom action routing**

```python
# tests/hooks/test_match_triggers.py
# (Add to existing file if it exists, or create new)
"""Tests for match_triggers.py — custom action routing."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

MATCH_TRIGGERS = str(
    Path(__file__).resolve().parents[2] / "plugins" / "keel-ai" / "hooks" / "match_triggers.py"
)


def _run_match_triggers(config: dict, event: str, to_status: str) -> str | None:
    result = subprocess.run(
        [sys.executable, MATCH_TRIGGERS, event, to_status],
        input=json.dumps(config),
        capture_output=True, text=True, timeout=5,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return result.stdout.strip()


class TestKnownActions:
    def test_design_sync_produces_instruction(self) -> None:
        config = {
            "resolved_triggers": {
                "t1": {
                    "event": "task.status.post",
                    "when": {"to": "done"},
                    "action": "design-sync",
                    "mode": "lightweight",
                },
            },
        }
        output = _run_match_triggers(config, "task.status.post", "done")
        assert output is not None
        parsed = json.loads(output)
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        assert "/design-sync --lightweight" in ctx

    def test_code_review_produces_instruction(self) -> None:
        config = {
            "resolved_triggers": {
                "t1": {
                    "event": "task.status.post",
                    "when": {"to": "done"},
                    "action": "code-review",
                },
            },
        }
        output = _run_match_triggers(config, "task.status.post", "done")
        assert output is not None
        parsed = json.loads(output)
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        assert "code-reviewer" in ctx


class TestCustomActions:
    def test_unknown_action_produces_generic_instruction(self) -> None:
        config = {
            "resolved_triggers": {
                "t1": {
                    "event": "task.status.post",
                    "when": {"to": "done"},
                    "action": "my-custom-skill",
                },
            },
        }
        output = _run_match_triggers(config, "task.status.post", "done")
        assert output is not None
        parsed = json.loads(output)
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        assert "/my-custom-skill" in ctx

    def test_unknown_action_with_mode(self) -> None:
        config = {
            "resolved_triggers": {
                "t1": {
                    "event": "milestone.status.post",
                    "when": {"to": "done"},
                    "action": "deploy-check",
                    "mode": "full",
                },
            },
        }
        output = _run_match_triggers(config, "milestone.status.post", "done")
        assert output is not None
        parsed = json.loads(output)
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        assert "/deploy-check --full" in ctx

    def test_multiple_triggers_all_listed(self) -> None:
        config = {
            "resolved_triggers": {
                "t1": {
                    "event": "task.status.post",
                    "when": {"to": "done"},
                    "action": "design-sync",
                    "mode": "lightweight",
                },
                "t2": {
                    "event": "task.status.post",
                    "when": {"to": "done"},
                    "action": "my-lint",
                },
            },
        }
        output = _run_match_triggers(config, "task.status.post", "done")
        assert output is not None
        parsed = json.loads(output)
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        assert "/design-sync" in ctx
        assert "/my-lint" in ctx


class TestNoMatch:
    def test_no_matching_triggers_exits_silently(self) -> None:
        config = {
            "resolved_triggers": {
                "t1": {
                    "event": "task.status.post",
                    "when": {"to": "done"},
                    "action": "design-sync",
                },
            },
        }
        output = _run_match_triggers(config, "milestone.status.post", "done")
        assert output is None

    def test_wrong_status_no_match(self) -> None:
        config = {
            "resolved_triggers": {
                "t1": {
                    "event": "task.status.post",
                    "when": {"to": "done"},
                    "action": "design-sync",
                },
            },
        }
        output = _run_match_triggers(config, "task.status.post", "active")
        assert output is None
```

- [ ] **Step 3: Run tests to verify they pass**

The existing `match_triggers.py` already handles custom actions (lines 46-47):
```python
mode = f" --{trigger['mode']}" if trigger.get("mode") else ""
matching.append(f"Run /{action}{mode}")
```

Run: `python -m pytest tests/hooks/test_match_triggers.py -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/hooks/test_match_triggers.py
git commit -m "test(keel-ai): add tests for custom action routing in match_triggers"
```

---

### Task 10: Plugin Version Bump and Integration Verification

**Files:**
- Modify: `plugins/keel-ai/.claude-plugin/plugin.json`

- [ ] **Step 1: Bump plugin version**

Update `plugins/keel-ai/.claude-plugin/plugin.json`:

```json
{
  "name": "keel-ai",
  "version": "0.0.2",
  "description": "AI-assisted scope-first development for keel-managed projects",
  "author": {
    "name": "Andrei Matei"
  },
  "repository": "https://github.com/andmatei/keel",
  "license": "MIT",
  "keywords": [
    "keel",
    "ai",
    "design-sync",
    "scope-first",
    "vector-search",
    "claude-code"
  ]
}
```

- [ ] **Step 2: Verify all keel-cli tests still pass**

Run: `cd /Users/andrei.matei/projects/keel && python -m pytest tests/ -q`
Expected: All existing tests PASS (no regressions)

- [ ] **Step 3: Verify MCP server tests pass**

Run: `cd plugins/keel-ai/mcp-server && pip install pymongo voyageai && python -m pytest tests/ -v`
Expected: All MCP server tests PASS

- [ ] **Step 4: Verify plugin file structure**

Run: `find plugins/keel-ai -type f | sort`
Expected output:
```
plugins/keel-ai/.claude-plugin/plugin.json
plugins/keel-ai/agents/design-sync.md
plugins/keel-ai/hooks/hook_output.py
plugins/keel-ai/hooks/hooks.json
plugins/keel-ai/hooks/match_triggers.py
plugins/keel-ai/hooks/post-tool-use
plugins/keel-ai/hooks/session-start
plugins/keel-ai/mcp-server/atlas.py
plugins/keel-ai/mcp-server/chunker.py
plugins/keel-ai/mcp-server/docker-compose.yml
plugins/keel-ai/mcp-server/indexer.py
plugins/keel-ai/mcp-server/requirements.txt
plugins/keel-ai/mcp-server/server.py
plugins/keel-ai/mcp-server/tests/__init__.py
plugins/keel-ai/mcp-server/tests/test_atlas.py
plugins/keel-ai/mcp-server/tests/test_chunker.py
plugins/keel-ai/mcp-server/tests/test_indexer.py
plugins/keel-ai/mcp-server/tests/test_server.py
plugins/keel-ai/skills/design-sync/SKILL.md
plugins/keel-ai/skills/generate/SKILL.md
plugins/keel-ai/skills/scope-first/SKILL.md
plugins/keel-ai/skills/using-keel-ai/SKILL.md
```

- [ ] **Step 5: Commit**

```bash
git add plugins/keel-ai/.claude-plugin/plugin.json
git commit -m "chore(keel-ai): bump plugin version to 0.0.2 for Phase 2"
```
