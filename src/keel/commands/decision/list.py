"""`keel decision list`."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import typer
from rich.table import Table

from keel import workspace
from keel.api import Output, resolve_cli_scope


@dataclass
class _DecisionRow:
    date: str
    slug: str
    title: str
    status: str
    path: Path


_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)


def _parse_frontmatter(text: str) -> dict[str, str]:
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}
    fields: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fields[k.strip()] = v.strip()
    return fields


def _scan(decisions_dir: Path) -> list[_DecisionRow]:
    rows: list[_DecisionRow] = []
    if not decisions_dir.is_dir():
        return rows
    for f in sorted(decisions_dir.glob("*.md"), reverse=True):
        text = f.read_text()
        fm = _parse_frontmatter(text)
        # Filename format: YYYY-MM-DD-slug.md
        stem = f.stem
        if len(stem) > 10 and stem[10] == "-":
            d, slug = stem[:10], stem[11:]
        else:
            d, slug = "", stem
        rows.append(
            _DecisionRow(
                date=fm.get("date", d),
                slug=slug,
                title=fm.get("title", slug),
                status=fm.get("status", "unknown"),
                path=f,
            )
        )
    return rows


def cmd_list(
    ctx: typer.Context,
    deliverable: str | None = typer.Option(
        None,
        "-D",
        "--deliverable",
        help="Decision scope: a deliverable instead of the project. Auto-detected from CWD.",
    ),
    project: str | None = typer.Option(
        None, "--project", "-p", help="Project name. Auto-detected from CWD if omitted."
    ),
    all_scopes: bool = typer.Option(
        False, "--all", help="Include parent project decisions when at deliverable scope."
    ),
    status: str | None = typer.Option(
        None,
        "--status",
        help="Filter by frontmatter 'status' (e.g., proposed, accepted, superseded).",
    ),
    since: str | None = typer.Option(
        None, "--since", help="Show only decisions on or after this date (YYYY-MM-DD)."
    ),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout."),
) -> None:
    """List decisions at the current scope."""
    out = Output.from_context(ctx, json_mode=json_mode)

    scope = resolve_cli_scope(project, deliverable, out=out)
    project = scope.project
    deliverable = scope.deliverable

    rows: list[_DecisionRow] = []
    if deliverable:
        rows.extend(_scan(scope.decisions_dir))
        if all_scopes:
            rows.extend(_scan(workspace.Scope(project=project, deliverable=None).decisions_dir))
    else:
        rows.extend(_scan(scope.decisions_dir))

    if status:
        rows = [r for r in rows if r.status == status]
    if since:
        rows = [r for r in rows if r.date >= since]

    rows.sort(key=lambda r: r.date, reverse=True)

    if json_mode:
        out.result(
            {
                "decisions": [
                    {
                        "date": r.date,
                        "slug": r.slug,
                        "title": r.title,
                        "status": r.status,
                        "path": str(r.path),
                    }
                    for r in rows
                ]
            }
        )
        return

    if not rows:
        out.result(None, human_text="(no decisions)")
        return

    table = Table()
    table.add_column("Date")
    table.add_column("Slug")
    table.add_column("Status")
    table.add_column("Title")
    for r in rows:
        table.add_row(r.date, r.slug, r.status, r.title)
    out.print_rich(table)
