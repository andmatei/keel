"""Built-in pre-phase subscribers — keel's default-lifecycle checks.

These replace the legacy `keel.preflights.builtin` classes. Each function
inspects the event payload's (from, to) tuple and either:
- returns silently (this rule doesn't apply to this transition)
- calls out.warn(...) (advisory; user can continue)
- raises HookAborted(...) (blocks the transition)

Registration is idempotent — call register_builtin_listeners() at most
once per process; subsequent calls are no-ops.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from keel.hooks import HookAborted, HookEvent, subscribes_to
from keel.hooks.registry import _REGISTRY

if TYPE_CHECKING:
    from keel.output import Output
    from keel.workspace import Scope


def _scope_from_event(event: HookEvent) -> Scope:
    """Reconstruct a Scope from event.project / event.deliverable."""
    from keel.workspace import Scope

    return Scope(project=event.project, deliverable=event.deliverable)


def _template_diff(scope: Scope, filename: str, template_name: str) -> bool:
    """True if the file on disk differs from a fresh template render."""
    # Intentionally uses the package-default render() rather than render_for_scope().
    # The preflight checks whether the file still matches the ORIGINAL scaffold output.
    # Using render_for_scope() would make the check sensitive to workspace template
    # overrides installed after scaffolding, causing false "file is edited" results.
    from keel.templates import render

    path = scope.unit_dir / filename
    if not path.is_file():
        return True  # missing file counts as "different"
    actual = path.read_text()
    rendered = render(template_name, name=scope.project, description="")
    return actual.strip() != rendered.strip()


def _check_scope_md_edited(event: HookEvent, *, out: Output) -> None:
    """Warn when leaving 'scoping' if scope.md is still the template scaffold."""
    fr = event.payload.get("from")
    to = event.payload.get("to")
    if (fr, to) != ("scoping", "designing"):
        return
    scope = _scope_from_event(event)
    if not _template_diff(scope, "scope.md", "scope_md.j2"):
        out.warn("preflight: scope.md is still the template scaffold")


def _check_design_md_edited(event: HookEvent, *, out: Output) -> None:
    """Warn when leaving 'designing' if design.md is unedited or no decisions exist."""
    fr = event.payload.get("from")
    to = event.payload.get("to")
    if (fr, to) != ("designing", "poc"):
        return
    scope = _scope_from_event(event)
    if not _template_diff(scope, "design.md", "design_md.j2"):
        out.warn("preflight: design.md is still the template scaffold")
    decisions = scope.decisions_dir
    if not decisions.is_dir() or not any(decisions.glob("*.md")):
        out.warn("preflight: no decision records under decisions/")


def _check_milestone_exists(event: HookEvent, *, out: Output) -> None:
    """Block 'poc → implementing' if no milestones are defined."""
    fr = event.payload.get("from")
    to = event.payload.get("to")
    if (fr, to) != ("poc", "implementing"):
        return
    from keel.manifest import load_milestones_manifest

    scope = _scope_from_event(event)
    manifest = load_milestones_manifest(scope.milestones_manifest_path)
    if not manifest.milestones:
        raise HookAborted("no milestones defined; add one with 'keel milestone add'")


def _check_milestones_complete(event: HookEvent, *, out: Output) -> None:
    """Warn on 'shipping' / block on 'done' if any milestones are unfinished."""
    to = event.payload.get("to")
    if to not in ("shipping", "done"):
        return
    from keel.manifest import load_milestones_manifest

    scope = _scope_from_event(event)
    manifest = load_milestones_manifest(scope.milestones_manifest_path)
    unfinished = [ms.id for ms in manifest.milestones if ms.status not in ("done", "cancelled")]
    if not unfinished:
        return
    msg = f"unfinished milestones: {', '.join(unfinished)}"
    if to == "done":
        raise HookAborted(msg)
    out.warn(f"preflight: {msg}")


def _check_worktrees_clean(event: HookEvent, *, out: Output) -> None:
    """Warn when transitioning 'shipping → done' with dirty worktrees."""
    fr = event.payload.get("from")
    to = event.payload.get("to")
    if (fr, to) != ("shipping", "done"):
        return
    from keel import git
    from keel.manifest import load_project_manifest

    scope = _scope_from_event(event)
    try:
        pm = load_project_manifest(scope.manifest_path)
    except Exception:
        return
    unit_dir = scope.unit_dir
    dirty = []
    for repo in pm.repos:
        wt = unit_dir / repo.worktree
        if wt.is_dir() and git.is_worktree_dirty(wt):
            dirty.append(str(wt))
    if dirty:
        out.warn(f"preflight: dirty worktrees: {', '.join(dirty)}")


_BUILTIN_LISTENERS = (
    _check_scope_md_edited,
    _check_design_md_edited,
    _check_milestone_exists,
    _check_milestones_complete,
    _check_worktrees_clean,
)


def register_builtin_listeners() -> None:
    """Register all built-in pre-phase listeners. Idempotent."""
    existing = set(_REGISTRY.get("project.phase.pre", []))
    for fn in _BUILTIN_LISTENERS:
        if fn not in existing:
            subscribes_to("project.phase.pre")(fn)
