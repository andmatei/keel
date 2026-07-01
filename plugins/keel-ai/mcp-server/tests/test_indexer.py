"""Tests for indexer — embedding, upsert, orphan cleanup."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

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
        result = idx._prepare_for_embedding("Some content", project="my-proj", doc_type="design")
        assert result.startswith("[project: my-proj] [type: design]")
        assert "Some content" in result


class TestIndexerReindex:
    def test_discovers_current_keel_layout(self, tmp_path) -> None:
        (tmp_path / "scope.md").write_text("# Scope\n")
        (tmp_path / "design.md").write_text("# Design\n")
        (tmp_path / "milestones.toml").write_text("")
        (tmp_path / "decisions").mkdir()
        (tmp_path / "decisions" / "2026-01-01-choice.md").write_text("# Choice\n")

        idx = Indexer(collection=MagicMock(), voyage_client=MagicMock())

        files = {(path, doc_type) for path, doc_type, _abs in idx._discover_files(tmp_path)}
        assert files == {
            ("scope.md", "scope"),
            ("design.md", "design"),
            ("milestones.toml", "milestones"),
            ("decisions/2026-01-01-choice.md", "decision"),
        }

    @patch("indexer.voyageai")
    def test_skips_unchanged_chunks(self, mock_voyage) -> None:
        mock_coll = MagicMock()
        mock_voyage_client = MagicMock()
        mock_voyage.Client.return_value = mock_voyage_client

        idx = Indexer(collection=mock_coll, voyage_client=mock_voyage_client)

        mock_coll.find_one.return_value = {"content_hash": "sha256:abc123"}
        assert idx._chunk_unchanged("proj", "design.md", 0, "sha256:abc123") is True

    @patch("indexer.voyageai")
    def test_does_not_skip_changed_chunks(self, mock_voyage) -> None:
        mock_coll = MagicMock()
        mock_voyage_client = MagicMock()
        mock_voyage.Client.return_value = mock_voyage_client

        idx = Indexer(collection=mock_coll, voyage_client=mock_voyage_client)

        mock_coll.find_one.return_value = {"content_hash": "sha256:old"}
        assert idx._chunk_unchanged("proj", "design.md", 0, "sha256:new") is False

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
            ["hello world"],
            model="voyage-3-lite",
            input_type="document",
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

    @patch("indexer.voyageai")
    def test_deletes_excess_chunks_for_shrunk_files(self, mock_voyage) -> None:
        mock_coll = MagicMock()
        mock_voyage_client = MagicMock()

        idx = Indexer(collection=mock_coll, voyage_client=mock_voyage_client)

        mock_coll.distinct.return_value = ["design.md"]
        filesystem_files = {"design.md"}
        new_chunk_counts = {"design.md": 2}

        ops = idx._orphan_delete_ops("my-proj", filesystem_files, new_chunk_counts)
        assert len(ops) >= 1


class TestSearch:
    @patch("indexer.voyageai")
    def test_builds_pipeline_with_no_filters(self, mock_voyage) -> None:
        mock_coll = MagicMock()
        mock_voyage_client = MagicMock()
        idx = Indexer(collection=mock_coll, voyage_client=mock_voyage_client)

        mock_coll.aggregate.return_value = [
            {"score": 0.9, "project": "p", "content": "hello"},
        ]

        idx.search([0.1] * 512, limit=3)
        pipeline = mock_coll.aggregate.call_args[0][0]
        vs = pipeline[0]["$vectorSearch"]
        assert vs["limit"] == 3
        assert "filter" not in vs

    @patch("indexer.voyageai")
    def test_builds_pipeline_with_project_filter(self, mock_voyage) -> None:
        mock_coll = MagicMock()
        mock_voyage_client = MagicMock()
        idx = Indexer(collection=mock_coll, voyage_client=mock_voyage_client)

        mock_coll.aggregate.return_value = []
        idx.search([0.1] * 512, project="my-proj", doc_type="design")
        pipeline = mock_coll.aggregate.call_args[0][0]
        vs = pipeline[0]["$vectorSearch"]
        assert vs["filter"]["project"] == "my-proj"
        assert vs["filter"]["doc_type"] == "design"

    @patch("indexer.voyageai")
    def test_filters_results_below_min_score(self, mock_voyage) -> None:
        mock_coll = MagicMock()
        mock_voyage_client = MagicMock()
        idx = Indexer(collection=mock_coll, voyage_client=mock_voyage_client)

        mock_coll.aggregate.return_value = [
            {"score": 0.9, "content": "good"},
            {"score": 0.1, "content": "bad"},
        ]
        results = idx.search([0.1] * 512, min_score=0.3)
        assert len(results) == 1
        assert results[0]["content"] == "good"


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
        from pymongo.errors import DuplicateKeyError

        lock_coll.find_one_and_update.side_effect = DuplicateKeyError("duplicate key")
        idx._lock_collection = lock_coll

        assert idx._acquire_lock("proj") is False
