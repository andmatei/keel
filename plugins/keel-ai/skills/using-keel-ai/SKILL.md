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
