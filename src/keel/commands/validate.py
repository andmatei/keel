"""`keel validate`."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import typer
from rich.table import Table

from keel import git, workspace
from keel.api import Output, load_project_manifest


@dataclass
class _Finding:
    check: str
    level: str  # "pass" | "warn" | "fail"
    message: str
    path: str = field(default="")


def _check_required_design_files(unit_dir: Path, label: str) -> list[_Finding]:
    """Verify the required scaffolding files exist at the unit root."""
    findings: list[_Finding] = []
    # Per the new layout: design.md and the phase file under .keel/ are the canonical files.
    for required, path in (
        ("design.md", unit_dir / "design.md"),
        ("phase", unit_dir / ".keel" / "phase"),
    ):
        if path.is_file():
            findings.append(
                _Finding("required-files", "pass", f"{label} has {required}", str(path))
            )
        else:
            findings.append(
                _Finding("required-files", "fail", f"{label} missing {required}", str(path))
            )
    return findings


def _check_manifest(
    manifest_path: Path, loader, label: str
) -> tuple[list[_Finding], object | None]:
    if not manifest_path.is_file():
        return [_Finding("manifest", "fail", f"{label} manifest missing", str(manifest_path))], None
    try:
        m = loader(manifest_path)
        return [_Finding("manifest", "pass", f"{label} manifest valid", str(manifest_path))], m
    except Exception as e:
        return [
            _Finding("manifest", "fail", f"{label} manifest invalid: {e}", str(manifest_path))
        ], None


def _check_worktrees(unit_dir: Path, repos, label: str) -> list[_Finding]:
    findings: list[_Finding] = []
    for r in repos:
        wt = unit_dir / r.worktree
        if not wt.is_dir():
            findings.append(
                _Finding(
                    "worktree",
                    "warn",
                    f"{label} declares worktree {r.worktree} but dir missing",
                    str(wt),
                )
            )
            continue
        if not git.is_git_repo(wt):
            findings.append(
                _Finding(
                    "worktree",
                    "fail",
                    f"{label} worktree {r.worktree} is not a git worktree",
                    str(wt),
                )
            )
            continue
        if r.branch_prefix:
            try:
                cur = git.current_branch(wt)
                if cur and not cur.startswith(r.branch_prefix):
                    findings.append(
                        _Finding(
                            "worktree",
                            "warn",
                            f"{label} worktree {r.worktree} branch '{cur}' doesn't start with prefix '{r.branch_prefix}'",
                            str(wt),
                        )
                    )
                else:
                    findings.append(
                        _Finding("worktree", "pass", f"{label} worktree {r.worktree} OK", str(wt))
                    )
            except git.GitError:
                findings.append(
                    _Finding(
                        "worktree",
                        "warn",
                        f"{label} couldn't read branch for {r.worktree}",
                        str(wt),
                    )
                )
        else:
            findings.append(
                _Finding("worktree", "pass", f"{label} worktree {r.worktree} OK", str(wt))
            )
    return findings


def _check_deliverable_references(scope: workspace.Scope) -> list[_Finding]:
    """Detect orphan deliverables: a unit dir with `project.toml` that the parent's
    `design.md` doesn't mention under `## Deliverables`.
    """
    findings: list[_Finding] = []
    deliv_dir = scope.unit_dir / "deliverables"
    if not deliv_dir.is_dir():
        return findings
    parent_design = scope.design_md_path
    parent_text = parent_design.read_text() if parent_design.is_file() else ""
    for d in sorted(deliv_dir.iterdir()):
        if not d.is_dir() or not (d / "project.toml").is_file():
            continue
        if f"**{d.name}**" not in parent_text:
            findings.append(
                _Finding(
                    "refs",
                    "warn",
                    f"deliverable '{d.name}' exists on disk but not mentioned in parent design.md",
                    str(parent_design),
                )
            )
    return findings


def cmd_validate(
    ctx: typer.Context,
    name: str | None = typer.Argument(
        None, help="Project name. Auto-detected from CWD if omitted."
    ),
    strict: bool = typer.Option(
        False, "--strict", help="Treat warnings as failures (exit 1 if any warn)."
    ),
    check: str | None = typer.Option(
        None,
        "--check",
        help="Comma-separated list of check names to run (e.g. 'manifest,worktree').",
    ),
    content: bool = typer.Option(
        False,
        "--content",
        help="Run additional content checks (decision frontmatter, design.md sections).",
    ),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout."),
) -> None:
    """Validate project structure and (optionally) content."""
    out = Output.from_context(ctx, json_mode=json_mode)
    scope = workspace.resolve_cli_scope(name, None, allow_deliverable=False, out=out)

    findings: list[_Finding] = []

    # Project-level checks
    proj_dir = scope.unit_dir
    findings.extend(_check_required_design_files(proj_dir, "project"))
    proj_findings, m = _check_manifest(scope.manifest_path, load_project_manifest, "project")
    findings.extend(proj_findings)
    if m is not None:
        findings.extend(_check_worktrees(proj_dir, m.repos, "project"))
    findings.extend(_check_deliverable_references(scope))

    # Deliverables
    deliv_dir = proj_dir / "deliverables"
    if deliv_dir.is_dir():
        for d in sorted(deliv_dir.iterdir()):
            if not d.is_dir():
                continue
            label = f"deliverable {d.name}"
            findings.extend(_check_required_design_files(d, label))
            d_manifest = d / "project.toml"
            d_findings, dm = _check_manifest(d_manifest, load_project_manifest, label)
            findings.extend(d_findings)
            if dm is not None:
                findings.extend(_check_worktrees(d, dm.repos, label))

    # Filter by --check
    if check:
        wanted = {c.strip() for c in check.split(",")}
        findings = [f for f in findings if f.check in wanted]

    # Tally
    tally: dict[str, int] = {"pass": 0, "warn": 0, "fail": 0}
    for f in findings:
        tally[f.level] = tally.get(f.level, 0) + 1

    if json_mode:
        out.result(
            {
                "findings": [
                    {"check": f.check, "level": f.level, "message": f.message, "path": f.path}
                    for f in findings
                ],
                "summary": tally,
            }
        )
    else:
        if not findings:
            out.result(None, human_text="(no findings)")
        else:
            table = Table()
            table.add_column("Level")
            table.add_column("Check")
            table.add_column("Message")
            for f in findings:
                color = {"pass": "green", "warn": "yellow", "fail": "red"}.get(f.level, "white")
                table.add_row(f"[{color}]{f.level}[/{color}]", f.check, f.message)
            out.print_rich(table)
            out.result(
                None,
                human_text=f"summary: {tally['pass']} pass, {tally['warn']} warn, {tally['fail']} fail",
            )

    # Exit code
    if tally["fail"] > 0:
        raise typer.Exit(code=1)
    if strict and tally["warn"] > 0:
        raise typer.Exit(code=1)
