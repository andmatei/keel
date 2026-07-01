---
date: 2026-05-14
title: "keel-ai: AI-assisted scope-first development plugin"
status: draft
depends-on: 2026-05-14-hooks-v1-dotted-events.md
---

# keel-ai: AI-assisted scope-first development plugin

## Summary

A Claude Code plugin that provides AI-assisted scope-first development
for keel-managed projects. Two core capabilities:

1. **Design drift prevention** — After task/milestone completion, AI
   updates design documents to reflect what was actually built.
2. **AI-assisted workflow** — Skills for scoping, designing, and
   generating project artifacts (CLAUDE.md as a reference index).

keel-ai is a **routing layer**: it maps keel lifecycle events to
configurable AI actions. It doesn't hardcode what AI does — users
configure triggers and can swap in their own skills.

## Architecture

keel-ai is a **Claude Code plugin** (not an MCP server, not a standalone
Python package). It consists of:

```
keel-ai/
├── .claude-plugin/
│   └── plugin.json
├── hooks/
│   ├── hooks.json              # SessionStart hook
│   └── session-start           # CLAUDE.md generation script
├── skills/
│   ├── design-sync/
│   │   └── SKILL.md
│   ├── generate-claude-md/
│   │   └── SKILL.md
│   ├── scope-first/
│   │   └── SKILL.md
│   └── using-keel-ai/
│       └── SKILL.md            # Routing/intro skill (loaded on session start)
├── agents/
│   └── design-sync.md          # Subagent for drift detection
└── package.json
```

### How AI actions are triggered

Claude Code is an AI that follows instructions. The triggering
mechanism is **CLAUDE.md generation** — not a complex event bus
bridging Python and Claude Code processes.

**Flow:**

1. keel-ai's **SessionStart hook** runs `keel` CLI to read project
   state and generates/updates a `CLAUDE.md` at the project root.
2. The generated CLAUDE.md includes:
   - An **index of project artifacts** (scope.md, design.md,
     decisions/, milestones, deliverables)
   - **Workflow instructions** derived from `[extensions.ai]` config:
     "After completing a task, run `/design-sync --lightweight`.
     After completing a milestone, run `/design-sync --thorough`."
3. Claude Code reads CLAUDE.md at session start and follows the
   instructions naturally during the session.

This approach is transparent (users can read CLAUDE.md to see what AI
will do), debuggable (edit CLAUDE.md to override), and doesn't require
bridging keel's Python event system to Claude Code's runtime.

### Why not bridge keel hooks directly to Claude Code?

keel hooks fire in the CLI process (Python). Claude Code skills run in
the AI session. There's no IPC channel between them. Possible bridges
(file queues, output parsing) add complexity and fragility. CLAUDE.md
generation is the idiomatic Claude Code pattern — it's how every Claude
Code plugin communicates intent to the AI.

For non-AI consumers of keel events (Slack notifications, ticket
transitions), the Python hooks framework serves directly. keel-ai's
contribution is the AI layer on top.

## Capability 1: Design drift prevention

### The problem

Design documents (scope.md, design.md, decisions/) drift from
implementation as work progresses. The scope said "support 3 providers"
but implementation added 5. The design said "REST API" but the team
switched to GraphQL. Nobody updates the docs until they're useless.

### The solution

After lifecycle events, AI reads the current implementation state and
updates design documents to reflect reality. Two modes:

**Lightweight** (after task completion):
- Read the completed task's diff (git log since task started)
- Scan design.md for sections that reference the changed area
- Apply targeted updates: fix outdated descriptions, add new
  components, mark completed items
- Small, focused changes — not a full rewrite

**Thorough** (after milestone completion):
- Read all changes across the milestone's tasks
- Full design.md review: architecture section, component descriptions,
  data flow, API surface
- Update decisions/ if any implicit decisions were made during
  implementation
- Flag scope drift: "Implementation added X which isn't in scope.md —
  should scope be updated?"

### /design-sync skill

The primary skill for drift prevention. Invoked by Claude Code when
CLAUDE.md instructions say to, or manually by the user.

```
/design-sync                    # auto-detect mode from context
/design-sync --lightweight      # targeted update (post-task)
/design-sync --thorough         # full review (post-milestone)
/design-sync --check            # report drift without fixing
```

