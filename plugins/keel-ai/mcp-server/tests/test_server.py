"""Tests for server — MCP tool definitions and lazy init."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

import pytest


@pytest.fixture(autouse=True)
def _reset_server_state():
    from server import _state, _ServerState
    from atlas import AtlasLocal
    original = _ServerState()
    yield
    _state.initialized = False
    _state.init_error = None
    _state.permanent_error = False
    _state.atlas = AtlasLocal()
    _state.indexer = None
    _state.voyage_client = None


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


class TestSearchHandler:
    @patch("server._detect_project_name", return_value="my-proj")
    @patch("server._ensure_initialized", return_value=None)
    def test_search_returns_results(self, mock_init, mock_detect) -> None:
        from server import search, _state
        mock_voyage = MagicMock()
        mock_voyage.embed.return_value = MagicMock(embeddings=[[0.1] * 512])
        _state.voyage_client = mock_voyage

        mock_indexer = MagicMock()
        mock_indexer.search.return_value = [
            {"score": 0.9, "project": "my-proj", "file_path": "design.md",
             "section_heading": "Arch", "doc_type": "design", "chunk_index": 0,
             "content": "hello", "token_count": 10},
        ]
        _state.indexer = mock_indexer
        _state.initialized = True

        result = search(query="architecture")
        assert result["count"] == 1
        assert result["results"][0]["content"] == "hello"

    @patch("server._ensure_initialized", return_value="GROVE_API_KEY not set")
    def test_search_returns_error_on_init_failure(self, mock_init) -> None:
        from server import search
        result = search(query="test")
        assert "error" in result

    @patch("server._ensure_initialized", return_value=None)
    def test_search_rejects_empty_query(self, mock_init) -> None:
        from server import search
        result = search(query="   ")
        assert "error" in result


class TestReindexHandler:
    @patch("server._detect_project_name", return_value="my-proj")
    @patch("server._detect_project_dir", return_value=Path("/fake"))
    @patch("server._ensure_initialized", return_value=None)
    def test_reindex_calls_indexer(self, mock_init, mock_dir, mock_name) -> None:
        from server import reindex, _state
        mock_indexer = MagicMock()
        mock_indexer.reindex_project.return_value = {"status": "ok", "indexed": 3}
        _state.indexer = mock_indexer
        _state.initialized = True

        result = reindex()
        assert result["status"] == "ok"
        mock_indexer.reindex_project.assert_called_once()

    @patch("server._detect_project_name", return_value=None)
    @patch("server._ensure_initialized", return_value=None)
    def test_reindex_errors_when_no_project_detected(self, mock_init, mock_name) -> None:
        from server import reindex
        result = reindex()
        assert "error" in result


class TestStatusHandler:
    def test_status_shows_atlas_health(self) -> None:
        from server import status, _state
        _state.initialized = False
        _state.init_error = "not ready"
        mock_atlas = MagicMock()
        mock_atlas.health.return_value = {"connected": False}
        mock_atlas.vector_index_status.return_value = "NOT_FOUND"
        _state.atlas = mock_atlas

        result = status()
        assert result["atlas_local"] == {"connected": False}
        assert result["vector_index"] == "NOT_FOUND"
        assert "error" in result["stats"]


class TestLazyInit:
    def test_not_initialized_at_import(self) -> None:
        from server import _state
        assert hasattr(_state, "initialized")

    @patch("server._do_initialize")
    def test_ensure_initialized_calls_init_once(self, mock_init) -> None:
        from server import _state, _ensure_initialized
        _state.initialized = False
        _state.init_error = None
        mock_init.return_value = None
        _ensure_initialized()
        mock_init.assert_called_once()

    @patch("server._do_initialize")
    def test_ensure_initialized_skips_when_done(self, mock_init) -> None:
        from server import _state, _ensure_initialized
        _state.initialized = True
        _ensure_initialized()
        mock_init.assert_not_called()
