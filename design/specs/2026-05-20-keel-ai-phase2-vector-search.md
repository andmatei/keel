---
date: 2026-05-20
title: "keel-ai Phase 2: Vector-powered design intelligence"
status: draft
depends-on: 2026-05-14-keel-ai-plugin.md
---

# keel-ai Phase 2: Vector-powered design intelligence

## Summary

Add semantic vector search to keel-ai so the design-sync agent (and
other skills) can find relevant design document sections instead of
reading everything. An MCP server indexes project design artifacts into
Atlas local with Voyage embeddings, exposing `search`, `reindex`, and
`status` tools.

This also covers the remaining Phase 2 items from the original spec:
the `/scope-first` skill and custom action routing in triggers.

## Architecture

Three components:

### 1. Atlas local (Docker Compose)

A MongoDB instance with vector search, shared across all projects and
Claude Code sessions. One database (`keel_ai`), one collection
(`doc_chunks`). Persistent volume survives container stop/start.

### 2. MCP server (`keel-ai/mcp-server/`)

A Python process started by Claude Code per session via `.mcp.json`.
Connects to Atlas local at `localhost:27117`. Exposes three tools:
`search`, `reindex`, `status`.

**Lazy initialization**: The server starts immediately and registers
tools without blocking on Atlas local or indexing. Docker Compose and
reindexing are triggered lazily on the first tool call that needs
them. This avoids blocking Claude Code's session startup (MCP servers
must be ready within seconds). If Atlas local is still starting when a
tool is called, the tool returns a clear "warming up" message rather
than hanging.

Requires **pymongo >= 4.7** (for `create_search_index()`).

On process exit, the server closes pymongo connections via `atexit`
handler. Uses `serverSelectionTimeoutMS=5000` so orphaned servers
don't block indefinitely on a stopped container.

### 3. Indexer (module inside MCP server)

Chunks documents by type-specific strategies, embeds with Voyage,
upserts to Atlas local. Tracks content hashes to skip unchanged
chunks. Handles orphan cleanup for deleted/renamed files.

### Data flow

```
Session start -> MCP server starts -> ensures Atlas local -> incremental reindex
Design-sync completes -> agent calls reindex tool -> updated chunks
Agent needs context -> calls search tool -> vector similarity -> ranked chunks
```

### Why not bridge to keel-cli?

The MCP server owns the full indexing and search lifecycle. Splitting
indexing into keel-cli and search into the MCP server creates split
brain. The MCP server is the right home because: (a) it runs during
the session when search is needed, (b) it can trigger re-indexing
after design-sync without subprocess overhead, (c) the tool interface
stays stable regardless of internal changes.

## Collection schema

Database: `keel_ai`. Collection: `doc_chunks`.

```javascript
{
  project: "my-project",
  deliverable: null,               // null = project-level
  doc_type: "design",              // "scope" | "design" | "decision" | "milestones"
  file_path: "design.md",          // relative to project root
  section_heading: "## Architecture",
  chunk_index: 0,                  // ordinal position in file
  parent_heading: null,            // for ### chunks nested under ##
  content: "...",                  // raw text
  token_count: 342,               // for context window packing
  content_hash: "sha256:abc123",  // skip re-embedding unchanged chunks
  embedding: [float x 512],       // voyage-3-lite
  git_hash: "9a6c98c",           // freshness signal
  indexed_at: ISODate()           // operational tracking
}
```

**Upsert key**: `(project, file_path, chunk_index)`. Makes concurrent
reindexes on different projects conflict-free.

**Vector search index**: Created programmatically on first startup via
`collection.create_search_index()` using `SearchIndexModel` from
`pymongo.operations`. 512 dimensions (voyage-3-lite), cosine
similarity. The index definition must declare filter fields for
pre-filtering in `$vectorSearch`:

```python
SearchIndexModel(
    name="design_docs_index",
    type="vectorSearch",
    definition={
        "fields": [
            {"path": "embedding", "type": "vector",
             "numDimensions": 512, "similarity": "cosine"},
            {"path": "project", "type": "filter"},
            {"path": "deliverable", "type": "filter"},
            {"path": "doc_type", "type": "filter"},
        ]
    },
)
```

