# keel

## Scope Document

Author: Andrei Matei
Date: 2026-04-27

## Summary

Rewrite the existing Bash CLI at `~/projects/bin/project` as a Python tool with
a proper subcommand structure, a manifest-based source of truth for code
linkage, and consistent UX. Deliverables become full mini-projects with their
own scope (opt-in), phase, and decisions — parallel to the project level.

## Terminology

- **Project**: a top-level workspace under `~/projects/<name>/` with `design/`
  and optional `code/` worktrees.
- **Deliverable**: a sub-project nested at `~/projects/<name>/deliverables/<x>/`,
  with its own `design/` and (optionally) `code/`. Treated as a mini-project.
- **Manifest**: TOML file at `<unit>/project.toml` that declares linked
  source repos and how to materialize their worktrees.
- **Composition principle**: the project's design materials compose into a
  single multi-section export. Each level (project, deliverable) contributes
  its own sections, like tabs in a Google Doc.

## Engineering Goals

- Replace ~1000 lines of Bash with maintainable Python (Typer + Rich + Pydantic
  + markdown-it-py + Jinja2 + tomlkit + questionary + pytest).
- Introduce per-unit TOML manifests as the source of truth for code linkage,
  replacing fragile sed-based mutation of CLAUDE.md/design.md.
- Standardize the command surface: auto-detection from CWD, consistent global
  flags (`--json`, `--dry-run`, `-y`, `-q/-v`), structured JSON output, dry-run
  for all mutations, AST-aware markdown editing.
- Promote deliverable to a true mini-project: parallel scope (opt-in), phase,
  and decisions; design.md and decisions/ already parallel today.
- Add commands the Bash version lacks: `deliverable rm/rename/list`,
  `decision rm/list/show`, `decision new --supersedes`, `validate`, `archive`,
  `rename` (project), `code init/status/list/add/rm`, `--version`,
  `completion`.
- Keep all slash commands working with the same entry points, re-pointed at
  the new CLI surface.

## Non-goals

- Distributing the tool beyond personal/local use.
- Single-binary distribution. Python via `uv tool install --editable .` is fine.
- Replacing the slash commands or any Claude-driven workflow.
- Bundled ticketing providers — see Plan 5 and the plugin model decision for rationale.
- Semantic design-vs-code drift detection — that remains the
  `/design-sync` slash command's job (Claude-driven).

## Assumptions and Risks

- Python ≥3.11 is available on the host. `uv tool install --editable .` handles
  isolation, and `tomllib` is in the stdlib.
- Existing projects needed a one-time migration to populate manifests from
  current CLAUDE.md text. Migration is complete; `keel migrate` was removed
  in 0.0.5.
- AST-aware markdown editing is more code than `sed`, but `markdown-it-py` has a
  mature ecosystem and the alternative (regex-based mutation) is what we're
  fixing.
- Slash commands depend on stable command names. Re-pointing is a one-shot
  rewrite of the slash command bodies.

## Open Questions

- Where the Python source lives: in `bin/` alongside the existing tools, in a
  new top-level dir under `~/projects/`, or in its own repo. To be decided
  during implementation planning.
- Pending parking-lot item: clarify what "idl where to put it" meant in the
  brainstorm session.

## Success Criteria

- All existing slash commands (`/decide`, `/phase`, `/export-design`,
  `/new-project`, `/design-sync`) continue to work without user-visible
  regressions.
- All existing Bash CLI behaviors are covered with feature parity or
  improvement.
- Existing projects (`api-ai-agents`, etc.) usable after running the migration
  with no manual fixup required.
- `pytest` covers the core flows: `new`, `deliverable add/rm/rename`,
  `decision new/list/rm`, `phase`, `design export`, `code init`, `validate`,
  `archive`, `rename`. Mutation commands have dry-run snapshots.
- `project --help` is self-documenting; `project completion zsh` produces a
  working completion script.

## Status as of Plan 5.2

- **Milestones + tasks (Plan 5)** — shipped. See `keel milestone` and `keel task` commands.
- **Ticketing plugin protocol (Plan 5)** — shipped. No bundled providers; see `design/decisions/2026-04-29-plan-5-plugin-model.md` for rationale.
- **Migration from Bash CLI (Plan 4)** — complete. Bash CLI archived; `keel migrate` removed in 0.0.5 (all active workspaces migrated).
- **Rename to `keel` (Plan 3-4)** — complete. Public repo at https://github.com/andmatei/keel.

## References

- Previous Bash CLI: archived as part of Plan 4 migration.
- Workspace conventions: documented in `design/CLAUDE.md`.
- Brainstorm session that produced this scope: 2026-04-27 (this design dir)
