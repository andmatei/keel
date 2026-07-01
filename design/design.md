# keel — Design

## Status

Initial design from 2026-04-27 brainstorm. Living source of truth — update as
implementation reveals new constraints. See `scope.md` for what's in/out and
why; see `decisions/` for rationale on choices made.

The 0.0.3 redesign (Plan 8) reshapes the on-disk layout: manifests now live
at each unit's root rather than under a `design/` subdir, tool state moves
under `.keel/`, the `CLAUDE.md` artifact is replaced by an auto-generated
`README.md`, and deliverables collapse onto the same `ProjectManifest`
schema as projects (no more `deliverable.toml`). See
`decisions/2026-05-05-data-model-redesign.md` for rationale and
`plans/2026-05-05-plan-8-data-model-redesign.md` for the rollout plan.
The structural sections below describe the post-0.0.3 layout.

0.0.4 adds user hooks (Plan 9): commands opt into pre/post events via
`@hookable` + `hook_event()`. User-defined hook scripts live under
`.keel/hooks/` at workspace or project level.

0.0.5 adds tags (Plan 10): free-form labels on projects and deliverables
for categorization and filtering. `keel tag {add,rm,list}` manages them;
`keel list`, `keel deliverable list`, and `keel show` display and filter
by them; `keel new --tag` sets them at creation time.

---

## 1. Summary

Rewrite the projects-workspace CLI in Python (Typer + Rich + Pydantic +
markdown-it-py + Jinja2 + tomlkit + questionary + pytest), with three core
structural changes versus the current Bash version:

1. **Per-unit TOML manifest** is the source of truth for code linkage —
   the auto-generated `README.md` is rendered from it, not the other way
   around.
2. **Deliverables are mini-projects** — their unit root has parallel artifacts
   (scope.md opt-in, design.md, decisions/, `.keel/phase`) to a project's,
   and they share the same `ProjectManifest` schema.
3. **Consistent surface** — every command auto-detects scope from CWD, supports
   the same global flags (`--json`, `--dry-run`, `-y`, `-q/-v`), and uses
   AST-aware markdown editing for cross-file mutations (no more `sed`).

---

## 2. Stack

| Concern | Choice | Notes |
|---|---|---|
| CLI framework | **Typer** | Subcommand groups, auto-generated help, built-in completion |
| Output rendering | **Rich** | Tables, color, progress, markdown rendering. Honors `NO_COLOR`. |
| Manifest schema validation | **Pydantic v2** | TOML → typed models for safety |
| TOML I/O | **tomllib** (read), **tomlkit** (write) | Stdlib reads; tomlkit preserves comments on write |
| Markdown AST editing | **markdown-it-py** | Replaces `sed`-based mutation in current Bash |
| Templating | **Jinja2** | Replaces `envsubst`-based templating |
| Interactive prompts | **questionary** | Used only when stdin is a TTY and a required value is missing |
| Tests | **pytest** + **pytest-snapshot** | Snapshot tests on dry-run output and rendered files |
| Install | `uv tool install --editable .` (or `pipx install -e .`) | No system packaging |

---

## 3. Cross-cutting conventions

### 3.1 Auto-detection from CWD

- If `$PWD` is inside `~/projects/<X>/` → `--project=<X>` is set automatically.
- If `$PWD` is inside `~/projects/<X>/deliverables/<Y>/` → both `--project=<X>`
  and `--deliverable=<Y>` are set.
- An explicit `--project`/`--deliverable` flag always overrides.
- If a command needs a project and none is detected and none is passed, fail
  with a clear error. Do **not** silently prompt — too easy to misfire.

### 3.2 Global flags

| Flag | Scope | Behavior |
|---|---|---|
| `--help` / `-h` | every command | Typer-generated |
| `--json` | commands with readable output (`list`, `show`, `phase`, `validate`, decisions, deliverable, code) | structured output, suppresses log lines (implies `-q`) |
| `--dry-run` | mutating commands (`new`, `deliverable add/rm/rename`, `decision new/rm`, `phase set`, `code init/add/rm`, `archive`, `rename`) | print intended actions + diffs, write nothing. Read-only commands (`list`, `show`, `validate`, `decision list/show`, `code list/status`, `design export`) don't need it — running them doesn't mutate state |
| `--yes` / `-y` | destructive commands (`rm`, `rename`, anything that overwrites) | skip confirmation prompt |
| `--quiet` / `-q` | global | suppress info logs, errors still go to stderr |
| `--verbose` / `-v` | global | extra debug logs to stderr |
| `NO_COLOR` env | global | honored by Rich |

