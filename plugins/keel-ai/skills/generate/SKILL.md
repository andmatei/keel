---
name: generate
description: |
  Regenerate the project's AGENTS.md and CLAUDE.md files mid-session.
  Use when project structure or configuration has changed and you need
  an updated artifact index. Triggers on "regenerate agents.md",
  "update agents.md", "refresh agents.md", "generate".
---

# Generate AGENTS.md

Regenerate the AGENTS.md and CLAUDE.md files for the current project.

## When to use

- After changing `[extensions.ai]` config in project.toml
- After adding/removing deliverables or milestones
- After a phase transition
- When the AGENTS.md feels out of date

## Process

1. Detect the current project from the working directory.
2. Run the keel CLI to regenerate:

```bash
keel ai generate --output <project-root>
```

3. Read the updated AGENTS.md and confirm the changes look correct.
4. Report what changed (new deliverables, updated milestone counts, etc.).
