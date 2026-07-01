"""`keel phase [PHASE]`."""

from __future__ import annotations

from datetime import date

import typer

from keel import templates, workspace
from keel.api import (
    ErrorCode,
    LifecycleNotFoundError,
    OpLog,
    Output,
    load_lifecycle,
    load_project_manifest,
    resolve_cli_scope,
)
from keel.hooks import HookAborted, hook_event, hookable
from keel.hooks.builtin_listeners import register_builtin_listeners

# Activate built-in pre-phase listeners on first import of this module.
register_builtin_listeners()


def _read_phase(scope: workspace.Scope) -> tuple[str, list[str]]:
    """Returns (current_phase, history_lines). History lines are everything after line 1."""
    current = workspace.read_phase(scope.unit_dir)
    path = scope.phase_path
    if not path.is_file():
        return current, []
    lines = path.read_text().splitlines()
    return current, lines[1:]


@hookable("project.phase")
def cmd_phase(
    ctx: typer.Context,
    phase: str | None = typer.Argument(
        None, help="Target phase to transition to. Mutually exclusive with --next."
    ),
    next_phase: bool = typer.Option(False, "--next", help="Advance one step in the lifecycle."),
    deliverable: str | None = typer.Option(
        None, "-D", "--deliverable", help="Phase scope: deliverable instead of project."
    ),
    project: str | None = typer.Option(
        None, "--project", "-p", help="Project name. Auto-detected from CWD if omitted."
    ),
    message: str | None = typer.Option(
        None, "-m", "--message", help="Optional note recorded in the phase history."
    ),
    no_decision: bool = typer.Option(
        False, "--no-decision", help="Skip auto-creating a phase-transition decision file."
    ),
    no_verify: bool = typer.Option(
        False, "--no-verify", help="Skip all project.phase.pre hooks (in-tree + plugin + user-script)."
    ),
    yes: bool = typer.Option(False, "-y", "--yes", help="Skip the warning confirmation prompt."),
    list_next: bool = typer.Option(
        False,
        "--list-next",
        help="Print the valid next phase(s) from the current state and exit (no transition).",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print intended operations and exit; write nothing."
    ),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout."),
) -> None:
    """Show or transition the phase."""
    out = Output.from_context(ctx, json_mode=json_mode)

    scope = resolve_cli_scope(project, deliverable, out=out)
    project = scope.project
    deliverable = scope.deliverable

    path = scope.phase_path
    current, history = _read_phase(scope)

    # Load the project's lifecycle (deliverables inherit from their parent project)
    try:
        project_scope = workspace.Scope(project=scope.project, deliverable=None)
        manifest = load_project_manifest(project_scope.manifest_path)
        lc = load_lifecycle(manifest.project.lifecycle)
    except LifecycleNotFoundError as e:
        out.fail(f"lifecycle not found: {e}", code=ErrorCode.NOT_FOUND)

    # --list-next mode: show valid next transitions and exit
    if list_next:
        nexts = lc.successors(current) if current in lc.states else []
        if json_mode:
            out.result({"current": current, "next": nexts})
        else:
            if nexts:
                out.info(f"Current: {current} → next: {', '.join(nexts)}")
            else:
                out.info(f"Current: {current} (end of lifecycle)")
        return

    if phase is None and not next_phase:
        # Show mode
        scope_name = f"{project}/{deliverable}" if deliverable else project
        if json_mode:
            out.result(
                {
                    "scope": "deliverable" if deliverable else "project",
                    "name": scope_name,
                    "phase": current,
                    "history": [{"line": h} for h in history if h.strip()],
                }
            )
            return
        out.result(
            None,
            human_text=f"{scope_name}\nphase: {current}\n\n" + "\n".join(history)
            if history
            else f"{scope_name}\nphase: {current}",
        )
        return

    # Transition mode
    target = phase
    if next_phase:
        if current not in lc.states:
            out.fail(f"invalid current phase: {current}", code=ErrorCode.INVALID_PHASE)
        explicit_successors = [s for s in lc.successors(current) if s != "cancelled"]
        if not explicit_successors:
            out.fail(
                f"no forward transition from '{current}' (state is terminal or has no non-cancel edges)",
                code=ErrorCode.END_OF_LIFECYCLE,
            )
        target = explicit_successors[0]

    if target not in lc.states:
        out.fail(
            f"unknown phase '{target}' for lifecycle '{lc.name}'",
            code=ErrorCode.INVALID_PHASE,
        )

    if target != current and target not in lc.successors(current):
        out.fail(
            f"cannot transition from '{current}' to '{target}' "
            f"(allowed: {', '.join(lc.successors(current)) or 'none'})",
            code=ErrorCode.INVALID_STATE,
        )

    if target == current:
        out.info(f"already in phase: {current}")
        return

    if dry_run:
        log = OpLog()
        log.modify_file(path, diff=f"{current} → {target}")
        if not no_decision:
            today = date.today().isoformat()
            log.create_file(scope.decisions_dir / f"{today}-phase-{target}.md", size=0)
        out.info(log.format_summary())
        return

    # Fire pre-phase + body + post-phase via hook_event.
    try:
        with hook_event(
            "project.phase",
            project=project,
            deliverable=deliverable,
            payload={"from": current, "to": target},
            positional_args=(current, target),
            out=out,
            no_verify=no_verify,
        ):
            # Apply transition.
            today = date.today().isoformat()
            history_line = f"{today}  {current} → {target}"
            if message:
                history_line += f"  ({message})"
            new_lines = [target] + [history_line] + history
            scope.keel_dir.mkdir(parents=True, exist_ok=True)
            path.write_text("\n".join(new_lines) + "\n")

            # Auto-create phase decision file.
            if not no_decision:
                _decisions_dir = scope.decisions_dir
                _decisions_dir.mkdir(parents=True, exist_ok=True)
                decision_path = _decisions_dir / f"{today}-phase-{target}.md"
                if not decision_path.exists():
                    decision_path.write_text(
                        templates.render(
                            "decision_entry.j2",
                            date=today,
                            title=f"Phase transition: {current} → {target}",
                        )
                    )
    except HookAborted as e:
        out.fail(
            f"phase transition blocked: {e} (use --no-verify to override)",
            code=ErrorCode.PREFLIGHT_BLOCKED,
        )

    out.result(
        {
            "scope": "deliverable" if deliverable else "project",
            "name": f"{project}/{deliverable}" if deliverable else project,
            "phase": target,
            "transitioned_from": current,
        },
        human_text=f"Phase: {current} → {target}",
    )