`-q` and `-v` are mutually exclusive. `--json` implies `-q`.

### 3.3 Exit codes

- `0` success
- `1` runtime error (project not found, file conflict, git failed,
  validation failed)
- `2` usage error (Typer default)
- `130` SIGINT (Typer default)

### 3.4 Output format

- **stdout**: command results — the requested data, or the `--json` payload.
  Pipe-friendly.
- **stderr**: progress/info logs ("Created project at ..."), errors,
  interactive prompts. Never pollutes stdout.
- **`--json` mode**: predictable schema per command (e.g., `list` always
  returns `{"projects": [...]}`); errors emitted as
  `{"error": "...", "code": "..."}` on stderr, exit non-zero.
- **Color**: auto-detect TTY via Rich; respect `NO_COLOR`.

### 3.5 Mutation safety

- `--dry-run` prints a structured op list and exits 0. Example:
  ```
  [dry-run] Would create:
    ~/projects/foo/README.md                (1.2 KB)
    ~/projects/foo/scope.md                 (340 B)
    ~/projects/foo/.keel/phase
  [dry-run] Would modify:
    ~/projects/parent/design.md
      + ## Deliverables
      + - **foo**: desc. See [design](deliverables/foo/design.md).
  [dry-run] Would create git worktree:
    ~/projects/foo/code  (from ~/repo, branch andrei/foo-base)
  ```
- **Confirmation** prompts only on **destructive** ops (`rm`, `rename`,
  `--force` overwrites). Creates and additive modifications never prompt.
  `-y/--yes` skips confirmation.