On Atlas local, vector search indexes build **asynchronously**. After
creation, poll `list_search_indexes()` until status is `READY` before
serving searches.

**Compound indexes** for non-vector operations:
- `{project: 1, file_path: 1, chunk_index: 1}` — covers upserts and
  orphan cleanup queries.
- `{project: 1, doc_type: 1}` — covers filtered status queries.

## Chunking strategy

Different document types get different treatment.

### Markdown files (scope.md, design.md)

Split on `## ` headings. Each section = one chunk with 1-2 sentence
trailing overlap from the next section (prevents retrieval misses for
concepts spanning section boundaries). If a section exceeds ~800
tokens, sub-split on `### ` first, then paragraph boundaries.
`parent_heading` tracks the `##` parent for sub-split chunks. Strip
YAML frontmatter (`---` blocks) before chunking. Skip empty sections
(heading with no body).

### decisions/*.md

Each file is one chunk. Decisions are short, self-contained documents.

### milestones.toml

Parse TOML, serialize each milestone as a text block:
`"Milestone: Foundation | Status: active | Tasks: 3/5 done | Description: ..."`.
Raw TOML fragments embed poorly; structured text embeds well.

### No-heading documents

Fallback: treat entire file as one chunk if under 800 tokens, otherwise
split on paragraph boundaries.

### Metadata prepending

Prepend project/type context to chunk text before embedding:
`"[project: ipa-skills] [type: decision] ## Use Atlas Vector Search\n\n..."`.
This is a well-established technique with Voyage models that improves
retrieval when queries mention a project or document type.

### Edge cases

- Empty docs: skip indexing (zero-content embeddings are noise).
- Heading-only sections (no body): skip.
- Binary files or non-UTF8: filter on extension allowlist (`.md`,
  `.toml`) before indexing.
- Very long sections: sub-split to stay under 800 tokens.

## Embedding model

**voyage-3-lite** (512 dimensions). Sufficient for a sub-1000-chunk
corpus. Cheaper and faster than voyage-3 (1024-dim).

Use `input_type="document"` at index time and `input_type="query"` at
search time. These flags meaningfully improve retrieval quality with
Voyage models.

**Access via Grove**: All Voyage API calls go through Grove, MongoDB's
internal AI gateway (`grove-gateway-prod.azure-api.net`). Grove
provides compliance, cost tracking, and enterprise rate limits. The
`voyageai` Python client is configured with a Grove-provided base URL
and API key:

```python
import voyageai

client = voyageai.Client(
    api_key=os.environ["GROVE_API_KEY"],
    base_url=os.environ.get(
        "GROVE_VOYAGE_BASE_URL",
        "https://grove-gateway-prod.azure-api.net/grove-foundry-prod/voyage/v1",
    ),
)
```

If the `voyageai` client doesn't support Grove's `api-key` header
convention natively, use a thin `httpx` transport wrapper that maps
the auth header. The Grove base URL and exact header requirements
should be verified against the provisioned request in Grove's UI
(usage snippets are model-specific).

**Batch limits**: Voyage allows 128 texts per batch call but also
enforces a 320K total token limit per batch. The indexer must check
cumulative token count per batch, not just chunk count, to avoid
silent truncation or 400 errors.

## MCP server tools

### search

```
search(query, project?, deliverable?, doc_type?, limit?, min_score?)
```

Embeds query with Voyage (`input_type="query"`). Runs `$vectorSearch`
aggregation with optional pre-filters on project, deliverable,
doc_type. Default `limit=5`, `numCandidates=100`, `min_score=0.3`.
Returns chunks with score, metadata, content, and token_count.

The `min_score` parameter filters out low-relevance chunks that would
pollute the agent's context. Default of 0.3 is a starting point;
tune empirically.

MCP tool annotation: `readOnlyHint=true`.

**Error handling**: If Voyage API is unreachable at search time
(embedding the query fails), return a structured MCP error with a
clear message rather than hanging or crashing. The agent can fall
back to direct file reads.

The `$vectorSearch` pipeline:

