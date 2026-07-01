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
            result = subprocess.run(
                ["docker", "compose", "-f", self._compose_file, "up", "-d", "--wait"],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode != 0:
                return f"docker compose up failed (exit {result.returncode}): {result.stderr.strip()}"
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
