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
    permanent_error: bool = False
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
        _state.permanent_error = True
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
    if _state.permanent_error:
        return _state.init_error
    _state.init_error = None
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
    cwd = Path.cwd()
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
    annotations=ToolAnnotations(idempotentHint=True, destructiveHint=True),
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
        result["stats"] = _state.indexer.get_status(proj, project_dir=_detect_project_dir())
    else:
        err = _state.init_error or "not initialized"
        result["stats"] = {"error": err}

    return result


if __name__ == "__main__":
    mcp_server.run(transport="stdio")
