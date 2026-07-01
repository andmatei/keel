---
name: scope-first
description: |
  Guided scope-first workflow: scope → design → plan → execute.
  Detects where you are in the flow and delegates to the right skill.
  Triggers on "scope-first", "start from scope", "guided workflow".
context: fork
---

# Scope-First Workflow

A guided workflow that ensures work follows the scope → design → plan → execute sequence.

## Detection

Detect where the user is in the workflow by checking which artifacts exist:

1. Does `scope.md` exist? If not → start with scoping
2. Does `design.md` exist? If not → start with design
3. Does `milestones.toml` exist with tasks? If not → start with planning
4. Are there active tasks? → continue execution

```bash
keel show --brief --json
```

## Workflow Steps

### Step 1: Scope

If `scope.md` doesn't exist or the user wants to start fresh:

Delegate to the configured scope skill. Check the project's AI config:

```bash
keel ai show-config --json
```

Look at `skills.scope` (default: `writing-scopes`). Run that skill.

### Step 2: Design

If `scope.md` exists but `design.md` doesn't:

Delegate to the configured design skill. Look at `skills.design` (default: `writing-tech-designs`).

Before starting, use the `search` tool (if available) to find similar designs or decisions across other projects:

```
search(query="<project description>", project="all")
```

This surfaces patterns and prior art that can inform the design.

### Step 3: Plan

If both `scope.md` and `design.md` exist but no milestones:

Delegate to the configured plan skill. Look at `skills.plan` (default: `superpowers:writing-plans`).

### Step 4: Execute

If milestones and tasks exist:

Work through tasks in order. After each task completion, run `/design-sync --lightweight` to keep documents current. After each milestone completion, run `/design-sync --thorough`.

## Cross-Project Context

When available, use the `search` tool to find relevant prior decisions or design patterns across all indexed projects. This is particularly useful during the scope and design phases to avoid reinventing solutions.

## Key Principle

Never skip a step. If the user asks to "just start coding" but there's no scope document, guide them through scoping first. The workflow exists to prevent wasted work.
