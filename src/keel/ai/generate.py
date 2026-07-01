"""Generate AGENTS.md content from project state."""

from __future__ import annotations

from pathlib import Path

from keel.ai.config import Trigger, parse_ai_config, resolve_triggers
from keel.manifest import (
    load_milestones_manifest,
    load_project_manifest,
)
from keel.workspace import Scope, read_phase


CLAUDE_MD_POINTER = (
    "# See AGENTS.md\n"
    "\n"
    "This project uses AGENTS.md for AI agent instructions.\n"
    "Read AGENTS.md in this directory for project context and workflow instructions.\n"
)


def generate_agents_md(scope: Scope) -> str:
    """Generate AGENTS.md content for a project scope."""
    pm = load_project_manifest(scope.manifest_path)
    phase = read_phase(scope.unit_dir)
    ai_config = parse_ai_config(pm.extensions.get("ai"))
    resolved = resolve_triggers(ai_config, pm.project.lifecycle)

    lines: list[str] = []

    _header(lines, pm.project.name, phase, pm.project.lifecycle)
    _artifacts(lines, scope)
    _deliverables(lines, scope)
    _active_work(lines, scope)

    if ai_config.enabled and resolved:
        _workflow(lines, resolved)

    if ai_config.agents_md.extra:
        _extra(lines, scope.unit_dir, ai_config.agents_md.extra)

    return "\n".join(lines) + "\n"


def _header(lines: list[str], name: str, phase: str, lifecycle: str) -> None:
    lines.append(f"# Project: {name}")
    lines.append(f"# Phase: {phase}")
    lines.append(f"# Lifecycle: {lifecycle}")
    lines.append("")


def _artifacts(lines: list[str], scope: Scope) -> None:
    lines.append("## Artifacts")
    _artifact_line(lines, "Scope", scope.scope_md_path)
    _artifact_line(lines, "Design", scope.design_md_path)

    decisions = (
        sorted(scope.decisions_dir.glob("*.md"))
        if scope.decisions_dir.is_dir()
        else []
    )
    if decisions:
        rel = _rel(scope.decisions_dir, scope.unit_dir)
        # Ensure the path renders with a trailing slash to signal it's a directory.
        rel_display = rel.rstrip("/") + "/"
        lines.append(f"- Decisions: {rel_display} ({len(decisions)} files)")

    mm = load_milestones_manifest(scope.milestones_manifest_path)
    if mm.milestones:
        counts: dict[str, int] = {}
        for m in mm.milestones:
            counts[m.status] = counts.get(m.status, 0) + 1
        summary = ", ".join(f"{c} {s}" for s, c in counts.items())
        lines.append(f"- Milestones: milestones.toml ({summary})")

    lines.append("")


def _artifact_line(lines: list[str], label: str, path: Path) -> None:
    if path.is_file():
        lines.append(f"- {label}: {path.name}")
    else:
        lines.append(f"- {label}: *(not yet created)*")


def _deliverables(lines: list[str], scope: Scope) -> None:
    deliv_root = scope.unit_dir / "deliverables"
    if not deliv_root.is_dir():
        return

    entries: list[tuple[str, str, Scope]] = []
    for child in sorted(deliv_root.iterdir()):
        if not child.is_dir():
            continue
        manifest_path = child / "project.toml"
        if not manifest_path.is_file():
            continue
        d_phase = read_phase(child)
        d_scope = Scope(project=scope.project, deliverable=child.name)
        entries.append((child.name, d_phase, d_scope))

    if not entries:
        return

    lines.append("## Deliverables")
    for name, d_phase, d_scope in entries:
        lines.append(f"- **{name}** ({d_phase} phase)")
        if d_scope.scope_md_path.is_file():
            lines.append(f"  - Scope: deliverables/{name}/scope.md")
        if d_scope.design_md_path.is_file():
            lines.append(f"  - Design: deliverables/{name}/design.md")
    lines.append("")


def _active_work(lines: list[str], scope: Scope) -> None:
    mm = load_milestones_manifest(scope.milestones_manifest_path)
    active_milestones = [m for m in mm.milestones if m.status == "active"]
    if not active_milestones:
        return

    lines.append("## Active Work")
    for milestone in active_milestones:
        m_tasks = [t for t in mm.tasks if t.milestone == milestone.id]
        done_count = sum(1 for t in m_tasks if t.status == "done")
        lines.append(
            f"- Milestone {milestone.id} \"{milestone.title}\" "
            f"(active, {done_count}/{len(m_tasks)} tasks done)"
        )
        for t in m_tasks:
            if t.status in ("active", "planned"):
                lines.append(f"  - Task {t.id} \"{t.title}\" ({t.status})")
    lines.append("")


def _workflow(lines: list[str], resolved: dict[str, Trigger]) -> None:
    lines.append("## AI Workflow")
    for name, trigger in resolved.items():
        instruction = _trigger_instruction(trigger)
        lines.append(f"- {instruction}")
    lines.append("")


def _trigger_instruction(trigger: Trigger) -> str:
    event_desc = trigger.event.replace(".", " ").replace("post", "").strip()
    when_desc = ""
    if trigger.when:
        parts = []
        if trigger.when.to:
            parts.append(f"to={trigger.when.to}")
        if trigger.when.from_state:
            parts.append(f"from={trigger.when.from_state}")
        if parts:
            when_desc = f" (when {', '.join(parts)})"

    mode_desc = f" --{trigger.mode}" if trigger.mode else ""
    return f"After {event_desc}{when_desc}: run /{trigger.action}{mode_desc}"


def _extra(lines: list[str], unit_dir: Path, extra_path: str) -> None:
    full = unit_dir / extra_path
    if full.is_file():
        lines.append(full.read_text().rstrip())
        lines.append("")


def _rel(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)