The skill:
1. Reads the project's `[extensions.ai]` config for mode/scope
2. Reads current design documents (scope.md, design.md, decisions/)
3. Reads recent implementation changes (git diff/log)
4. Identifies drift between docs and code
5. In check mode: reports findings
6. In update mode: edits design documents and commits

This skill extends the existing `design-sync` agent already in the
workspace. keel-ai's version adds lifecycle-awareness (knows about
milestones, tasks, and their completion state) and config-driven
behavior.

## Capability 2: AI-assisted scope-first workflow

### /scope-first skill

Guided workflow for starting new projects or deliverables with scope
first:

1. **Scope** — Ask clarifying questions, write scope.md
2. **Design** — Based on scope, brainstorm and write design.md
3. **Plan** — Break design into milestones and tasks via keel CLI
4. **Execute** — Work through tasks, design-sync after each

The skill is a coordinator — it delegates to existing skills
(writing-scopes, writing-tech-designs, superpowers:writing-plans) and
orchestrates the keel CLI commands between them.

Users can swap in their own skills for each step. The routing config
specifies which skill handles each phase:

```toml
[extensions.ai.skills]
scope = "writing-scopes"           # default
design = "writing-tech-designs"    # default
plan = "superpowers:writing-plans" # default
```

## Capability 3: Artifact generation

### Generated CLAUDE.md

The SessionStart hook generates a CLAUDE.md at the project root that
serves as an index and instruction set:

```markdown
# Project: <name>
# Phase: <current_phase>
# Lifecycle: <lifecycle_name>

## Artifacts
- Scope: design/scope.md
- Design: design/design.md
- Decisions: design/decisions/ (3 files)
- Milestones: milestones.toml (2 active, 1 planned)

## Deliverables
- alpha: deliverables/alpha/ (designing phase)
  - Scope: deliverables/alpha/design/scope.md
  - Design: deliverables/alpha/design/design.md

## Active Work
- Milestone m1 "Foundation" (active, 3/5 tasks done)
  - Task t4 "API endpoints" (active)
  - Task t5 "Error handling" (planned)

## AI Workflow
After completing a task: run /design-sync --lightweight
After completing a milestone: run /design-sync --thorough
After phase transition: review scope.md for drift
```

The CLAUDE.md is **regenerated on every session start** — it's a
derived artifact, not a hand-edited file. Users can add a
`.keel/claude-md-extra.md` file with additional instructions that get
appended.

### When CLAUDE.md is generated

- **SessionStart**: Always regenerated from current project state
- **On demand**: `/generate-claude-md` skill for manual regeneration
  mid-session

The generator reads:
- `project.toml` (project metadata, extensions config)
- `milestones.toml` (milestone/task state)
- `.keel/.phase` (current phase)
- File existence checks (scope.md, design.md, decisions/)
- `[extensions.ai]` config (workflow instructions)

## Configuration

Config lives in `[extensions.ai]` in project.toml:

```toml
[extensions.ai]
enabled = true

# What to do after lifecycle events
[extensions.ai.triggers]

[extensions.ai.triggers.task_done]
event = "task.status.post"
when = {to = "done"}
action = "design-sync"
mode = "lightweight"

[extensions.ai.triggers.milestone_done]
event = "milestone.status.post"
when = {to = "done"}
action = "design-sync"
mode = "thorough"

[extensions.ai.triggers.phase_change]
event = "project.phase.post"
action = "design-sync"
mode = "thorough"
enabled = false                    # opt-in per user preference

# Which skills handle each workflow step
[extensions.ai.skills]
scope = "writing-scopes"
design = "writing-tech-designs"
plan = "superpowers:writing-plans"

# Extra CLAUDE.md content file
[extensions.ai.claude_md]
extra = ".keel/claude-md-extra.md"
```

### Config resolution

1. If `[extensions.ai]` is absent, keel-ai does nothing (generates a
   minimal CLAUDE.md with just the artifact index, no workflow
   instructions)
2. If `enabled = false`, keel-ai is fully disabled
3. Individual triggers can be disabled with `enabled = false`
4. The `when` field is optional — omitting it means "always fire"
5. The `action` field maps to a skill name (extensible)
6. The `mode` field is passed to the skill as a parameter

### Config schema validation

The `[extensions.ai]` config is validated by keel-cli (Python/Pydantic)
since keel-ai reads project state via the CLI. A `keel ai show-config`
command parses and returns the validated config as JSON, which the
SessionStart hook and skills consume.