- Non-TTY stdin + destructive op + no `-y` → fail loud (don't hang).
- **Conflict on create** → hard fail by default. Opt-in `--force` where it
  makes sense (`decision new` overwriting same-day slug, etc.).
- **Atomicity**: cheap ops (mkdir, file writes) happen first; expensive/
  external ops (git worktree create) happen last. On git failure, leave files
  in place and print recovery hints. No auto-rollback — manual recovery is
  fine for a personal tool.
- **Cross-file mutations** (e.g., `deliverable add` updating parent
  `design.md`) use **markdown-it-py AST editing**, not regex/sed. AST edits
  target named sections (insert under `## Deliverables` heading; create the
  heading if missing). Idempotent — re-running doesn't duplicate.

---

## 4. Conceptual model

```
~/projects/
├── <project-name>/
│   ├── README.md               # Auto-generated from project.toml + lifecycle
│   ├── project.toml            # Manifest: source of truth for code linkage
│   ├── scope.md                # Always present at project level
│   ├── design.md               # Always present at project level
│   ├── decisions/
│   │   └── YYYY-MM-DD-slug.md
│   ├── plans/                  # Optional; implementation plans
│   ├── specs/                  # Optional; design specs
│   ├── .keel/                  # Tool state (managed by keel)
│   │   ├── phase               # Current phase + history
│   │   └── lifecycle.lock.toml # Snapshot of the resolved lifecycle FSM
│   ├── code/                   # Worktree #1 (or code-<repo>/ if multiple)
│   └── deliverables/
│       └── <deliverable>/
│           ├── README.md              # Auto-generated
│           ├── project.toml           # Same schema as parent project
│           ├── scope.md               # OPT-IN — only when distinct from parent
│           ├── design.md
│           ├── decisions/
│           ├── .keel/
│           │   └── phase              # Independent phase tracker
│           └── code/                  # Worktree (or shared with parent)
└── .archive/                   # Soft-deleted projects
    └── <project-name>-<date>/
```

### 4.1 Project vs. deliverable artifact parity

| Artifact | Project | Deliverable |
|---|---|---|
| `README.md` (generated) | yes | yes |
| Manifest | `project.toml` | `project.toml` (same schema) |
| `scope.md` | always created | **opt-in** (use `/write-scope` from inside the dir) |
| `design.md` | always created | always created |
| `decisions/` | yes | yes (independent) |
| Phase (`.keel/phase`) | yes | yes (**independent** — different deliverables can be at different phases) |
| Worktree(s) | optional, declared in manifest | optional, declared in manifest, may be `shared_worktree = true` |

**Rationale (recorded in `decisions/`):**
- Deliverable scope is opt-in because scope is usually derived top-down from
  the project; most deliverables don't have a distinct bounded scope.
- Deliverable phase is independent because deliverables progress at different
  rates (one in `implementing`, another still in `designing`).

### 4.2 Composition principle

The project's design materials compose into a single multi-section document.
Each level contributes its own sections (mental model: tabs in a Google Doc).
`project design export` at the project level produces the unified output;
at the deliverable level it produces just that deliverable.

---

## 5. Manifest schema

### 5.1 `project.toml`

```toml
[project]
name = "api-ai-agents"
description = "AI agents for the API platform"
created = "2026-04-15"
tags = ["api", "research"]

[[repos]]
remote = "git@github.com:10gen/mms.git"   # canonical clone URL
local_hint = "~/mms"                       # suggested local path on a fresh machine
worktree = "code"                          # subdir under project for the worktree
branch_prefix = "andrei/api-ai-agents"     # prefix for branches in this worktree
```

### 5.2 Deliverable manifest

Deliverables use the same `ProjectManifest` schema as projects (Plan 8 /
0.0.3 redesign). The file is `<deliverable>/project.toml`:

```toml
[project]
name = "ipa-skills"
description = "Interface for IPA validation skills"
created = "2026-04-20"
lifecycle = "default"
shared_worktree = false   # true means uses parent's worktree, no own [[repos]]
tags = ["api"]

[[repos]]
remote = "git@github.com:10gen/ipa.git"
local_hint = "~/ipa"
worktree = "code"
branch_prefix = "andrei/api-ai-agents-ipa-skills"
```

### 5.3 Schema rules

- Manifests are validated via Pydantic models on every read.
- `[[repos]]` is empty when the unit has no code (design-only project).
- `shared_worktree = true` is mutually exclusive with `[[repos]]` on a
  deliverable.
- The `branch_prefix` is the basis for branch naming when `code add` creates
  a new worktree.
- `tags` defaults to `[]` — existing manifests without it load fine.
  Validated: lowercase alphanumeric + hyphens, 1–50 chars, no
  leading/trailing hyphens. Lowercased and deduplicated on write.
- `validate` checks: TOML parses, schema matches, declared worktrees exist on
  disk, branches start with the declared `branch_prefix`.
- Lifecycle state names must match `^[a-z][a-z0-9]*(-[a-z0-9]+)*$` — lowercase
  alphanumeric + hyphens, must start with a letter. Both single words (`scoping`)
  and kebab-case (`in-review`) are valid. Enforced by Pydantic validator.

### 5.4 README regeneration

The unit's `README.md` is **rendered from the manifest** (`readme_md.j2`).
It is a derived cache — safe to delete and regenerate, never the source
of truth. AST-aware editing of `design.md` (rather than `README.md`) is
how cross-file mutations propagate, e.g. `deliverable add` inserts a
bullet under `## Deliverables` in the parent's `design.md`.

---

## 6. Command surface

```
project new <name>                                     # create project
project list                                           # tree of projects
project show [name]                                    # project card
project phase [PHASE]                                  # show or transition phase
project validate [name]                                # structural health check
project archive <name>                                 # soft-delete
project rename <old> <new>                             # rename project
project completion {bash|zsh|fish}                     # shell completion install
project --version

project deliverable add <name>
project deliverable rm <name>
project deliverable rename <old> <new>
project deliverable list

project decision new <title> [--supersedes <slug>]
project decision list
project decision show <slug>
project decision rm <slug>

project tag add <tag> [<tag>...]
project tag rm <tag> [<tag>...]
project tag list

project design export

project code list [name]
project code status [name]
project code init [name] [--clone-missing]
project code add [name] --repo PATH
project code rm [name] --repo URL
```

**Slash command remap** (slash command bodies are rewritten to call the new CLI):
- `/decide` → `project decision new`
- `/phase` → `project phase`
- `/export-design` → `project design export`
- `/new-project` (already a guided Claude flow — just calls `project new` at the end)
- `/design-sync` (Claude-driven; no CLI counterpart — `project validate`
  covers structural drift only)

---

## 7. Per-command contracts

### 7.1 `project new <name>`

| Aspect | Spec |
|---|---|
| Args | positional `<name>` (slugified), `-d/--description TEXT` (required, prompted on TTY if missing), `-r/--repo PATH` (repeatable), `--tag TAG` (repeatable), `--no-worktree`, `--dry-run`, `-y/--yes` |
| Auto-detect | n/a (creates new project) |
| Side effects | mkdir `~/projects/<name>/{decisions,.keel}`; write `project.toml`, `README.md` (generated), `scope.md`, `design.md`; `.keel/phase` set to lifecycle's initial state; `.keel/lifecycle.lock.toml` snapshot; for each `--repo`: append `[[repos]]` to manifest, then `code init` materializes worktrees |
| Conflict | hard fail if `~/projects/<name>` exists. No `--force` here (too risky for `new`) |
| Output | created paths + next-steps hints; `--json`: `{"path": "...", "design": "...", "worktrees": [...]}` |
| Errors | invalid name, description missing in non-TTY, repo not a git dir, worktree creation fails (file ops kept; recovery hint printed) |

### 7.2 `project deliverable add <name>`

| Aspect | Spec |
|---|---|
| Args | positional `<name>`, `-d/--description TEXT` (required), `-r/--repo PATH` (single), `--shared` (use parent's worktree), `--dry-run`, `-y/--yes` |
| Auto-detect | parent project from CWD; `--project NAME` overrides; fail loud if not detected and not provided |
| Side effects | mkdir deliverable unit root; write `project.toml`, generated `README.md`, `design.md`, initial `decisions/`; `scope.md` is also scaffolded (kept for parity); `.keel/phase` set to the lifecycle's initial state (lifecycle inherited from parent); AST-edit parent `design.md` to add deliverable under `## Deliverables` (idempotent); create worktree if `--repo` (or shared if `--shared`) |
| Conflict | hard fail if deliverable already exists |
| Output | created paths + parent files modified + next-steps; `--json`: `{"deliverable_path": "...", "modified_files": [...]}` |

### 7.3 `project deliverable rm <name>`

| Aspect | Spec |
|---|---|
| Args | positional `<name>`, `--keep-code`, `--keep-design`, `--force` (allow even if worktree dirty), `-y/--yes`, `--dry-run` |
| Auto-detect | parent project from CWD |
| Confirm | always prompts unless `-y`; lists paths to delete + parent files to modify |
| Side effects | `git worktree remove` (fail if dirty without `--force`); rmtree deliverable unit root; AST-edit parent `design.md` to remove the deliverable line |
| Errors | dirty worktree without `--force`, deliverable not found, non-TTY without `-y` |

### 7.4 `project deliverable rename <old> <new>`

| Aspect | Spec |
|---|---|
| Args | positional `<old> <new>`, `--rename-branch / --no-rename-branch` (default rename), `-y`, `--dry-run` |
| Auto-detect | parent project from CWD |
| Side effects | `git worktree move` (proper git op); rename deliverable unit dir; update manifest's `[project]` block; AST-edit parent `design.md`; `git branch -m old new` if `--rename-branch` |
| Conflict | new name exists → hard fail; dirty worktree → warn but allow |

### 7.5 `project deliverable list`

| Aspect | Spec |
|---|---|
| Args | `--tag TAG` (repeatable, AND semantics), `--json` |
| Auto-detect | project from CWD |
| Default output | table: name, phase, shared, tags, description |
| `--json` | `{"deliverables": [{"name": "...", "phase": "...", "description": "...", "shared_worktree": bool, "tags": [...], "repos": [...]}]}` |

### 7.6 `project decision new <title>`

| Aspect | Spec |
|---|---|
| Args | positional `<title>`, `-D/--deliverable NAME` (override CWD), `--slug SLUG` (override auto-slug), `--supersedes <slug>` (mark old decision superseded + link), `--no-edit` (skip `$EDITOR`), `--force` (overwrite if a decision with same `<date>-<slug>.md` already exists), `--dry-run` |
| Auto-detect | scope (project or deliverable) from CWD |
| Side effects | create `decisions/<YYYY-MM-DD>-<slug>.md` with frontmatter + question/options/conclusion stub; open `$EDITOR` afterwards (skip with `--no-edit` or unset `$EDITOR`); if `--supersedes`: edit old decision's frontmatter to `status: superseded` and append `Superseded by: <new-slug>` |
| Conflict | `<date>-<slug>.md` exists → hard fail; suggest `--slug` to disambiguate |
| Output | path; `--json`: `{"path": "...", "scope": "project|deliverable", "slug": "...", "supersedes": "..."}` |

### 7.7 `project decision list`

| Aspect | Spec |
|---|---|
| Args | `-D/--deliverable NAME`, `--all` (include parent project decisions when run inside a deliverable), `--status STATUS`, `--since DATE`, `--json` |
| Auto-detect | scope from CWD |
| Default output | table: date, slug, status, title (truncated). Sorted reverse-chronological |
| `--json` | `{"decisions": [{"date": "...", "slug": "...", "title": "...", "status": "...", "path": "..."}]}` |

### 7.8 `project decision show <slug>`

| Aspect | Spec |
|---|---|
| Args | positional `<slug>` (date prefix optional), `-D/--deliverable NAME`, `--json`, `--raw` |
| Auto-detect | scope from CWD |
| Default output | rendered markdown via Rich |
| `--raw` | dump file contents unchanged (pipe-friendly) |
| `--json` | `{"path": "...", "frontmatter": {...}, "body_markdown": "..."}` |
| Errors | slug not found → suggest closest matches (fuzzy) |

### 7.9 `project decision rm <slug>`

| Aspect | Spec |
|---|---|
| Args | positional `<slug>` or full filename, `-y/--yes`, `--dry-run` |
| Auto-detect | scope from CWD |
| Confirm | prompts unless `-y` |
| Side effects | rm decision file. Note: typical "changed my mind" pattern is `decision new --supersedes <slug>`, not `rm` |

### 7.10 `project phase [PHASE]`

| Aspect | Spec |
|---|---|
| Args | positional `[PHASE]` (transition target), `--next` (advance one step, exclusive with positional), `-D/--deliverable NAME`, `-m/--message TEXT`, `--no-decision` (skip auto-creating phase decision file), `--json`, `--dry-run` |
| Auto-detect | scope from CWD |
| Show mode (no `PHASE`/`--next`) | print current + lifecycle bar with current marked + history (date, old→new, note) |
| Transition mode | write `.phase`; auto-create `decisions/<date>-phase-<new>.md` unless `--no-decision`; print `old → new` |
| Lifecycle | `scoping → designing → poc → implementing → shipping → done` |
| Backwards transitions | allowed; warn + confirm prompt unless `-y` |
| `--json` | show: `{"scope": "project|deliverable", "name": "...", "phase": "...", "history": [...]}`. transition: same plus `"transitioned_from"` |

### 7.11 `project list`

| Aspect | Spec |
|---|---|
| Args | `--phase PHASE`, `--tag TAG` (repeatable, AND semantics), `--active`, `--deliverables-only`, `--json` |
| Default output | tree: project name + phase + tags (colored) + deliverable count + active milestone/task counts. Does NOT run `git status` (slow) |
| `--json` | `{"projects": [{"name": "...", "phase": "...", "description": "...", "tags": [...], "deliverable_count": N, "active_milestones": N, "active_tasks": N}]}` |

### 7.12 `project show [name]`

| Aspect | Spec |
|---|---|
| Args | positional `[name]` (auto-detected), `-D/--deliverable NAME`, `--json` |
| Default output | structured "project card": name + description, phase, tags (colored, omitted when empty), manifest repos (paths/branches), design files (mtime), decision count + last 3, deliverable list with phases, worktree paths/branches (no git status — `code status` covers it) |
| `--json` | flat object with all the above |

### 7.13 `project validate [name]`

| Aspect | Spec |
|---|---|
| Args | positional `[name]` (auto-detected), `--strict` (warnings → failures), `--check FILTER` (e.g., `--check manifest,refs`), `--content` (opt-in content checks), `--json` |
| Structural checks (always) | manifest is valid TOML & matches schema; required files exist (`design.md`, `.keel/phase`); declared worktrees exist; worktree branches match `branch_prefix`; on-disk deliverables (those with a `project.toml`) are mentioned in parent `design.md` |
| Content checks (`--content`) | decision frontmatter parses; design.md has expected sections |
| Default output | per-check PASS/WARN/FAIL list + summary |
| `--json` | `{"findings": [...], "summary": {"pass": N, "warn": N, "fail": N}}` |
| Exit code | 0 if no FAILs; 1 if any FAIL; with `--strict`, warnings count as fails |

### 7.14 `project archive <name>`

| Aspect | Spec |
|---|---|
| Args | positional `[name]` (auto-detected), `--force` (allow if any worktree dirty), `-y/--yes`, `--dry-run` |
| Side effects | `git worktree remove` for each worktree (fail if dirty without `--force`); move `~/projects/<name>` → `~/projects/.archive/<name>-<YYYY-MM-DD>/`; leave `.archived` marker noting timestamp |
| Restore | manual: `mv .archive/foo-<date> foo && project code init` |

### 7.15 `project rename <old> <new>`

| Aspect | Spec |
|---|---|
| Args | positional `<old> <new>`, `--rename-branches / --no-rename-branches` (default rename), `-y`, `--dry-run` |
| Side effects | rename project dir; for each worktree: `git worktree move`, `git branch -m`; update manifest's `branch_prefix`; AST-edit any deliverable `design.md` mentioning old name |
| Output | summary of dirs renamed + branches renamed + files updated |

### 7.16 `project design export`

| Aspect | Spec |
|---|---|
| Args | positional `[name]` (auto-detected), `-D/--deliverable NAME`, `--no-decisions`, `--no-deliverables` (project-level only), `--include-scope` (prepend scope.md), `-o/--output PATH` (default stdout), `--format markdown` |
| Project-level output | `# <Project>: Design` → `## Project Design` (decisions replaced with `(Appendix D.N)` refs) → `## Deliverable: <a>` ... → `## Appendix: Decisions` (numbered, superseded excluded) |
| Deliverable-level output | `# <Deliverable>: Design` → `## Design` → `## Appendix: Decisions` (just that deliverable's) |
| Decision appendix scoping | flat numbering across the whole export (D.1, D.2, ...) |
| Errors | design.md missing; broken decision refs (warns + inlines with note) |

### 7.17 `project code list [name]`

| Aspect | Spec |
|---|---|
| Args | positional `[name]` (auto-detected), `-D/--deliverable NAME`, `--json` |
| Default output | table: remote, local_hint, worktree path, branch_prefix |
| `--json` | `{"repos": [...]}` |

### 7.18 `project code status [name]`

| Aspect | Spec |
|---|---|
| Args | positional `[name]` (auto-detected), `--json`, `--fetch` (run `git fetch` first) |
| Default output | per-repo: cloned? worktree exists? current branch (matches prefix?), clean/dirty, ahead/behind |
| `--json` | structured per-repo state |

### 7.19 `project code init [name]`

| Aspect | Spec |
|---|---|
| Args | positional `[name]` (auto-detected), `--clone-missing` (clone repos missing locally — uses `local_hint` or prompts), `-y/--yes`, `--dry-run` |
| Side effects | for each `[[repos]]` entry: ensure source repo exists at `local_hint` (clone if `--clone-missing`); ensure worktree at declared `worktree` path on a branch with `branch_prefix` (create if missing). Idempotent |
| Errors | source repo missing without `--clone-missing`; branch_prefix mismatch (existing branch elsewhere) |

### 7.20 `project code add [name] --repo PATH`

| Aspect | Spec |
|---|---|
| Args | positional `[name]` (auto-detected), `--repo PATH` (required), `--worktree NAME` (default: `code-<reponame>`), `--branch-prefix PREFIX` (default: `<gituser>/<project>[-<deliverable>]`), `--dry-run`, `-y` |
| Side effects | append `[[repos]]` entry to manifest; create worktree per the new entry; regen `README.md` |
| Conflict | repo already declared → hard fail unless `--force` |

### 7.21 `project code rm [name] --repo URL`

| Aspect | Spec |
|---|---|
| Args | positional `[name]` (auto-detected), `--repo URL` (required), `-y/--yes`, `--dry-run`, `--force` (dirty worktree) |
| Confirm | prompts unless `-y` |
| Side effects | `git worktree remove` (fail if dirty without `--force`); remove `[[repos]]` entry; regen `README.md` |

### 7.22 `project completion {bash|zsh|fish}`

Wraps Typer's built-in completion installer. Prints the completion script to
stdout (redirect to file), or with `--install` writes to the canonical
location for the chosen shell.

### 7.23 `project tag add <tag> [<tag>...]`

| Aspect | Spec |
|---|---|
| Args | positional `<tag>` (repeatable), `--project`/`-p`, `--deliverable`, `--no-verify`, `--json` |
| Auto-detect | scope from CWD |
| Side effects | appends tags to manifest's `tags` list; saves manifest |
| Idempotent | adding an already-present tag is a no-op (no error) |
| Hookable | `pre-tag-add` / `post-tag-add` (post payload: `tags_added` = only actually new tags) |
| Output | current tag list; `--json`: `{"tags": [...], "added": [...]}` |

### 7.24 `project tag rm <tag> [<tag>...]`

| Aspect | Spec |
|---|---|
| Args | positional `<tag>` (repeatable), `--project`/`-p`, `--deliverable`, `--no-verify`, `--json` |
| Auto-detect | scope from CWD |
| Side effects | removes tags from manifest; warns (does not error) if a tag was not present |
| Hookable | `pre-tag-rm` / `post-tag-rm` (post payload: `tags_removed` = only actually removed tags) |
| Output | current tag list; `--json`: `{"tags": [...], "removed": [...]}` |

### 7.25 `project tag list`

| Aspect | Spec |
|---|---|
| Args | `--project`/`-p`, `--deliverable`, `--json` |
| Auto-detect | scope from CWD; falls back to global mode if no project detected |
| Scoped mode | flat list of the unit's tags |
| Global mode | grouped tree: each tag with its member projects and deliverables, colored, sorted alphabetically |
| Not hookable | read-only, no side effects |
| `--json` (scoped) | `{"tags": [...]}` |
| `--json` (global) | `{"tags": {"<tag>": {"projects": [...], "deliverables": [{"project": "...", "name": "..."}]}}}` |

### 7.26 `project --version`

Reads version from `pyproject.toml` via `importlib.metadata`.

---

## 8. Migration plan (historical)

`keel migrate` was removed in 0.0.5. The one-time Bash CLI → TOML and
layout restructure migrations are complete for all active workspaces.
During `0.0.x` alpha, breaking schema changes are handled directly —
Pydantic's `extra="forbid"` provides clear errors if a manifest doesn't
match the expected schema. A proper migration framework may be revisited
post-1.0 if needed. See `decisions/2026-05-12-discontinue-migrate-and-schema-versioning.md`.

---

## 9. Tests

- `pytest` covers, at minimum:
  - `new` (with and without repos)
  - `deliverable add/rm/rename/list`
  - `decision new/list/show/rm` and `--supersedes`
  - `phase` show + transitions (incl. backwards + per-deliverable)
  - `design export` (project- and deliverable-level)
  - `code init/status/list/add/rm`
  - `validate` (PASS, WARN, FAIL fixtures)
  - `archive` + restore round-trip
  - `rename` (project-level)
- **Snapshot tests** on dry-run output and rendered files: changes to
  generated artifacts (`README.md`, `design.md` mutations) require updating
  snapshots, making cross-file mutations easy to review.
- Each command has a smoke test for `--json` shape (Pydantic models).

---

## 10. Deferred / Parking lot

- ~~**Milestones per deliverable/project**~~: shipped in 0.0.2.
  `milestones.toml` lives at the unit root. Milestone fields: `id`, `title`,
  `description: str | None`, `status`, `parent: str | None` (links sub-milestones
  back to project-level), `tickets: dict[str, str]` (provider-keyed, e.g.
  `{"jira": "CLOUDP-123"}`). Tasks: `id`, `milestone`, `title`,
  `description: str | None`, `status`, `depends_on`, `branch: str | None`,
  `tickets: dict[str, str]`.
- **IDL location**: pending clarification of what "idl where to put it"
  meant — possibly Interface Definition Language files, possibly a typo.
- **`project link/unlink` for Jira/Confluence**: structured external-ref
  storage is out of scope for v1; links live in design docs and tickets.

---

## 11. Open questions

- **Where does the Python source code live?**
  - In `~/projects/bin/` alongside the existing Bash tool until cutover, then
    replace?
  - In a new top-level dir, e.g., `~/projects/.tools/keel/`?
  - In its own git repo, separate from `~/projects/`?
  - Decide during implementation planning (writing-plans skill).
- **Cutover strategy**: do we run new + old in parallel for a period, or
  swap atomically? Probably atomic, since we control both sides.
- **`local_hint` UX in `code init --clone-missing`**: prompt with default,
  or fail if not present? Probably prompt-with-default on TTY, fail on
  non-TTY.