```python
collection.aggregate([
    {"$vectorSearch": {
        "index": "design_docs_index",
        "path": "embedding",
        "queryVector": query_vec,
        "numCandidates": 100,
        "limit": 5,
        "filter": {"project": project}
    }},
    {"$project": {
        "score": {"$meta": "vectorSearchScore"},
        "project": 1, "file_path": 1, "section_heading": 1,
        "content": 1, "doc_type": 1, "chunk_index": 1,
        "token_count": 1
    }}
])
```

### reindex

```
reindex(project?, full?)
```

No args: incremental reindex for current project (compare content
hashes, skip unchanged chunks). `project="all"`: reindex all projects.
`full=true`: wipe and rebuild (ignore hashes).

Orphan cleanup runs at the end of each project reindex. Collect all
delete operations, then execute as a single `bulk_write` for
atomicity:
1. Collect all `file_path` values in the collection for that project.
2. Diff against the actual filesystem.
3. Delete chunks for removed files and chunks where `chunk_index >=
   new_chunk_count` for files that still exist (handles removed
   sections).

Same-project concurrent reindex prevented via an atomic lock:
`find_one_and_update({"_id": project, "locked": False},
{"$set": {"locked": True}}, upsert=True)`. Returns `None` if another
reindex is running. Release with `{"$set": {"locked": False}}` in a
`try/finally`.

MCP tool annotation: `idempotentHint=true`. With `full=true`:
`destructiveHint=true`.

Voyage batching: up to 128 chunks per API call, respecting the 320K
token-per-batch limit. Retry with exponential backoff (3 attempts).
On persistent failure, return partial success with a list of failed
files so the user knows search results may be incomplete.

### status

```
status(project?)
```

