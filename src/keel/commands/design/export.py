"""`keel design export`."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import typer

from keel import workspace
from keel.api import Output, load_project_manifest

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)


def _split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    fm: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    return fm, text[m.end() :]


@dataclass
class _Decision:
    path: Path
    label: str  # e.g. "D.1"
    title: str
    body: str
    status: str
    superseded: bool


def _collect_decisions(
    decisions_dir: Path, *, include_superseded: bool, start_index: int
) -> list[_Decision]:
    if not decisions_dir.is_dir():
        return []
    out: list[_Decision] = []
    idx = start_index
    for f in sorted(decisions_dir.glob("*.md")):
        text = f.read_text()
        fm, body = _split_frontmatter(text)
        status = fm.get("status", "proposed")
        superseded = status.lower() == "superseded"
        if superseded and not include_superseded:
            continue
        title = fm.get("title", f.stem)
        # Strip a leading "# Title" heading from the body if present (we'll re-render it)
        body_stripped = re.sub(r"^# .+?\n+", "", body, count=1)
        out.append(
            _Decision(
                path=f,
                label=f"D.{idx}",
                title=title,
                body=body_stripped.rstrip("\n"),
                status=status,
                superseded=superseded,
            )
        )
        idx += 1
    return out


def _replace_decision_links(design_text: str, decisions: Iterable[_Decision]) -> str:
    """Replace `[text](decisions/<file>.md)` links with `text (Appendix D.N)`."""
    for d in decisions:
        rel = f"decisions/{d.path.name}"
        # Match [any text](decisions/<file>.md) and replace with `text (Appendix D.N)`
        pattern = rf"\[([^\]]*)\]\({re.escape(rel)}\)"
        design_text = re.sub(
            pattern,
            lambda m, label=d.label: f"{m.group(1)} (Appendix {label})",
            design_text,
        )
    return design_text


def cmd_export(
    ctx: typer.Context,
    name: str | None = typer.Argument(
        None, help="Project name. Auto-detected from CWD if omitted."
    ),
    deliverable: str | None = typer.Option(
        None, "-D", "--deliverable", help="Export this deliverable instead of the whole project."
    ),
    project: str | None = typer.Option(
        None, "--project", "-p", help="Project name. Auto-detected from CWD if omitted."
    ),
    no_decisions: bool = typer.Option(False, "--no-decisions", help="Skip the decisions appendix."),
    no_deliverables: bool = typer.Option(
        False,
        "--no-deliverables",
        help="At project level, export parent only (skip deliverable sections).",
    ),
    include_scope: bool = typer.Option(
        False, "--include-scope", help="Prepend the scope.md as a Scope section."
    ),
    include_superseded: bool = typer.Option(
        False, "--include-superseded", help="Include superseded decisions in the appendix."
    ),
    output: Path | None = typer.Option(
        None, "-o", "--output", help="Write to this file instead of stdout."
    ),
    json_mode: bool = typer.Option(False, "--json", help="Emit JSON envelope around the markdown."),
) -> None:
    """Compose a project's or deliverable's design + decisions into a single markdown document."""
    out_obj = Output.from_context(ctx, json_mode=json_mode)
    project = project or name
    scope = workspace.resolve_cli_scope(project, deliverable, out=out_obj)
    project = scope.project
    deliverable = scope.deliverable

    sections: list[str] = []
    appendix: list[_Decision] = []

    if deliverable:
        m = load_project_manifest(scope.manifest_path)
        title = m.project.name
        sections.append(f"# {title}\n")
        if include_scope:
            scope_path = scope.scope_md_path
            if scope_path.is_file():
                sections.append("## Scope\n\n" + scope_path.read_text().strip())
        decisions = (
            _collect_decisions(
                scope.decisions_dir,
                include_superseded=include_superseded,
                start_index=1,
            )
            if not no_decisions
            else []
        )
        appendix.extend(decisions)
        design_path = scope.design_md_path
        if design_path.is_file():
            text = design_path.read_text().strip()
            text = _replace_decision_links(text, decisions)
            sections.append("## Design\n\n" + text)
    else:
        # Project-level composition
        unit_dir = scope.unit_dir
        m = load_project_manifest(scope.manifest_path)
        title = m.project.name
        sections.append(f"# {title}\n")
        if include_scope:
            scope_path = scope.scope_md_path
            if scope_path.is_file():
                sections.append("## Scope\n\n" + scope_path.read_text().strip())

        # Project decisions get D.1...
        proj_decisions = (
            _collect_decisions(
                scope.decisions_dir,
                include_superseded=include_superseded,
                start_index=1,
            )
            if not no_decisions
            else []
        )
        appendix.extend(proj_decisions)
        next_idx = len(proj_decisions) + 1

        # Project design
        design_path = scope.design_md_path
        if design_path.is_file():
            text = design_path.read_text().strip()
            text = _replace_decision_links(text, proj_decisions)
            sections.append("## Project Design\n\n" + text)

        # Deliverables
        if not no_deliverables:
            deliv_dir = unit_dir / "deliverables"
            if deliv_dir.is_dir():
                for d in sorted(deliv_dir.iterdir()):
                    d_manifest = d / "project.toml"
                    if not d_manifest.is_file():
                        continue
                    d_decisions = (
                        _collect_decisions(
                            d / "decisions",
                            include_superseded=include_superseded,
                            start_index=next_idx,
                        )
                        if not no_decisions
                        else []
                    )
                    next_idx += len(d_decisions)
                    appendix.extend(d_decisions)
                    d_design = d / "design.md"
                    if d_design.is_file():
                        d_text = d_design.read_text().strip()
                        d_text = _replace_decision_links(d_text, d_decisions)
                        sections.append(f"## Deliverable: {d.name}\n\n{d_text}")

    if appendix and not no_decisions:
        sections.append("---\n")
        sections.append("## Appendix: Decisions\n")
        for d in appendix:
            sections.append(f"### Appendix {d.label}: {d.title}\n\n{d.body}")

    full = "\n\n".join(sections) + "\n"

    if output:
        output.write_text(full)
        out_obj.info(f"Written: {output}")
        if json_mode:
            out_obj.result({"path": str(output), "size": len(full)})
        else:
            out_obj.result(None, human_text=str(output))
    else:
        if json_mode:
            out_obj.result({"markdown": full})
        else:
            print(full)