Pydantic models in keel-cli:

```python
class TriggerWhen(BaseModel):
    to: str | None = None
    from_state: str | None = Field(None, alias="from")

class Trigger(BaseModel):
    event: str
    when: TriggerWhen | None = None
    action: str
    mode: str | None = None
    enabled: bool = True

class AISkills(BaseModel):
    scope: str = "writing-scopes"
    design: str = "writing-tech-designs"
    plan: str = "superpowers:writing-plans"

class ClaudeMdConfig(BaseModel):
    extra: str | None = None

class AIConfig(BaseModel):
    enabled: bool = True
    triggers: dict[str, Trigger] = {}
    skills: AISkills = AISkills()
    claude_md: ClaudeMdConfig = ClaudeMdConfig()
```

The SessionStart hook calls `keel ai show-config --json` and uses the
output to generate CLAUDE.md. Skills call the same command to read
trigger configuration.

## Extensibility

### Custom skills

Users can override any skill in the workflow:

```toml
[extensions.ai.skills]
scope = "my-custom-scoping-skill"
design = "my-custom-design-skill"
```

The skill name is resolved by Claude Code's skill system — it can be a
plugin skill, a workspace skill, or a superpowers skill.

### Custom triggers

Users can add their own trigger entries:

```toml
[extensions.ai.triggers.notify_on_cancel]
event = "milestone.status.post"
when = {to = "cancelled"}
action = "notify-team"
mode = "slack"
```

The `action` field maps to a skill name. keel-ai's built-in actions are
`design-sync` and `generate-claude-md`. Custom actions resolve to
user-defined skills.

### Custom CLAUDE.md sections

The `.keel/claude-md-extra.md` file is appended to the generated
CLAUDE.md. Users can add project-specific instructions, tool
preferences, or workflow overrides.

## Plugin packaging

keel-ai lives at `plugins/keel-ai/` in the keel monorepo. It is a
**Claude Code plugin** (not a Python package). Contains `.claude-plugin/`,
skills/, hooks/, agents/.

**Distribution:**
- **Development**: local path — `claude plugin add ~/projects/keel/plugins/keel-ai`
- **Future**: extract to a standalone `keel-ai` repo for
  `claude plugin add https://github.com/andmatei/keel-ai`.
  Claude Code plugin install from a git URL requires the plugin to be
  at the repo root (subdirectory paths are not supported).

keel-ai does NOT need a Python package on PyPI. It doesn't register
`keel.event_listeners` — it operates entirely through Claude Code's
skill/hook system and reads keel state via the CLI.

### Dependencies

- `keel-cli` must be installed (keel-ai calls it via subprocess)
- No Python package dependencies beyond what keel-cli provides
- No MCP server — skills and hooks are sufficient

## Testing strategy

| Area | Tests |
|---|---|
| CLAUDE.md generation | Unit tests: given project state, verify generated content |
| Config parsing | Pydantic model validation for `[extensions.ai]` |
| Trigger matching | Given event + config, verify correct action selected |
| /design-sync | Integration: make a code change, run skill, verify design.md updated |
| /scope-first | Integration: verify workflow steps execute in order |
| Extensibility | Custom skill name in config resolves correctly |
| Edge cases | Missing config, disabled triggers, empty project |

## Implementation phases

**Phase 1** (this plan): Core plugin structure
- CLAUDE.md generation (SessionStart hook + /generate-claude-md skill)
- Config model + validation
- /design-sync skill (lightweight + thorough modes)

**Phase 2** (follow-up): Workflow skills
- /scope-first skill
- Deeper integration with superpowers skills
- Custom action routing

## Out of scope

- **MCP server**: No resources or tools exposed via MCP. Skills are
  sufficient for Claude Code integration.
- **Standalone Python package**: keel-ai doesn't need PyPI distribution.
  It's a Claude Code plugin distributed via npm/marketplace.
- **Real-time file watching**: No `watchdog`/`watchfiles` integration.
  Design sync is triggered by lifecycle events, not file changes.
- **Multi-agent orchestration**: keel-ai doesn't spawn background
  agents. All AI actions run in the current Claude Code session.
- **Automatic execution**: AI actions are suggested in CLAUDE.md, not
  auto-executed. Claude Code follows the instructions but the user
  controls when skills run.