Returns chunk count, last indexed time, stale file count, Atlas local
connection health, and vector index status (READY/BUILDING). Reports
degraded state clearly (e.g., "Atlas local not running", "index
building") rather than throwing errors.

MCP tool annotation: `readOnlyHint=true`.

## Indexing triggers

Three triggers, matching the agreed-upon "Option B + on-demand" model:

1. **Session start** (lazy): MCP server registers tools immediately.
   Incremental reindex runs on the first `search` or `reindex` call,
   not during server init. This avoids blocking session startup.
2. **After design-sync** (automatic): the design-sync agent calls
   `reindex` after editing design documents. Updated chunks are
   immediately available for subsequent searches.
3. **On-demand** (manual): user or any automation calls the `reindex`
   tool directly. Extensible endpoint for a future daemon or file
   watcher.

## Docker infrastructure

`docker-compose.yml` in `plugins/keel-ai/mcp-server/`:

```yaml
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

- **Port 27117**: avoids collision with any local mongod or other Atlas
  local instances.
- **Named volume** `keel-atlas-data`: persists across stop/start. Only
  `docker compose down -v` wipes data.
- **Container name** `keel-atlas-local`: stable, predictable.
- MCP server checks container health before operations. Runs
  `docker compose up -d` only if container is not already healthy.

### Performance

- First ever cold start (image pull): 30-60 seconds.
- Container stopped then started: 5-10 seconds.
- Indexing 10 projects x 10 docs x 5 chunks = 500 chunks: ~2-3 seconds
  (4 Voyage API batches at ~400ms each).
- Atlas local idles at ~200MB RAM. Vector data for a few hundred 512-dim
  vectors: < 1MB.

### Multi-process safety

Multiple Claude Code sessions spawn separate MCP server processes, all
connecting to the same Atlas local. pymongo handles concurrent
connections natively. Upsert keyed on `(project, file_path,
chunk_index)` makes different-project reindexes conflict-free.
Same-project concurrent reindex uses a lock document (see reindex
section).

## Integration with existing keel-ai

### MCP configuration

The plugin declares its MCP server in `hooks.json` (same file that
declares hook entries), using `${CLAUDE_PLUGIN_ROOT}` — the
environment variable Claude Code sets for every plugin process:

```json
{
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

This is the same `${CLAUDE_PLUGIN_ROOT}` already used by the hook
commands. No path resolution logic needed in the MCP server itself.
`GROVE_VOYAGE_BASE_URL` is optional — defaults to the standard Grove
Voyage endpoint if not set.

### Design-sync agent

Updated to call `search` before reading full documents. Finds the
relevant sections to focus on instead of reading everything. The agent
still has Read/Edit/Write tools for the actual updates — search
provides targeted context, not a replacement for direct file access.

### Scope-first skill

New skill at `plugins/keel-ai/skills/scope-first/SKILL.md`. Guided
workflow: scope -> design -> plan -> execute. Delegates to
configurable skills from `[extensions.ai.skills]` config. Can search
across projects for similar past decisions or design patterns.

Steps:
1. Detect where the user is (does scope.md exist? design.md? milestones?)
2. Scope: delegate to `skills.scope` (default: `writing-scopes`)
3. Design: delegate to `skills.design` (default: `writing-tech-designs`)
4. Plan: delegate to `skills.plan` (default: `superpowers:writing-plans`)
5. Execute: work through tasks, design-sync after each completion

### Custom action routing

The PostToolUse hook's `match_triggers.py` currently hardcodes
descriptions for `design-sync` and `code-review`. Updated to handle
arbitrary action names: for unknown actions, generate a generic
instruction (`"Run /<action-name>"` or `"Run /<action-name> --<mode>"`).
Users can define custom skills and wire them to triggers.

### SessionStart hook

Updated to trigger `reindex` after AGENTS.md generation (one
additional subprocess call to the MCP server, or the MCP server
handles it on its own startup).

## Configuration

No new TOML configuration needed. The vector search is an internal
capability of the MCP server. Existing `[extensions.ai]` config
(triggers, skills, agents_md) is unchanged.

Voyage embedding access is through Grove (MongoDB's internal AI
gateway). The `GROVE_API_KEY` environment variable is required;
`GROVE_VOYAGE_BASE_URL` is optional (defaults to the standard Grove
Voyage endpoint). Both are configured in the MCP server's
`hooks.json` entry. Users must request Voyage model access in Grove
(`grove.aix.prod.corp.mongodb.com`) before using vector search.

## File structure

```
plugins/keel-ai/
  .claude-plugin/plugin.json        # existing
  hooks/                            # existing
  skills/
    design-sync/SKILL.md            # existing (updated)
    generate/SKILL.md               # existing
    using-keel-ai/SKILL.md          # existing (updated)
    scope-first/SKILL.md            # NEW
  agents/
    design-sync.md                  # existing (updated)
  mcp-server/                       # NEW
    server.py                       # MCP protocol handler
    indexer.py                      # chunking, embedding, upsert
    docker-compose.yml              # Atlas local with persistent volume
    requirements.txt                # pymongo, voyageai, mcp
```

## Testing strategy

| Area | Tests |
|---|---|
| Chunking | Unit: markdown splitting, TOML serialization, frontmatter stripping, edge cases |
| Embedding | Unit: metadata prepending, input_type flags, batch sizing |
| Indexing | Integration: reindex a project, verify chunks in collection, content hash skipping |
| Orphan cleanup | Integration: delete a file, reindex, verify chunks removed |
| Search | Integration: index docs, search, verify relevance and filtering |
| MCP tools | Integration: call search/reindex/status via MCP protocol |
| Docker lifecycle | Integration: compose up/down, health check, volume persistence |
| Multi-process | Integration: concurrent reindexes on different projects |
| Cold start | Performance: time to index a fresh workspace |

## Future upgrade path

The current design uses synchronous pymongo. A future production-grade
version could migrate to:

- **async motor** for non-blocking MongoDB operations
- **watchfiles** for continuous background re-indexing on file changes
- **re-ranking** (Cohere or cross-encoder) if precision becomes an
  issue on larger corpora

The MCP tool interfaces (`search`, `reindex`, `status`) stay stable
across this migration. Only internals change.

## Out of scope

- **Cross-repository code indexing**: only design documents are indexed,
  not source code.
- **Cloud Atlas**: Atlas local only. No cloud deployment.
- **Embedding fine-tuning**: use voyage-3-lite as-is.
- **Real-time streaming search**: search is request/response, not
  streaming.
