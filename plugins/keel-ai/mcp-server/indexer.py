"""Document indexer: chunking, embedding, upsert, orphan cleanup."""

from __future__ import annotations

import logging
import subprocess
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import voyageai
from atlas import VECTOR_INDEX_NAME
from chunker import chunk_document, content_hash, prepend_metadata
from pymongo import DeleteMany, UpdateOne
from pymongo.collection import Collection

_log = logging.getLogger(__name__)

_CHARS_PER_TOKEN = 4
_MAX_BATCH_COUNT = 128
_MAX_BATCH_TOKENS = 320_000
_EMBED_MODEL = "voyage-3-lite"
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0
_LOCK_TTL = timedelta(minutes=10)

_DOC_PATTERNS: dict[str, list[str]] = {
    "scope": ["scope.md"],
    "design": ["design.md"],
    "milestones": ["milestones.toml"],
}


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
            capture_output=True,
            text=True,
            timeout=5,
            cwd=project_dir,
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
        files = self._discover_files(project_dir)
        git_h = _git_hash(project_dir)
        now = datetime.now(UTC)

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

            file_hash = content_hash(content)
            chunks = chunk_document(content, file_path=file_path, doc_type=doc_type)
            new_chunk_counts[file_path] = len(chunks)

            if not chunks:
                continue

            texts_to_embed: list[str] = []
            chunk_data: list[dict] = []

            for chunk in chunks:
                c_hash = content_hash(chunk["content"])
                if not full and self._chunk_unchanged(
                    project_name, file_path, chunk["chunk_index"], c_hash
                ):
                    skipped += 1
                    continue

                embed_text = self._prepare_for_embedding(
                    chunk["content"],
                    project=project_name,
                    doc_type=doc_type,
                )
                texts_to_embed.append(embed_text)
                chunk_data.append(
                    {
                        **chunk,
                        "project": project_name,
                        "deliverable": deliverable,
                        "doc_type": doc_type,
                        "file_path": file_path,
                        "content_hash": c_hash,
                        "file_content_hash": file_hash,
                        "token_count": len(chunk["content"]) // _CHARS_PER_TOKEN,
                        "git_hash": git_h,
                        "indexed_at": now,
                    }
                )

            if not texts_to_embed:
                continue

            try:
                embeddings = self._embed_texts(texts_to_embed)
            except Exception as exc:
                _log.error("Embedding failed for %s: %s", file_path, exc)
                failed_files.append(file_path)
                continue

            ops = []
            for cd, emb in zip(chunk_data, embeddings, strict=True):
                cd["embedding"] = emb
                ops.append(
                    UpdateOne(
                        {
                            "project": cd["project"],
                            "file_path": cd["file_path"],
                            "chunk_index": cd["chunk_index"],
                        },
                        {"$set": cd},
                        upsert=True,
                    )
                )
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
        self,
        project: str,
        file_path: str,
        chunk_index: int,
        new_hash: str,
    ) -> bool:
        existing = self._coll.find_one(
            {"project": project, "file_path": file_path, "chunk_index": chunk_index},
            {"content_hash": 1},
        )
        return existing is not None and existing.get("content_hash") == new_hash

    def _prepare_for_embedding(self, text: str, *, project: str, doc_type: str) -> str:
        return prepend_metadata(text, project=project, doc_type=doc_type)

    def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        all_embeddings: list[list[float]] = []
        for batch in _batch_by_tokens(texts):
            for attempt in range(_MAX_RETRIES):
                try:
                    result = self._voyage.embed(
                        batch,
                        model=_EMBED_MODEL,
                        input_type="document",
                    )
                    all_embeddings.extend(result.embeddings)
                    break
                except Exception as exc:
                    if attempt == _MAX_RETRIES - 1:
                        raise
                    delay = _RETRY_BASE_DELAY * (2**attempt)
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
                ops.append(
                    DeleteMany(
                        {
                            "project": project,
                            "file_path": fp,
                            "chunk_index": {"$gte": count},
                        }
                    )
                )

        return ops

    def _acquire_lock(self, project: str) -> bool:
        from pymongo.errors import DuplicateKeyError

        now = datetime.now(UTC)
        stale_cutoff = now - _LOCK_TTL

        # First, recover any stale locks older than TTL
        self._lock_collection.update_many(
            {"locked": True, "locked_at": {"$lt": stale_cutoff}},
            {"$set": {"locked": False}},
        )

        try:
            self._lock_collection.find_one_and_update(
                {"_id": project, "locked": False},
                {"$set": {"locked": True, "locked_at": now}},
                upsert=True,
            )
            return True
        except DuplicateKeyError:
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
            {
                "$vectorSearch": {
                    "index": VECTOR_INDEX_NAME,
                    "path": "embedding",
                    "queryVector": query_embedding,
                    "numCandidates": num_candidates,
                    "limit": limit,
                    **({"filter": filter_doc} if filter_doc else {}),
                }
            },
            {
                "$project": {
                    "score": {"$meta": "vectorSearchScore"},
                    "project": 1,
                    "file_path": 1,
                    "section_heading": 1,
                    "content": 1,
                    "doc_type": 1,
                    "chunk_index": 1,
                    "token_count": 1,
                    "deliverable": 1,
                }
            },
        ]
        results = list(self._coll.aggregate(pipeline))
        return [r for r in results if r.get("score", 0) >= min_score]

    def get_status(self, project: str | None = None, project_dir: Path | None = None) -> dict:
        query: dict = {}
        if project:
            query["project"] = project

        chunk_count = self._coll.count_documents(query)

        last_indexed = None
        latest = self._coll.find_one(query, sort=[("indexed_at", -1)])
        if latest and latest.get("indexed_at"):
            last_indexed = latest["indexed_at"].isoformat()

        stale_files = 0
        if project and project_dir:
            files = self._discover_files(project_dir)
            for file_path, _doc_type, abs_path in files:
                try:
                    current = content_hash(abs_path.read_text(encoding="utf-8"))
                except Exception:
                    continue
                existing = self._coll.find_one(
                    {"project": project, "file_path": file_path, "chunk_index": 0},
                    {"file_content_hash": 1},
                )
                if not existing or existing.get("file_content_hash") != current:
                    stale_files += 1

        return {
            "chunk_count": chunk_count,
            "last_indexed": last_indexed,
            "stale_files": stale_files,
        }
