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
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='[{"State":{"Health":{"Status":"healthy"}}}]',
        )
        a = AtlasLocal()
        a._ensure_docker_running()
        calls = [c.args[0] for c in mock_run.call_args_list]
        assert any("inspect" in str(c) for c in calls)
        assert not any("compose" in str(c) and "up" in str(c) for c in calls)

    @patch("atlas.subprocess.run")
    def test_runs_compose_up_when_not_healthy(self, mock_run) -> None:
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
    @patch.object(AtlasLocal, "_wait_for_index_ready")
    def test_creates_vector_index_when_missing(self, mock_wait) -> None:
        a = AtlasLocal()
        mock_coll = MagicMock()
        mock_coll.list_search_indexes.return_value = []
        a._ensure_vector_index(mock_coll)
        mock_coll.create_search_index.assert_called_once()

    def test_skips_vector_index_when_exists(self) -> None:
        a = AtlasLocal()
        mock_coll = MagicMock()
        mock_coll.list_search_indexes.return_value = [
            {"name": VECTOR_INDEX_NAME, "status": "READY"},
        ]
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
