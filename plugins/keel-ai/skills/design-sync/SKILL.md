---
name: design-sync
description: |
  Check for drift between design documents and implementation.
  Lifecycle-aware: knows about milestones, tasks, and their completion state.
  Use after task/milestone completion, phase transitions, or when asked to
  sync the design. Triggers on "sync design", "check drift", "update design
  from code", "design sync", "design-sync".
context: fork
agent: design-sync
---

# Design Sync

Detect and fix drift between design documents and implementation.

## Mode Detection

Determine the mode from arguments or context:

- `--lightweight` → targeted update (small, focused changes)
- `--thorough` → full review (architecture, components, decisions)
- `--check` → report only, no edits
- No argument → auto-detect from recent lifecycle events

## Run the Sync

Dispatch the design-sync agent with the detected mode and scope.
