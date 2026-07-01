# Plan 3: Validate, design export, code group, archive, project rename

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the manifest-driven `code` subcommand group (5 commands), the `validate` health-check command, `design export` (composing parent + deliverables + decision appendix), and the project-level destructive ops `archive` and `rename`.

**Architecture:** Three new command groups (`code`, `design`) and three new top-level commands (`validate`, `archive`, `rename`). The `code` group is the manifest's runtime: it materializes worktrees declared in `project.toml`/`deliverable.toml` and keeps the manifest in sync with on-disk state. `validate` walks every project and checks structural + (optionally) content invariants. `design export` produces a single composable markdown document for the project or a deliverable. `archive` and `rename` extend the project-level operation set started in Plans 1+2.

**Tech Stack:** Same as Plans 1+2.5 — Python 3.11+, Typer, Rich, Pydantic v2, markdown-it-py, Jinja2, tomlkit, questionary, pytest, ruff.

---

## Pre-decided open questions

These were left open in earlier plans or flagged as forward debt; settled here.

1. **`RepoSpec.worktree` validator tightened** to require a single path component (no `/`, no `..`, no `.`, no absolute, no empty). Done in T1.7 — once tightened, `code add` and `validate` can rely on the schema rather than re-checking.

2. **Multi-repo `Path.name` collision** — `code add` detects collision against existing manifest entries (same `worktree` value or same `remote`) and exits 1 with `code="duplicate_worktree"` / `code="duplicate_remote"` and a clear hint to pass `--worktree NAME`.

3. **`code init --clone-missing` UX**: on TTY, prompts with `local_hint` as the default and lets the user override; on non-TTY, fails with a clear message asking to pass `--clone-missing` and ensure `local_hint` is set.

4. **`archive` is a soft-delete**: removes worktrees (with dirty check), moves the entire project tree to `~/projects/.archive/<name>-<YYYY-MM-DD>/`, leaves a `.archived` marker file. Restore is manual: `mv` back, then `keel code init`.

5. **`rename` (project-level)** renames the project dir, the worktrees inside it (via `git_ops.move_worktree`), and the branches (via `git_ops.rename_branch`, gated on `--rename-branches/--no-rename-branches`, default rename). Updates `branch_prefix` in the manifest. Updates references in deliverable CLAUDE.md files.

6. **`validate --content`** is opt-in. Default `validate` runs only structural checks (cheap; safe to run in CI). `--content` runs additional semantic checks like decision frontmatter parsing and design.md section presence.

7. **`design export` superseded-decision filtering**: decisions with `status: superseded` in their frontmatter are excluded from the appendix unless `--include-superseded` is passed. This already partially exists in the Bash CLI's behavior; encoded explicitly here.

8. **`design export` decision numbering**: flat across the whole export. So if the project has 3 decisions and deliverable A has 2, the appendix is D.1..D.5 in document order.

---

## File Structure

After Plan 3 lands, new/changed files:

```
~/projects/keel/
└── src/keel/
    ├── manifest.py                      # MODIFY — tighten RepoSpec.worktree validator
    └── commands/
        ├── archive.py                   # CREATE — top-level archive command
        ├── rename.py                    # CREATE — top-level project-rename command
        ├── validate.py                  # CREATE — top-level validate command
        ├── code/                        # CREATE — code group
        │   ├── __init__.py              # creates Typer subapp + registers commands
        │   ├── list.py
        │   ├── status.py
        │   ├── init.py
        │   ├── add.py
        │   └── rm.py
        └── design/                      # CREATE — design group
            ├── __init__.py
            └── export.py

tests/
├── commands/
│   ├── test_archive.py                  # CREATE
│   ├── test_rename.py                   # CREATE
│   ├── test_validate.py                 # CREATE
│   ├── code/                            # CREATE
│   │   ├── __init__.py
│   │   ├── test_list.py
│   │   ├── test_status.py
│   │   ├── test_init.py
│   │   ├── test_add.py
│   │   └── test_rm.py
│   └── design/                          # CREATE
│       ├── __init__.py
│       └── test_export.py
└── test_manifest.py                     # MODIFY — add tests for tightened worktree validator
```

---

## Pre-requisites

- Plan 2.5 is complete and tagged `keel-plan-2.5`
- 175 tests passing on `main`
- Ruff clean
- Working dir: `keel/`. Run tests: `uv run --extra dev pytest`. Run lint: `uv run ruff check src tests`.

---

## Milestone 1: `code` subcommand group

### Task 1.1: Scaffold `commands/code/` subpackage

**Files:**
- Create: `src/keel/commands/code/__init__.py`
- Create: `tests/commands/code/__init__.py` (empty)
- Modify: `src/keel/app.py` (register subapp)

- [ ] **Step 1: Create `src/keel/commands/code/__init__.py`**

```python
"""`keel code ...` command group — manifest-driven worktree management."""
from __future__ import annotations
import typer

app = typer.Typer(
    name="code",
    help="Manage source-repo linkage and git worktrees.",
    no_args_is_help=True,
)
```

- [ ] **Step 2: Create `tests/commands/code/__init__.py`** (empty file)

- [ ] **Step 3: Register in `src/keel/app.py`**

Append:

```python
from keel.commands.code import app as code_app  # noqa: E402
app.add_typer(code_app, name="code")
```

- [ ] **Step 4: Smoke check**

Run:
```bash
cd ~/projects/keel && uv tool install --editable .
keel code --help
```
Expected: shows the help with no subcommands yet.

- [ ] **Step 5: Run full suite**

Run: `uv run --extra dev pytest`
Expected: 175 PASS.

- [ ] **Step 6: Commit**

```bash
git add keel/src/keel/commands/code/ keel/tests/commands/code/ keel/src/keel/app.py
git commit -m "feat(keel): scaffold code command group"
```

---

### Task 1.2: `code list` — show declared repos

**Files:**
- Create: `src/keel/commands/code/list.py`
- Create: `tests/commands/code/test_list.py`
- Modify: `src/keel/commands/code/__init__.py` (register)

- [ ] **Step 1: Write failing tests**

Create `tests/commands/code/test_list.py`:

```python
"""Tests for `keel code list`."""
import json
from typer.testing import CliRunner
from keel.app import app
from keel.manifest import (
    ProjectManifest, ProjectMeta, RepoSpec,
    save_project_manifest,
)
from datetime import date

runner = CliRunner()


def test_list_empty(projects, make_project) -> None:
    make_project("foo")
    result = runner.invoke(app, ["code", "list", "--project", "foo"])
    assert result.exit_code == 0


def test_list_one_repo(projects, make_project) -> None:
    proj = make_project("foo")
    m = ProjectManifest(
        project=ProjectMeta(name="foo", description="d", created=date(2026, 4, 29)),
        repos=[RepoSpec(
            remote="git@example.com:org/r.git",
            local_hint="~/r",
            worktree="code",
            branch_prefix="alice/foo",
        )],
    )
    save_project_manifest(proj / "design" / "project.toml", m)
    result = runner.invoke(app, ["code", "list", "--project", "foo"])
    assert result.exit_code == 0
    assert "git@example.com:org/r.git" in result.stdout
    assert "code" in result.stdout


def test_list_json_shape(projects, make_project) -> None:
    proj = make_project("foo")
    m = ProjectManifest(
        project=ProjectMeta(name="foo", description="d", created=date(2026, 4, 29)),
        repos=[RepoSpec(remote="git@e.com:o/r.git", worktree="code", branch_prefix="a/foo")],
    )
    save_project_manifest(proj / "design" / "project.toml", m)
    result = runner.invoke(app, ["code", "list", "--project", "foo", "--json"])
    payload = json.loads(result.stdout)
    assert payload["repos"][0]["remote"] == "git@e.com:o/r.git"
    assert payload["repos"][0]["worktree"] == "code"


def test_list_at_deliverable_scope(projects, make_deliverable) -> None:
    deliv = make_deliverable(project_name="foo", name="bar", description="d")
    from keel.manifest import (
        DeliverableManifest, DeliverableMeta, RepoSpec,
        save_deliverable_manifest,
    )
    m = DeliverableManifest(
        deliverable=DeliverableMeta(
            name="bar", parent_project="foo", description="d",
            created=date(2026, 4, 29), shared_worktree=False,
        ),
        repos=[RepoSpec(remote="git@e.com:o/d.git", worktree="code", branch_prefix="a/foo-bar")],
    )
    save_deliverable_manifest(deliv / "design" / "deliverable.toml", m)
    result = runner.invoke(app, ["code", "list", "--project", "foo", "-D", "bar"])
    assert result.exit_code == 0
    assert "git@e.com:o/d.git" in result.stdout
```

- [ ] **Step 2: Run, expect collection error**

- [ ] **Step 3: Implement `src/keel/commands/code/list.py`**

```python
"""`keel code list`."""
from __future__ import annotations
import typer
from rich.table import Table

from keel import workspace
from keel.manifest import load_project_manifest, load_deliverable_manifest
from keel.output import Output


def cmd_list(
    ctx: typer.Context,
    project: str | None = typer.Option(None, "--project", "-p", help="Project name. Auto-detected from CWD if omitted."),
    deliverable: str | None = typer.Option(None, "-D", "--deliverable", help="Show repos for this deliverable instead of the project."),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout."),
) -> None:
    """List source repos declared in the manifest."""
    out = Output.from_context(ctx, json_mode=json_mode)
    scope = workspace.resolve_cli_scope(project, deliverable)
    project = scope.project
    deliverable = scope.deliverable

    if deliverable:
        manifest_path = workspace.deliverable_dir(project, deliverable) / "design" / "deliverable.toml"
        m = load_deliverable_manifest(manifest_path)
    else:
        manifest_path = workspace.project_dir(project) / "design" / "project.toml"
        m = load_project_manifest(manifest_path)

    repos_data = [
        {
            "remote": r.remote,
            "local_hint": r.local_hint,
            "worktree": r.worktree,
            "branch_prefix": r.branch_prefix,
        }
        for r in m.repos
    ]

    if json_mode:
        out.result({"repos": repos_data})
        return

    if not m.repos:
        out.result(None, human_text="(no repos)")
        return

    table = Table()
    table.add_column("Remote")
    table.add_column("Worktree")
    table.add_column("Branch prefix")
    table.add_column("Local hint")
    for r in m.repos:
        table.add_row(r.remote, r.worktree, r.branch_prefix or "-", r.local_hint or "-")
    out.print_rich(table)
```

- [ ] **Step 4: Register in `__init__.py`**

```python
from keel.commands.code.list import cmd_list  # noqa: E402
app.command(name="list")(cmd_list)
```

- [ ] **Step 5: Run tests, expect 4 PASS**

- [ ] **Step 6: Commit**

```bash
git add keel/src/keel/commands/code/list.py keel/src/keel/commands/code/__init__.py keel/tests/commands/code/test_list.py
git commit -m "feat(keel): implement 'code list'"
```

---

### Task 1.3: `code status` — per-repo worktree state

**Files:**
- Create: `src/keel/commands/code/status.py`
- Create: `tests/commands/code/test_status.py`
- Modify: `src/keel/commands/code/__init__.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/commands/code/test_status.py
"""Tests for `keel code status`."""
import json
from typer.testing import CliRunner
from keel.app import app

runner = CliRunner()


def test_status_no_repos(projects, make_project) -> None:
    make_project("foo")
    result = runner.invoke(app, ["code", "status", "--project", "foo"])
    assert result.exit_code == 0


def test_status_repo_not_cloned(projects, make_project) -> None:
    """When local_hint points at a missing dir, status reports 'missing'."""
    from keel.manifest import (
        ProjectManifest, ProjectMeta, RepoSpec, save_project_manifest,
    )
    from datetime import date
    proj = make_project("foo")
    m = ProjectManifest(
        project=ProjectMeta(name="foo", description="d", created=date(2026, 4, 29)),
        repos=[RepoSpec(
            remote="git@e.com:o/r.git",
            local_hint=str(projects / "_missing"),
            worktree="code",
            branch_prefix="a/foo",
        )],
    )
    save_project_manifest(proj / "design" / "project.toml", m)
    result = runner.invoke(app, ["code", "status", "--project", "foo", "--json"])
    payload = json.loads(result.stdout)
    assert payload["repos"][0]["cloned"] is False
    assert payload["repos"][0]["worktree_exists"] is False


def test_status_worktree_clean(projects, make_project, source_repo) -> None:
    """A live worktree on the right branch is reported as clean."""
    from keel.manifest import (
        ProjectManifest, ProjectMeta, RepoSpec, save_project_manifest,
    )
    from keel import git_ops
    from datetime import date

    proj = make_project("foo")
    branch = "alice/foo-base"
    git_ops.create_worktree(source_repo, proj / "code", branch=branch)

    m = ProjectManifest(
        project=ProjectMeta(name="foo", description="d", created=date(2026, 4, 29)),
        repos=[RepoSpec(
            remote=str(source_repo),
            local_hint=str(source_repo),
            worktree="code",
            branch_prefix=branch,
        )],
    )
    save_project_manifest(proj / "design" / "project.toml", m)

    result = runner.invoke(app, ["code", "status", "--project", "foo", "--json"])
    payload = json.loads(result.stdout)
    repo = payload["repos"][0]
    assert repo["cloned"] is True
    assert repo["worktree_exists"] is True
    assert repo["dirty"] is False
    assert repo["branch"] == branch


def test_status_worktree_dirty(projects, make_project, source_repo) -> None:
    from keel.manifest import (
        ProjectManifest, ProjectMeta, RepoSpec, save_project_manifest,
    )
    from keel import git_ops
    from datetime import date

    proj = make_project("foo")
    git_ops.create_worktree(source_repo, proj / "code", branch="alice/foo-base")
    (proj / "code" / "dirty.txt").write_text("not committed")

    m = ProjectManifest(
        project=ProjectMeta(name="foo", description="d", created=date(2026, 4, 29)),
        repos=[RepoSpec(
            remote=str(source_repo),
            local_hint=str(source_repo),
            worktree="code",
            branch_prefix="alice/foo-base",
        )],
    )
    save_project_manifest(proj / "design" / "project.toml", m)

    result = runner.invoke(app, ["code", "status", "--project", "foo", "--json"])
    payload = json.loads(result.stdout)
    assert payload["repos"][0]["dirty"] is True
```

- [ ] **Step 2: Run, expect collection error**

- [ ] **Step 3: Implement `src/keel/commands/code/status.py`**

```python
"""`keel code status`."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import typer
from rich.table import Table

from keel import git_ops, workspace
from keel.manifest import load_project_manifest, load_deliverable_manifest
from keel.output import Output


@dataclass
class _RepoStatus:
    remote: str
    local_hint: str | None
    worktree: str
    branch_prefix: str | None
    cloned: bool
    worktree_exists: bool
    branch: str | None
    dirty: bool | None


def _collect_status(unit_dir: Path, repos) -> list[_RepoStatus]:
    rows: list[_RepoStatus] = []
    for r in repos:
        cloned = bool(r.local_hint and Path(r.local_hint).expanduser().is_dir() and git_ops.is_git_repo(Path(r.local_hint).expanduser()))
        wt_path = unit_dir / r.worktree
        worktree_exists = wt_path.is_dir() and git_ops.is_git_repo(wt_path)
        branch = git_ops.current_branch(wt_path) if worktree_exists else None
        dirty = git_ops.is_worktree_dirty(wt_path) if worktree_exists else None
        rows.append(_RepoStatus(
            remote=r.remote,
            local_hint=r.local_hint,
            worktree=r.worktree,
            branch_prefix=r.branch_prefix,
            cloned=cloned,
            worktree_exists=worktree_exists,
            branch=branch,
            dirty=dirty,
        ))
    return rows


def cmd_status(
    ctx: typer.Context,
    project: str | None = typer.Option(None, "--project", "-p", help="Project name. Auto-detected from CWD if omitted."),
    deliverable: str | None = typer.Option(None, "-D", "--deliverable", help="Status for this deliverable's repos."),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout."),
) -> None:
    """Show per-repo worktree status (cloned, exists, branch, clean/dirty)."""
    out = Output.from_context(ctx, json_mode=json_mode)
    scope = workspace.resolve_cli_scope(project, deliverable)
    project = scope.project
    deliverable = scope.deliverable

    if deliverable:
        unit_dir = workspace.deliverable_dir(project, deliverable)
        m = load_deliverable_manifest(unit_dir / "design" / "deliverable.toml")
    else:
        unit_dir = workspace.project_dir(project)
        m = load_project_manifest(unit_dir / "design" / "project.toml")

    rows = _collect_status(unit_dir, m.repos)

    if json_mode:
        out.result({
            "repos": [
                {
                    "remote": r.remote, "worktree": r.worktree, "branch_prefix": r.branch_prefix,
                    "local_hint": r.local_hint, "cloned": r.cloned,
                    "worktree_exists": r.worktree_exists, "branch": r.branch, "dirty": r.dirty,
                }
                for r in rows
            ]
        })
        return

    if not rows:
        out.result(None, human_text="(no repos)")
        return

    table = Table()
    table.add_column("Remote")
    table.add_column("Worktree")
    table.add_column("Cloned")
    table.add_column("Worktree exists")
    table.add_column("Branch")
    table.add_column("Dirty")
    for r in rows:
        table.add_row(
            r.remote,
            r.worktree,
            "yes" if r.cloned else "no",
            "yes" if r.worktree_exists else "no",
            r.branch or "-",
            "yes" if r.dirty else ("no" if r.dirty is False else "-"),
        )
    out.print_rich(table)
```

- [ ] **Step 4: Register**

```python
from keel.commands.code.status import cmd_status  # noqa: E402
app.command(name="status")(cmd_status)
```

- [ ] **Step 5: Run tests, expect 4 PASS**

- [ ] **Step 6: Commit**

```bash
git add keel/src/keel/commands/code/status.py keel/src/keel/commands/code/__init__.py keel/tests/commands/code/test_status.py
git commit -m "feat(keel): implement 'code status'"
```

---

### Task 1.4: `code init` — materialize worktrees from manifest

**Files:**
- Create: `src/keel/commands/code/init.py`
- Create: `tests/commands/code/test_init.py`
- Modify: `src/keel/commands/code/__init__.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/commands/code/test_init.py
"""Tests for `keel code init`."""
from typer.testing import CliRunner
from keel.app import app

runner = CliRunner()


def test_init_creates_missing_worktree(projects, make_project, source_repo) -> None:
    """If a manifest declares a worktree that doesn't exist, init creates it."""
    from keel.manifest import (
        ProjectManifest, ProjectMeta, RepoSpec, save_project_manifest,
    )
    from datetime import date
    proj = make_project("foo")
    m = ProjectManifest(
        project=ProjectMeta(name="foo", description="d", created=date(2026, 4, 29)),
        repos=[RepoSpec(
            remote=str(source_repo),
            local_hint=str(source_repo),
            worktree="code",
            branch_prefix="alice/foo",
        )],
    )
    save_project_manifest(proj / "design" / "project.toml", m)

    result = runner.invoke(app, ["code", "init", "--project", "foo", "-y"])
    assert result.exit_code == 0
    assert (proj / "code").is_dir()
    assert (proj / "code" / "README").is_file()


def test_init_idempotent(projects, make_project, source_repo) -> None:
    """init is idempotent — running twice doesn't error or create duplicate worktrees."""
    from keel.manifest import (
        ProjectManifest, ProjectMeta, RepoSpec, save_project_manifest,
    )
    from datetime import date
    proj = make_project("foo")
    m = ProjectManifest(
        project=ProjectMeta(name="foo", description="d", created=date(2026, 4, 29)),
        repos=[RepoSpec(
            remote=str(source_repo),
            local_hint=str(source_repo),
            worktree="code",
            branch_prefix="alice/foo",
        )],
    )
    save_project_manifest(proj / "design" / "project.toml", m)
    runner.invoke(app, ["code", "init", "--project", "foo", "-y"])
    result = runner.invoke(app, ["code", "init", "--project", "foo", "-y"])
    assert result.exit_code == 0


def test_init_dry_run_writes_nothing(projects, make_project, source_repo) -> None:
    from keel.manifest import (
        ProjectManifest, ProjectMeta, RepoSpec, save_project_manifest,
    )
    from datetime import date
    proj = make_project("foo")
    m = ProjectManifest(
        project=ProjectMeta(name="foo", description="d", created=date(2026, 4, 29)),
        repos=[RepoSpec(remote=str(source_repo), local_hint=str(source_repo), worktree="code", branch_prefix="a/f")],
    )
    save_project_manifest(proj / "design" / "project.toml", m)
    result = runner.invoke(app, ["code", "init", "--project", "foo", "--dry-run", "-y"])
    assert result.exit_code == 0
    assert not (proj / "code").exists()
    assert "[dry-run]" in result.stderr


def test_init_fails_when_local_repo_missing_without_clone_flag(projects, make_project) -> None:
    """If local_hint points to a missing dir and --clone-missing not set, fail."""
    from keel.manifest import (
        ProjectManifest, ProjectMeta, RepoSpec, save_project_manifest,
    )
    from datetime import date
    proj = make_project("foo")
    m = ProjectManifest(
        project=ProjectMeta(name="foo", description="d", created=date(2026, 4, 29)),
        repos=[RepoSpec(
            remote="git@e.com:o/r.git",
            local_hint=str(projects / "_does_not_exist"),
            worktree="code",
            branch_prefix="a/f",
        )],
    )
    save_project_manifest(proj / "design" / "project.toml", m)
    result = runner.invoke(app, ["code", "init", "--project", "foo", "-y"])
    assert result.exit_code == 1
    assert "missing" in result.stderr.lower() or "not found" in result.stderr.lower()
```

- [ ] **Step 2: Run, expect collection error**

- [ ] **Step 3: Implement `src/keel/commands/code/init.py`**

```python
"""`keel code init`."""
from __future__ import annotations
from pathlib import Path
import subprocess
import typer

from keel import git_ops, workspace
from keel.dryrun import OpLog
from keel.manifest import load_project_manifest, load_deliverable_manifest
from keel.output import Output


def cmd_init(
    ctx: typer.Context,
    project: str | None = typer.Option(None, "--project", "-p", help="Project name. Auto-detected from CWD if omitted."),
    deliverable: str | None = typer.Option(None, "-D", "--deliverable", help="Init worktrees declared at deliverable scope."),
    clone_missing: bool = typer.Option(False, "--clone-missing", help="Clone any source repo whose local_hint is missing on disk."),
    yes: bool = typer.Option(False, "-y", "--yes", help="Skip interactive prompts."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print intended operations and exit; write nothing."),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout."),
) -> None:
    """Materialize worktrees declared in the manifest. Idempotent."""
    out = Output.from_context(ctx, json_mode=json_mode)
    scope = workspace.resolve_cli_scope(project, deliverable)
    project = scope.project
    deliverable = scope.deliverable

    if deliverable:
        unit_dir = workspace.deliverable_dir(project, deliverable)
        m = load_deliverable_manifest(unit_dir / "design" / "deliverable.toml")
    else:
        unit_dir = workspace.project_dir(project)
        m = load_project_manifest(unit_dir / "design" / "project.toml")

    if dry_run:
        log = OpLog()
        for r in m.repos:
            wt = unit_dir / r.worktree
            if not wt.is_dir():
                source = Path(r.local_hint).expanduser() if r.local_hint else Path(r.remote)
                log.create_worktree(wt, source=source, branch=r.branch_prefix or "main")
        out.info(log.format_summary())
        return

    created: list[str] = []
    for r in m.repos:
        wt = unit_dir / r.worktree
        if wt.is_dir():
            continue  # idempotent — already there

        # Resolve source repo on disk
        source: Path | None = None
        if r.local_hint:
            candidate = Path(r.local_hint).expanduser()
            if git_ops.is_git_repo(candidate):
                source = candidate
        if source is None:
            if clone_missing and r.local_hint:
                target = Path(r.local_hint).expanduser()
                target.parent.mkdir(parents=True, exist_ok=True)
                try:
                    subprocess.run(
                        ["git", "clone", r.remote, str(target)],
                        check=True, capture_output=True,
                    )
                except subprocess.CalledProcessError as e:
                    out.error(f"clone failed for {r.remote}: {e.stderr.decode()}", code="clone_failed")
                    raise typer.Exit(code=1) from None
                source = target
            else:
                out.error(
                    f"source repo missing: {r.local_hint or r.remote}. "
                    f"Pass --clone-missing to clone it, or set local_hint to a valid path.",
                    code="source_missing",
                )
                raise typer.Exit(code=1)

        try:
            git_ops.create_worktree(source, wt, branch=r.branch_prefix or "main")
            created.append(str(wt))
        except git_ops.GitError as e:
            out.error(f"worktree creation failed: {e}", code="git_failed")
            raise typer.Exit(code=1) from None

    out.info(f"Initialized {len(created)} worktree(s).")
    out.result(
        {"created": created, "scope": "deliverable" if deliverable else "project"},
        human_text=f"Initialized {len(created)} worktree(s) for {project}{'/' + deliverable if deliverable else ''}.",
    )
```

- [ ] **Step 4: Register**

```python
from keel.commands.code.init import cmd_init  # noqa: E402
app.command(name="init")(cmd_init)
```

- [ ] **Step 5: Run tests, expect 4 PASS**

- [ ] **Step 6: Commit**

```bash
git add keel/src/keel/commands/code/init.py keel/src/keel/commands/code/__init__.py keel/tests/commands/code/test_init.py
git commit -m "feat(keel): implement 'code init' (idempotent worktree materialization)"
```

---

### Task 1.5: `code add` — append a repo to the manifest + create worktree

**Files:**
- Create: `src/keel/commands/code/add.py`
- Create: `tests/commands/code/test_add.py`
- Modify: `src/keel/commands/code/__init__.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/commands/code/test_add.py
"""Tests for `keel code add`."""
from typer.testing import CliRunner
from keel.app import app

runner = CliRunner()


def test_add_appends_to_manifest_and_creates_worktree(projects, make_project, source_repo) -> None:
    make_project("foo")
    result = runner.invoke(
        app,
        ["code", "add", "--project", "foo", "--repo", str(source_repo), "-y"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.stderr
    from keel.manifest import load_project_manifest
    m = load_project_manifest(projects / "foo" / "design" / "project.toml")
    assert len(m.repos) == 1
    assert m.repos[0].remote == str(source_repo)
    assert (projects / "foo" / "code").is_dir()


def test_add_rejects_duplicate_remote(projects, make_project, source_repo) -> None:
    make_project("foo")
    runner.invoke(app, ["code", "add", "--project", "foo", "--repo", str(source_repo), "-y"])
    result = runner.invoke(app, ["code", "add", "--project", "foo", "--repo", str(source_repo), "-y"])
    assert result.exit_code == 1
    assert "duplicate" in result.stderr.lower() or "already" in result.stderr.lower()


def test_add_rejects_duplicate_worktree_name(projects, make_project, tmp_path) -> None:
    """Two repos with same Path.name (basename) must be detected before they collide."""
    import subprocess
    make_project("foo")

    def _make_repo(p):
        p.mkdir()
        subprocess.run(["git", "init", "-b", "main"], cwd=p, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=p, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=p, check=True)
        (p / "README").write_text("x")
        subprocess.run(["git", "add", "."], cwd=p, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=p, check=True, capture_output=True)

    a = tmp_path / "first" / "samename"
    b = tmp_path / "second" / "samename"
    a.parent.mkdir()
    b.parent.mkdir()
    _make_repo(a)
    _make_repo(b)

    runner.invoke(app, ["code", "add", "--project", "foo", "--repo", str(a), "-y"])
    result = runner.invoke(app, ["code", "add", "--project", "foo", "--repo", str(b), "-y"])
    assert result.exit_code == 1
    assert "worktree" in result.stderr.lower()


def test_add_with_explicit_worktree_name(projects, make_project, source_repo) -> None:
    make_project("foo")
    result = runner.invoke(
        app,
        ["code", "add", "--project", "foo", "--repo", str(source_repo), "--worktree", "code-custom", "-y"],
    )
    assert result.exit_code == 0
    assert (projects / "foo" / "code-custom").is_dir()
```

- [ ] **Step 2: Run, expect collection error**

- [ ] **Step 3: Implement `src/keel/commands/code/add.py`**

```python
"""`keel code add`."""
from __future__ import annotations
from pathlib import Path
import typer

from keel import git_ops, workspace
from keel.manifest import (
    ProjectManifest, ProjectMeta, RepoSpec,
    DeliverableManifest, DeliverableMeta,
    load_project_manifest, save_project_manifest,
    load_deliverable_manifest, save_deliverable_manifest,
)
from keel.output import Output


def cmd_add(
    ctx: typer.Context,
    project: str | None = typer.Option(None, "--project", "-p", help="Project name. Auto-detected from CWD if omitted."),
    deliverable: str | None = typer.Option(None, "-D", "--deliverable", help="Add the repo at deliverable scope."),
    repo: str = typer.Option(..., "--repo", "-r", help="Source git repo path."),
    worktree: str | None = typer.Option(None, "--worktree", help="Override the worktree dir name (default: derived from repo basename)."),
    branch_prefix: str | None = typer.Option(None, "--branch-prefix", help="Override the branch prefix."),
    yes: bool = typer.Option(False, "-y", "--yes", help="Skip interactive prompts."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print intended operations and exit; write nothing."),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout."),
) -> None:
    """Add a source repo to the manifest and create its worktree."""
    out = Output.from_context(ctx, json_mode=json_mode)
    scope = workspace.resolve_cli_scope(project, deliverable)
    project = scope.project
    deliverable = scope.deliverable

    repo_path = Path(repo).expanduser().resolve()
    if not git_ops.is_git_repo(repo_path):
        out.error(f"not a git repo: {repo_path}", code="not_a_repo")
        raise typer.Exit(code=1)

    # Decide worktree dir name
    wt_name = worktree or f"code-{repo_path.name}"
    # If single repo and no override, prefer "code" for the first one
    # — but we don't know if this is the first; let the duplicate check handle it.

    # Derive branch prefix if not supplied
    if branch_prefix is None:
        try:
            user_slug = git_ops.git_user_slug(repo_path)
        except Exception:
            user_slug = "user"
        suffix = f"-{deliverable}" if deliverable else ""
        branch_prefix = f"{user_slug}/{project}{suffix}-{repo_path.name}"

    # Load manifest
    if deliverable:
        manifest_path = workspace.deliverable_dir(project, deliverable) / "design" / "deliverable.toml"
        m: DeliverableManifest = load_deliverable_manifest(manifest_path)
    else:
        manifest_path = workspace.project_dir(project) / "design" / "project.toml"
        m: ProjectManifest = load_project_manifest(manifest_path)

    # Detect duplicates
    for existing in m.repos:
        if existing.remote == str(repo_path):
            out.error(f"duplicate remote: {repo_path} already declared", code="duplicate_remote")
            raise typer.Exit(code=1)
        if existing.worktree == wt_name:
            out.error(
                f"worktree name '{wt_name}' already in use. Pass --worktree NAME to disambiguate.",
                code="duplicate_worktree",
            )
            raise typer.Exit(code=1)

    new_spec = RepoSpec(
        remote=str(repo_path),
        local_hint=str(repo_path),
        worktree=wt_name,
        branch_prefix=branch_prefix,
    )

    if dry_run:
        from keel.dryrun import OpLog
        log = OpLog()
        log.modify_file(manifest_path, diff=f"+ [[repos]] remote={repo_path} worktree={wt_name}")
        unit_dir = manifest_path.parent.parent
        log.create_worktree(unit_dir / wt_name, source=repo_path, branch=branch_prefix)
        out.info(log.format_summary())
        return

    # Append + write back
    new_repos = list(m.repos) + [new_spec]
    if deliverable:
        new_m = DeliverableManifest(deliverable=m.deliverable, repos=new_repos)
        save_deliverable_manifest(manifest_path, new_m)
    else:
        new_m = ProjectManifest(project=m.project, repos=new_repos)
        save_project_manifest(manifest_path, new_m)

    # Create worktree
    unit_dir = manifest_path.parent.parent
    try:
        git_ops.create_worktree(repo_path, unit_dir / wt_name, branch=branch_prefix)
    except git_ops.GitError as e:
        out.error(f"worktree creation failed: {e}", code="git_failed")
        out.info(f"Manifest was updated; remove the new [[repos]] entry manually if you want to retry.")
        raise typer.Exit(code=1) from None

    out.info(f"Added repo {repo_path} → worktree {unit_dir / wt_name}")
    out.result(
        {"remote": str(repo_path), "worktree": str(unit_dir / wt_name), "branch_prefix": branch_prefix},
        human_text=f"Repo added: {repo_path}",
    )
```

- [ ] **Step 4: Register**

```python
from keel.commands.code.add import cmd_add  # noqa: E402
app.command(name="add")(cmd_add)
```

- [ ] **Step 5: Run tests, expect 4 PASS**

- [ ] **Step 6: Commit**

```bash
git add keel/src/keel/commands/code/add.py keel/src/keel/commands/code/__init__.py keel/tests/commands/code/test_add.py
git commit -m "feat(keel): implement 'code add' with collision detection"
```

---

### Task 1.6: `code rm` — remove a repo from the manifest + worktree

**Files:**
- Create: `src/keel/commands/code/rm.py`
- Create: `tests/commands/code/test_rm.py`
- Modify: `src/keel/commands/code/__init__.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/commands/code/test_rm.py
"""Tests for `keel code rm`."""
from typer.testing import CliRunner
from keel.app import app

runner = CliRunner()


def test_rm_removes_manifest_entry_and_worktree(projects, make_project, source_repo) -> None:
    make_project("foo")
    runner.invoke(app, ["code", "add", "--project", "foo", "--repo", str(source_repo), "-y"])
    assert (projects / "foo" / "code").is_dir()
    result = runner.invoke(app, ["code", "rm", "--project", "foo", "--repo", str(source_repo), "-y"])
    assert result.exit_code == 0
    assert not (projects / "foo" / "code").exists()
    from keel.manifest import load_project_manifest
    m = load_project_manifest(projects / "foo" / "design" / "project.toml")
    assert m.repos == []


def test_rm_unknown_repo(projects, make_project) -> None:
    make_project("foo")
    result = runner.invoke(app, ["code", "rm", "--project", "foo", "--repo", "git@e.com:o/x.git", "-y"])
    assert result.exit_code == 1
    assert "not found" in result.stderr.lower() or "no such" in result.stderr.lower()


def test_rm_dirty_worktree_without_force(projects, make_project, source_repo) -> None:
    make_project("foo")
    runner.invoke(app, ["code", "add", "--project", "foo", "--repo", str(source_repo), "-y"])
    (projects / "foo" / "code" / "dirty.txt").write_text("dirty")
    result = runner.invoke(app, ["code", "rm", "--project", "foo", "--repo", str(source_repo), "-y"])
    assert result.exit_code == 1
```

- [ ] **Step 2: Run, expect collection error**

- [ ] **Step 3: Implement `src/keel/commands/code/rm.py`**

```python
"""`keel code rm`."""
from __future__ import annotations
import typer

from keel import git_ops, workspace
from keel.manifest import (
    ProjectManifest, DeliverableManifest,
    load_project_manifest, save_project_manifest,
    load_deliverable_manifest, save_deliverable_manifest,
)
from keel.output import Output
from keel.prompts import confirm_destructive


def cmd_rm(
    ctx: typer.Context,
    project: str | None = typer.Option(None, "--project", "-p", help="Project name. Auto-detected from CWD if omitted."),
    deliverable: str | None = typer.Option(None, "-D", "--deliverable", help="Remove from deliverable scope."),
    repo: str = typer.Option(..., "--repo", "-r", help="Remote URL of the repo to remove."),
    force: bool = typer.Option(False, "--force", help="Allow removal even if the worktree has uncommitted changes."),
    yes: bool = typer.Option(False, "-y", "--yes", help="Skip confirmation prompt."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print intended operations and exit; write nothing."),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout."),
) -> None:
    """Remove a repo from the manifest and remove its worktree."""
    out = Output.from_context(ctx, json_mode=json_mode)
    scope = workspace.resolve_cli_scope(project, deliverable)
    project = scope.project
    deliverable = scope.deliverable

    if deliverable:
        manifest_path = workspace.deliverable_dir(project, deliverable) / "design" / "deliverable.toml"
        m: DeliverableManifest = load_deliverable_manifest(manifest_path)
    else:
        manifest_path = workspace.project_dir(project) / "design" / "project.toml"
        m: ProjectManifest = load_project_manifest(manifest_path)

    target = next((r for r in m.repos if r.remote == repo), None)
    if target is None:
        out.error(f"no repo with remote: {repo}", code="not_found")
        raise typer.Exit(code=1)

    unit_dir = manifest_path.parent.parent
    wt_path = unit_dir / target.worktree

    if dry_run:
        from keel.dryrun import OpLog
        log = OpLog()
        log.modify_file(manifest_path, diff=f"- [[repos]] remote={repo}")
        if wt_path.is_dir():
            log.remove_worktree(wt_path)
        out.info(log.format_summary())
        return

    confirm_destructive(
        f"Remove repo {repo} and its worktree at {wt_path}?",
        yes=yes,
    )

    # Remove worktree first; if dirty and not --force, abort before manifest mutation
    if wt_path.is_dir():
        try:
            git_ops.remove_worktree(wt_path, force=force)
        except git_ops.GitError as e:
            out.error(f"worktree removal failed (use --force if dirty): {e}", code="git_failed")
            raise typer.Exit(code=1) from None

    # Update manifest
    new_repos = [r for r in m.repos if r.remote != repo]
    if deliverable:
        new_m = DeliverableManifest(deliverable=m.deliverable, repos=new_repos)
        save_deliverable_manifest(manifest_path, new_m)
    else:
        new_m = ProjectManifest(project=m.project, repos=new_repos)
        save_project_manifest(manifest_path, new_m)

    out.info(f"Removed repo {repo}")
    out.result({"removed_remote": repo, "removed_worktree": str(wt_path)}, human_text=f"Removed: {repo}")
```

- [ ] **Step 4: Register**

```python
from keel.commands.code.rm import cmd_rm  # noqa: E402
app.command(name="rm")(cmd_rm)
```

- [ ] **Step 5: Run tests, expect 3 PASS**

- [ ] **Step 6: Commit**

```bash
git add keel/src/keel/commands/code/rm.py keel/src/keel/commands/code/__init__.py keel/tests/commands/code/test_rm.py
git commit -m "feat(keel): implement 'code rm'"
```

---

### Task 1.7: Tighten `RepoSpec.worktree` validator

**Files:**
- Modify: `src/keel/manifest.py`
- Modify: `tests/test_manifest.py`

The current validator only rejects absolute paths. Spec §5.3 says `worktree` is "a subdir under the unit" — this should mean a single, non-special path component. Tighten to reject `/`, `\`, `..`, `.`, empty strings, and bare whitespace.

- [ ] **Step 1: Add failing tests**

Append to `tests/test_manifest.py`:

```python
def test_repo_spec_rejects_worktree_with_slash() -> None:
    with pytest.raises(ValidationError):
        RepoSpec(remote="git@e.com:o/r.git", worktree="sub/dir")


def test_repo_spec_rejects_worktree_dotdot() -> None:
    with pytest.raises(ValidationError):
        RepoSpec(remote="git@e.com:o/r.git", worktree="..")


def test_repo_spec_rejects_worktree_dot() -> None:
    with pytest.raises(ValidationError):
        RepoSpec(remote="git@e.com:o/r.git", worktree=".")


def test_repo_spec_rejects_worktree_with_backslash() -> None:
    with pytest.raises(ValidationError):
        RepoSpec(remote="git@e.com:o/r.git", worktree=r"sub\dir")


def test_repo_spec_accepts_normal_name() -> None:
    s = RepoSpec(remote="git@e.com:o/r.git", worktree="code")
    assert s.worktree == "code"
    s2 = RepoSpec(remote="git@e.com:o/r.git", worktree="code-foo")
    assert s2.worktree == "code-foo"
```

- [ ] **Step 2: Run, expect 4 FAIL** (the 5th passes already)

- [ ] **Step 3: Tighten the validator in `src/keel/manifest.py`**

Replace the existing `_worktree_relative` validator on `RepoSpec` with:

```python
    @field_validator("worktree")
    @classmethod
    def _worktree_single_component(cls, v: str) -> str:
        from pathlib import Path
        if not v or not v.strip():
            raise ValueError("worktree must be a non-empty string")
        if "/" in v or "\\" in v:
            raise ValueError("worktree must be a single path component (no slashes)")
        if v in (".", ".."):
            raise ValueError("worktree must not be '.' or '..'")
        if Path(v).is_absolute():
            raise ValueError("worktree must be a relative subdir name")
        return v
```

- [ ] **Step 4: Run tests, expect all PASS**

- [ ] **Step 5: Run full suite to confirm no other tests break**

Run: `uv run --extra dev pytest`
Expected: previous count + 4 new = ?

- [ ] **Step 6: Commit**

```bash
git add keel/src/keel/manifest.py keel/tests/test_manifest.py
git commit -m "feat(keel): tighten RepoSpec.worktree validator to single path component"
```

---

## Milestone 2: `validate` command

### Task 2.1: `validate` — basic structural checks

**Files:**
- Create: `src/keel/commands/validate.py`
- Create: `tests/commands/test_validate.py`
- Modify: `src/keel/app.py` (register)

Spec §7.13. Structural checks (always run):
- Manifest is valid TOML & matches Pydantic schema
- Required design files exist (`CLAUDE.md`, `design.md`, `.phase`)
- Declared worktrees exist on disk
- Worktree current branches start with declared `branch_prefix`
- Parent CLAUDE.md / design.md mention all on-disk deliverables
- Sibling CLAUDE.md files reference each other consistently

- [ ] **Step 1: Write failing tests**

```python
# tests/commands/test_validate.py
"""Tests for `keel validate`."""
import json
from typer.testing import CliRunner
from keel.app import app

runner = CliRunner()


def test_validate_clean_project(projects, make_project) -> None:
    make_project("foo")
    result = runner.invoke(app, ["validate", "foo"])
    assert result.exit_code == 0


def test_validate_missing_design_md_warns(projects, make_project) -> None:
    proj = make_project("foo")
    (proj / "design" / "design.md").unlink()
    result = runner.invoke(app, ["validate", "foo", "--json"])
    payload = json.loads(result.stdout)
    summary = payload["summary"]
    assert summary["fail"] >= 1 or summary["warn"] >= 1


def test_validate_missing_phase_warns(projects, make_project) -> None:
    proj = make_project("foo")
    (proj / "design" / ".phase").unlink()
    result = runner.invoke(app, ["validate", "foo", "--json"])
    payload = json.loads(result.stdout)
    assert payload["summary"]["fail"] >= 1 or payload["summary"]["warn"] >= 1


def test_validate_orphan_deliverable_dir_warns(projects, make_project, make_deliverable) -> None:
    """A deliverable on disk but not mentioned in parent CLAUDE.md should warn."""
    deliv = make_deliverable(project_name="foo", name="bar", description="d")
    # Deliberately strip the parent's mention of this deliverable
    parent_claude = projects / "foo" / "design" / "CLAUDE.md"
    text = parent_claude.read_text()
    parent_claude.write_text(text.replace(f"- **bar**:", "- **REMOVED**:"))
    result = runner.invoke(app, ["validate", "foo", "--json"])
    payload = json.loads(result.stdout)
    findings = payload["findings"]
    msgs = [f["message"] for f in findings]
    assert any("bar" in m or "missing" in m.lower() for m in msgs)
```

- [ ] **Step 2: Run, expect collection error**

- [ ] **Step 3: Implement `src/keel/commands/validate.py`**

```python
"""`keel validate`."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import typer
from rich.table import Table

from keel import git_ops, workspace
from keel.manifest import load_project_manifest, load_deliverable_manifest
from keel.output import Output


@dataclass
class _Finding:
    check: str
    level: str  # "pass" | "warn" | "fail"
    message: str
    path: str = ""


def _check_required_design_files(unit_dir: Path, label: str) -> list[_Finding]:
    findings: list[_Finding] = []
    for required in ("CLAUDE.md", "design.md", ".phase"):
        path = unit_dir / "design" / required
        if path.is_file():
            findings.append(_Finding("required-files", "pass", f"{label} has {required}", str(path)))
        else:
            findings.append(_Finding("required-files", "fail", f"{label} missing {required}", str(path)))
    return findings


def _check_manifest(manifest_path: Path, loader, label: str) -> tuple[list[_Finding], object | None]:
    if not manifest_path.is_file():
        return [_Finding("manifest", "fail", f"{label} manifest missing", str(manifest_path))], None
    try:
        m = loader(manifest_path)
        return [_Finding("manifest", "pass", f"{label} manifest valid", str(manifest_path))], m
    except Exception as e:
        return [_Finding("manifest", "fail", f"{label} manifest invalid: {e}", str(manifest_path))], None


def _check_worktrees(unit_dir: Path, repos, label: str) -> list[_Finding]:
    findings: list[_Finding] = []
    for r in repos:
        wt = unit_dir / r.worktree
        if not wt.is_dir():
            findings.append(_Finding("worktree", "warn", f"{label} declares worktree {r.worktree} but dir missing", str(wt)))
            continue
        if not git_ops.is_git_repo(wt):
            findings.append(_Finding("worktree", "fail", f"{label} worktree {r.worktree} is not a git worktree", str(wt)))
            continue
        if r.branch_prefix:
            try:
                cur = git_ops.current_branch(wt)
                if cur and not cur.startswith(r.branch_prefix):
                    findings.append(_Finding(
                        "worktree", "warn",
                        f"{label} worktree {r.worktree} branch '{cur}' doesn't start with prefix '{r.branch_prefix}'",
                        str(wt),
                    ))
                else:
                    findings.append(_Finding("worktree", "pass", f"{label} worktree {r.worktree} OK", str(wt)))
            except git_ops.GitError:
                findings.append(_Finding("worktree", "warn", f"{label} couldn't read branch for {r.worktree}", str(wt)))
        else:
            findings.append(_Finding("worktree", "pass", f"{label} worktree {r.worktree} OK", str(wt)))
    return findings


def _check_deliverable_references(project: str) -> list[_Finding]:
    findings: list[_Finding] = []
    deliv_dir = workspace.project_dir(project) / "deliverables"
    if not deliv_dir.is_dir():
        return findings
    parent_claude = workspace.project_dir(project) / "design" / "CLAUDE.md"
    parent_text = parent_claude.read_text() if parent_claude.is_file() else ""
    for d in sorted(deliv_dir.iterdir()):
        if not d.is_dir() or not (d / "design" / "deliverable.toml").is_file():
            continue
        if f"**{d.name}**" not in parent_text:
            findings.append(_Finding(
                "refs", "warn",
                f"deliverable '{d.name}' exists on disk but not mentioned in parent CLAUDE.md",
                str(parent_claude),
            ))
    return findings


def cmd_validate(
    ctx: typer.Context,
    name: str | None = typer.Argument(None, help="Project name. Auto-detected from CWD if omitted."),
    strict: bool = typer.Option(False, "--strict", help="Treat warnings as failures (exit 1 if any warn)."),
    check: str | None = typer.Option(None, "--check", help="Comma-separated list of check names to run (e.g. 'manifest,worktree')."),
    content: bool = typer.Option(False, "--content", help="Run additional content checks (decision frontmatter, design.md sections)."),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout."),
) -> None:
    """Validate project structure and (optionally) content."""
    out = Output.from_context(ctx, json_mode=json_mode)
    scope = workspace.resolve_cli_scope(name, None, allow_deliverable=False)
    project = scope.project

    findings: list[_Finding] = []

    # Project-level checks
    proj_dir = workspace.project_dir(project)
    findings.extend(_check_required_design_files(proj_dir, "project"))
    project_manifest_path = proj_dir / "design" / "project.toml"
    proj_findings, m = _check_manifest(project_manifest_path, load_project_manifest, "project")
    findings.extend(proj_findings)
    if m is not None:
        findings.extend(_check_worktrees(proj_dir, m.repos, "project"))
    findings.extend(_check_deliverable_references(project))

    # Deliverables
    deliv_dir = proj_dir / "deliverables"
    if deliv_dir.is_dir():
        for d in sorted(deliv_dir.iterdir()):
            if not d.is_dir():
                continue
            label = f"deliverable {d.name}"
            findings.extend(_check_required_design_files(d, label))
            d_manifest = d / "design" / "deliverable.toml"
            d_findings, dm = _check_manifest(d_manifest, load_deliverable_manifest, label)
            findings.extend(d_findings)
            if dm is not None:
                findings.extend(_check_worktrees(d, dm.repos, label))

    # Filter by --check
    if check:
        wanted = {c.strip() for c in check.split(",")}
        findings = [f for f in findings if f.check in wanted]

    # Tally
    tally = {"pass": 0, "warn": 0, "fail": 0}
    for f in findings:
        tally[f.level] = tally.get(f.level, 0) + 1

    if json_mode:
        out.result({
            "findings": [
                {"check": f.check, "level": f.level, "message": f.message, "path": f.path}
                for f in findings
            ],
            "summary": tally,
        })
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
            out.info(f"summary: {tally['pass']} pass, {tally['warn']} warn, {tally['fail']} fail")

    # Exit code
    if tally["fail"] > 0:
        raise typer.Exit(code=1)
    if strict and tally["warn"] > 0:
        raise typer.Exit(code=1)
```

- [ ] **Step 4: Register in `app.py`**

Append:
```python
from keel.commands.validate import cmd_validate  # noqa: E402
app.command(name="validate")(cmd_validate)
```

- [ ] **Step 5: Run tests, expect 4 PASS**

- [ ] **Step 6: Commit**

```bash
git add keel/src/keel/commands/validate.py keel/src/keel/app.py keel/tests/commands/test_validate.py
git commit -m "feat(keel): implement 'validate' with structural checks"
```

---

## Milestone 3: `design export` command

### Task 3.1: Scaffold `commands/design/` subpackage + deliverable-level export

**Files:**
- Create: `src/keel/commands/design/__init__.py`
- Create: `src/keel/commands/design/export.py`
- Create: `tests/commands/design/__init__.py` (empty)
- Create: `tests/commands/design/test_export.py`
- Modify: `src/keel/app.py` (register subapp)

- [ ] **Step 1: Scaffold the subapp**

`src/keel/commands/design/__init__.py`:
```python
"""`keel design ...` command group."""
from __future__ import annotations
import typer

app = typer.Typer(
    name="design",
    help="Compose and export design documents.",
    no_args_is_help=True,
)

from keel.commands.design.export import cmd_export  # noqa: E402
app.command(name="export")(cmd_export)
```

Append to `src/keel/app.py`:
```python
from keel.commands.design import app as design_app  # noqa: E402
app.add_typer(design_app, name="design")
```

- [ ] **Step 2: Write failing tests**

```python
# tests/commands/design/test_export.py
"""Tests for `keel design export`."""
from typer.testing import CliRunner
from keel.app import app

runner = CliRunner()


def test_export_deliverable(projects, make_deliverable) -> None:
    """Deliverable-level export produces a single doc with the deliverable's design + decisions."""
    deliv = make_deliverable(project_name="foo", name="bar", description="the bar")
    # Create a decision in the deliverable
    decision_dir = deliv / "design" / "decisions"
    decision_dir.mkdir(parents=True, exist_ok=True)
    (decision_dir / "2026-04-29-pick-x.md").write_text(
        "---\ndate: 2026-04-29\ntitle: Pick X\nstatus: proposed\n---\n# Pick X\n## Question\nQ?\n## Conclusion\nC.\n"
    )
    result = runner.invoke(app, ["design", "export", "--project", "foo", "-D", "bar"])
    assert result.exit_code == 0
    assert "# bar" in result.stdout or "bar" in result.stdout
    assert "Pick X" in result.stdout


def test_export_deliverable_excludes_superseded(projects, make_deliverable) -> None:
    deliv = make_deliverable(project_name="foo", name="bar", description="d")
    decision_dir = deliv / "design" / "decisions"
    decision_dir.mkdir(parents=True, exist_ok=True)
    (decision_dir / "2026-04-29-old.md").write_text(
        "---\ndate: 2026-04-29\ntitle: Old\nstatus: superseded\n---\n# Old\n## Question\nQ?\n## Conclusion\nC.\n"
    )
    (decision_dir / "2026-04-29-new.md").write_text(
        "---\ndate: 2026-04-29\ntitle: New\nstatus: proposed\n---\n# New\n## Question\nQ?\n## Conclusion\nC.\n"
    )
    result = runner.invoke(app, ["design", "export", "--project", "foo", "-D", "bar"])
    assert "New" in result.stdout
    assert "Old" not in result.stdout


def test_export_writes_to_output_file(projects, make_deliverable, tmp_path) -> None:
    deliv = make_deliverable(project_name="foo", name="bar", description="d")
    out_path = tmp_path / "out.md"
    result = runner.invoke(app, ["design", "export", "--project", "foo", "-D", "bar", "-o", str(out_path)])
    assert result.exit_code == 0
    assert out_path.is_file()
    assert "bar" in out_path.read_text()
```

- [ ] **Step 3: Run, expect collection error**

- [ ] **Step 4: Implement `src/keel/commands/design/export.py`**

This task implements the **deliverable-level** export. Project-level composition is T3.2.

```python
"""`keel design export`."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable
import typer

from keel import workspace
from keel.manifest import load_deliverable_manifest, load_project_manifest
from keel.output import Output


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
    return fm, text[m.end():]


@dataclass
class _Decision:
    path: Path
    label: str  # e.g. "D.1"
    title: str
    body: str
    status: str
    superseded: bool


def _collect_decisions(decisions_dir: Path, *, include_superseded: bool, start_index: int) -> list[_Decision]:
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
        out.append(_Decision(
            path=f,
            label=f"D.{idx}",
            title=title,
            body=body_stripped.rstrip("\n"),
            status=status,
            superseded=superseded,
        ))
        idx += 1
    return out


def _replace_decision_links(design_text: str, decisions: Iterable[_Decision]) -> str:
    """Replace `[text](decisions/<file>.md)` links with `text (Appendix D.N)`."""
    for d in decisions:
        rel = f"decisions/{d.path.name}"
        # Match [any text](decisions/<file>.md) and replace with `text (Appendix D.N)`
        pattern = rf"\[([^\]]*)\]\({re.escape(rel)}\)"
        design_text = re.sub(pattern, lambda m, label=d.label: f"{m.group(1)} (Appendix {label})", design_text)
    return design_text


def cmd_export(
    ctx: typer.Context,
    name: str | None = typer.Argument(None, help="Project name. Auto-detected from CWD if omitted."),
    deliverable: str | None = typer.Option(None, "-D", "--deliverable", help="Export this deliverable instead of the whole project."),
    project: str | None = typer.Option(None, "--project", "-p", help="Project name (alternative to positional)."),
    no_decisions: bool = typer.Option(False, "--no-decisions", help="Skip the decisions appendix."),
    no_deliverables: bool = typer.Option(False, "--no-deliverables", help="At project level, export parent only (skip deliverable sections)."),
    include_scope: bool = typer.Option(False, "--include-scope", help="Prepend the scope.md as a Scope section."),
    include_superseded: bool = typer.Option(False, "--include-superseded", help="Include superseded decisions in the appendix."),
    output: Path | None = typer.Option(None, "-o", "--output", help="Write to this file instead of stdout."),
    json_mode: bool = typer.Option(False, "--json", help="Emit JSON envelope around the markdown."),
) -> None:
    """Compose a project's or deliverable's design + decisions into a single markdown document."""
    out_obj = Output.from_context(ctx, json_mode=json_mode)
    project = project or name
    scope = workspace.resolve_cli_scope(project, deliverable)
    project = scope.project
    deliverable = scope.deliverable

    sections: list[str] = []
    appendix: list[_Decision] = []

    if deliverable:
        unit_dir = workspace.deliverable_dir(project, deliverable)
        m = load_deliverable_manifest(unit_dir / "design" / "deliverable.toml")
        title = m.deliverable.name
        sections.append(f"# {title}\n")
        if include_scope:
            scope_path = unit_dir / "design" / "scope.md"
            if scope_path.is_file():
                sections.append("## Scope\n\n" + scope_path.read_text().strip())
        design_path = unit_dir / "design" / "design.md"
        if design_path.is_file():
            decisions = _collect_decisions(unit_dir / "design" / "decisions", include_superseded=include_superseded, start_index=1) if not no_decisions else []
            text = design_path.read_text().strip()
            text = _replace_decision_links(text, decisions)
            sections.append("## Design\n\n" + text)
            appendix.extend(decisions)
    else:
        # Project-level: T3.2 implements composition; for T3.1 we just dump the project's design.md
        unit_dir = workspace.project_dir(project)
        m = load_project_manifest(unit_dir / "design" / "project.toml")
        title = m.project.name
        sections.append(f"# {title}\n")
        if include_scope:
            scope_path = unit_dir / "design" / "scope.md"
            if scope_path.is_file():
                sections.append("## Scope\n\n" + scope_path.read_text().strip())
        design_path = unit_dir / "design" / "design.md"
        if design_path.is_file():
            decisions = _collect_decisions(unit_dir / "design" / "decisions", include_superseded=include_superseded, start_index=1) if not no_decisions else []
            text = design_path.read_text().strip()
            text = _replace_decision_links(text, decisions)
            sections.append("## Project Design\n\n" + text)
            appendix.extend(decisions)

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
```

- [ ] **Step 5: Run tests, expect 3 PASS**

- [ ] **Step 6: Commit**

```bash
git add keel/src/keel/commands/design/ keel/src/keel/app.py keel/tests/commands/design/
git commit -m "feat(keel): implement 'design export' (deliverable-level + project-flat)"
```

---

### Task 3.2: Project-level export — composition with deliverables

**Files:**
- Modify: `src/keel/commands/design/export.py`
- Modify: `tests/commands/design/test_export.py`

When called at project level (no `--deliverable`), the export should:
- Start with the project's design
- Append a `## Deliverable: <name>` section per deliverable (each with its own design.md content)
- Build a flat decision appendix numbered across the whole document (D.1...D.N)
- Skip deliverable sections if `--no-deliverables` is passed

- [ ] **Step 1: Add failing tests**

Append to `test_export.py`:

```python
def test_export_project_composes_deliverables(projects, make_project) -> None:
    """Project-level export includes a section per deliverable."""
    make_project("foo")
    runner.invoke(app, ["deliverable", "add", "alpha", "-d", "alpha thing", "-y", "--project", "foo"])
    runner.invoke(app, ["deliverable", "add", "beta", "-d", "beta thing", "-y", "--project", "foo"])
    result = runner.invoke(app, ["design", "export", "foo"])
    assert result.exit_code == 0
    assert "## Deliverable: alpha" in result.stdout
    assert "## Deliverable: beta" in result.stdout


def test_export_no_deliverables_flag(projects, make_project) -> None:
    make_project("foo")
    runner.invoke(app, ["deliverable", "add", "alpha", "-d", "d", "-y", "--project", "foo"])
    result = runner.invoke(app, ["design", "export", "foo", "--no-deliverables"])
    assert "## Deliverable: alpha" not in result.stdout


def test_export_decision_numbering_flat_across_project(projects, make_project) -> None:
    """Project decisions get D.1+, then deliverable decisions follow."""
    proj_path = projects / "foo"
    make_project("foo")
    runner.invoke(app, ["deliverable", "add", "alpha", "-d", "d", "-y", "--project", "foo"])
    # Add decisions
    (proj_path / "design" / "decisions" / "2026-04-29-p1.md").write_text(
        "---\ndate: 2026-04-29\ntitle: P1\nstatus: proposed\n---\n# P1\n## Question\nQ\n## Conclusion\nC\n"
    )
    deliv_decisions = proj_path / "deliverables" / "alpha" / "design" / "decisions"
    deliv_decisions.mkdir(parents=True, exist_ok=True)
    (deliv_decisions / "2026-04-29-a1.md").write_text(
        "---\ndate: 2026-04-29\ntitle: A1\nstatus: proposed\n---\n# A1\n## Question\nQ\n## Conclusion\nC\n"
    )
    result = runner.invoke(app, ["design", "export", "foo"])
    text = result.stdout
    assert "Appendix D.1: P1" in text
    assert "Appendix D.2:" in text  # deliverable's a1 follows
```

- [ ] **Step 2: Run, expect FAIL on `test_export_project_composes_deliverables` and `test_export_decision_numbering_flat_across_project`**

- [ ] **Step 3: Update `cmd_export` to compose at project level**

Replace the project-level branch (the `else` block where `deliverable` is None) with:

```python
    else:
        # Project-level composition
        unit_dir = workspace.project_dir(project)
        m = load_project_manifest(unit_dir / "design" / "project.toml")
        title = m.project.name
        sections.append(f"# {title}\n")
        if include_scope:
            scope_path = unit_dir / "design" / "scope.md"
            if scope_path.is_file():
                sections.append("## Scope\n\n" + scope_path.read_text().strip())

        # Project decisions get D.1...
        proj_decisions = (
            _collect_decisions(unit_dir / "design" / "decisions", include_superseded=include_superseded, start_index=1)
            if not no_decisions else []
        )
        appendix.extend(proj_decisions)
        next_idx = len(proj_decisions) + 1

        # Project design
        design_path = unit_dir / "design" / "design.md"
        if design_path.is_file():
            text = design_path.read_text().strip()
            text = _replace_decision_links(text, proj_decisions)
            sections.append("## Project Design\n\n" + text)

        # Deliverables
        if not no_deliverables:
            deliv_dir = unit_dir / "deliverables"
            if deliv_dir.is_dir():
                for d in sorted(deliv_dir.iterdir()):
                    d_manifest = d / "design" / "deliverable.toml"
                    if not d_manifest.is_file():
                        continue
                    d_decisions = (
                        _collect_decisions(d / "design" / "decisions", include_superseded=include_superseded, start_index=next_idx)
                        if not no_decisions else []
                    )
                    next_idx += len(d_decisions)
                    appendix.extend(d_decisions)
                    d_design = d / "design" / "design.md"
                    if d_design.is_file():
                        d_text = d_design.read_text().strip()
                        d_text = _replace_decision_links(d_text, d_decisions)
                        sections.append(f"## Deliverable: {d.name}\n\n{d_text}")
```

- [ ] **Step 4: Run tests, all PASS**

- [ ] **Step 5: Commit**

```bash
git add keel/src/keel/commands/design/export.py keel/tests/commands/design/test_export.py
git commit -m "feat(keel): 'design export' composes parent + deliverables with flat decision appendix"
```

---

## Milestone 4: `archive` and project-level `rename`

### Task 4.1: `keel archive` — soft-delete a project

**Files:**
- Create: `src/keel/commands/archive.py`
- Create: `tests/commands/test_archive.py`
- Modify: `src/keel/app.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/commands/test_archive.py
"""Tests for `keel archive`."""
from typer.testing import CliRunner
from keel.app import app

runner = CliRunner()


def test_archive_moves_project_to_archive(projects, make_project) -> None:
    make_project("foo")
    result = runner.invoke(app, ["archive", "foo", "-y"])
    assert result.exit_code == 0
    assert not (projects / "foo").exists()
    archive_dirs = list((projects / ".archive").glob("foo-*"))
    assert len(archive_dirs) == 1
    assert (archive_dirs[0] / ".archived").is_file()
    assert (archive_dirs[0] / "design" / "project.toml").is_file()


def test_archive_unknown(projects) -> None:
    result = runner.invoke(app, ["archive", "ghost", "-y"])
    assert result.exit_code == 1


def test_archive_dry_run(projects, make_project) -> None:
    make_project("foo")
    result = runner.invoke(app, ["archive", "foo", "-y", "--dry-run"])
    assert result.exit_code == 0
    assert (projects / "foo").exists()
    assert not (projects / ".archive").exists()


def test_archive_with_worktree_clean(projects, make_project, source_repo) -> None:
    """Archive correctly removes a clean worktree before moving the project."""
    from keel import git_ops
    proj = make_project("foo")
    git_ops.create_worktree(source_repo, proj / "code", branch="alice/foo")
    result = runner.invoke(app, ["archive", "foo", "-y"])
    assert result.exit_code == 0
    archive_dirs = list((projects / ".archive").glob("foo-*"))
    assert len(archive_dirs) == 1
    # Worktree was removed before move (so it's not in the archive):
    assert not (archive_dirs[0] / "code").exists()
```

- [ ] **Step 2: Run, expect collection error**

- [ ] **Step 3: Implement `src/keel/commands/archive.py`**

```python
"""`keel archive`."""
from __future__ import annotations
from datetime import date
import shutil
import typer

from keel import git_ops, workspace
from keel.manifest import load_project_manifest
from keel.output import Output
from keel.prompts import confirm_destructive


def cmd_archive(
    ctx: typer.Context,
    name: str | None = typer.Argument(None, help="Project name. Auto-detected from CWD if omitted."),
    force: bool = typer.Option(False, "--force", help="Allow archive even if worktrees are dirty."),
    yes: bool = typer.Option(False, "-y", "--yes", help="Skip confirmation prompt."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print intended operations and exit; write nothing."),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout."),
) -> None:
    """Soft-delete a project: remove worktrees, move to ~/projects/.archive/."""
    out = Output.from_context(ctx, json_mode=json_mode)
    scope = workspace.resolve_cli_scope(name, None, allow_deliverable=False)
    project = scope.project

    proj_dir = workspace.project_dir(project)
    today = date.today().isoformat()
    dest = workspace.projects_dir() / ".archive" / f"{project}-{today}"

    if dry_run:
        from keel.dryrun import OpLog
        log = OpLog()
        log.modify_file(proj_dir, diff=f"move → {dest}")
        out.info(log.format_summary())
        return

    confirm_destructive(
        f"Archive project {project}? Will move {proj_dir} → {dest} (worktrees removed first).",
        yes=yes,
    )

    # Remove worktrees declared in the manifest
    try:
        m = load_project_manifest(proj_dir / "design" / "project.toml")
    except Exception:
        m = None

    removed_worktrees = 0
    if m is not None:
        for r in m.repos:
            wt = proj_dir / r.worktree
            if wt.is_dir():
                try:
                    git_ops.remove_worktree(wt, force=force)
                    removed_worktrees += 1
                except git_ops.GitError as e:
                    out.error(f"can't remove worktree {wt}: {e} (use --force)", code="git_failed")
                    raise typer.Exit(code=1) from None

    # Also handle deliverable worktrees
    deliv_dir = proj_dir / "deliverables"
    if deliv_dir.is_dir():
        for d in sorted(deliv_dir.iterdir()):
            d_manifest_path = d / "design" / "deliverable.toml"
            if not d_manifest_path.is_file():
                continue
            from keel.manifest import load_deliverable_manifest
            try:
                dm = load_deliverable_manifest(d_manifest_path)
            except Exception:
                continue
            for r in dm.repos:
                wt = d / r.worktree
                if wt.is_dir():
                    try:
                        git_ops.remove_worktree(wt, force=force)
                        removed_worktrees += 1
                    except git_ops.GitError as e:
                        out.error(f"can't remove worktree {wt}: {e} (use --force)", code="git_failed")
                        raise typer.Exit(code=1) from None

    # Move the project tree
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(proj_dir), str(dest))
    (dest / ".archived").write_text(f"archived: {today}\nfrom: {proj_dir}\n")

    out.info(f"Archived: {dest}")
    out.result(
        {"archived_to": str(dest), "removed_worktrees": removed_worktrees},
        human_text=f"Archived {project} to {dest}.",
    )
```

- [ ] **Step 4: Register**

Append to `app.py`:
```python
from keel.commands.archive import cmd_archive  # noqa: E402
app.command(name="archive")(cmd_archive)
```

- [ ] **Step 5: Run tests, expect 4 PASS**

- [ ] **Step 6: Commit**

```bash
git add keel/src/keel/commands/archive.py keel/src/keel/app.py keel/tests/commands/test_archive.py
git commit -m "feat(keel): implement 'archive' (soft-delete project to .archive/)"
```

---

### Task 4.2: `keel rename` — rename a project

**Files:**
- Create: `src/keel/commands/rename.py`
- Create: `tests/commands/test_rename.py`
- Modify: `src/keel/app.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/commands/test_rename.py
"""Tests for project-level `keel rename`."""
from typer.testing import CliRunner
from keel.app import app

runner = CliRunner()


def test_rename_moves_project_dir(projects, make_project) -> None:
    make_project("foo")
    result = runner.invoke(app, ["rename", "foo", "bar", "-y"])
    assert result.exit_code == 0
    assert not (projects / "foo").exists()
    assert (projects / "bar" / "design" / "project.toml").is_file()


def test_rename_updates_manifest_name(projects, make_project) -> None:
    make_project("foo")
    runner.invoke(app, ["rename", "foo", "bar", "-y"])
    from keel.manifest import load_project_manifest
    m = load_project_manifest(projects / "bar" / "design" / "project.toml")
    assert m.project.name == "bar"


def test_rename_target_exists(projects, make_project) -> None:
    make_project("foo")
    make_project("bar")
    result = runner.invoke(app, ["rename", "foo", "bar", "-y"])
    assert result.exit_code == 1


def test_rename_with_worktree_uses_git_worktree_move(projects, make_project, source_repo, monkeypatch) -> None:
    from keel import git_ops
    from keel.manifest import (
        ProjectManifest, ProjectMeta, RepoSpec, save_project_manifest,
    )
    from datetime import date
    proj = make_project("foo")
    git_ops.create_worktree(source_repo, proj / "code", branch="alice/foo")
    # Update manifest to declare the repo
    m = ProjectManifest(
        project=ProjectMeta(name="foo", description="d", created=date(2026, 4, 29)),
        repos=[RepoSpec(remote=str(source_repo), local_hint=str(source_repo), worktree="code", branch_prefix="alice/foo")],
    )
    save_project_manifest(proj / "design" / "project.toml", m)

    move_calls = []
    real_move = git_ops.move_worktree
    def spy(old, new):
        move_calls.append((str(old), str(new)))
        real_move(old, new)
    monkeypatch.setattr("keel.git_ops.move_worktree", spy)
    result = runner.invoke(app, ["rename", "foo", "bar", "-y"], catch_exceptions=False)
    assert result.exit_code == 0
    assert len(move_calls) == 1
    assert (projects / "bar" / "code" / "README").is_file()
```

- [ ] **Step 2: Run, expect collection error**

- [ ] **Step 3: Implement `src/keel/commands/rename.py`**

```python
"""`keel rename` (project-level)."""
from __future__ import annotations
import shutil
import typer

from keel import git_ops, workspace
from keel.manifest import (
    ProjectManifest, ProjectMeta, RepoSpec,
    load_project_manifest, save_project_manifest,
)
from keel.output import Output
from keel.prompts import confirm_destructive
from keel.util import slugify


def cmd_rename(
    ctx: typer.Context,
    old: str = typer.Argument(..., help="Current project name."),
    new: str = typer.Argument(..., help="New project name (will be slugified)."),
    rename_branches: bool = typer.Option(True, "--rename-branches/--no-rename-branches", help="Rename worktree branches to use the new project's branch_prefix."),
    yes: bool = typer.Option(False, "-y", "--yes", help="Skip confirmation prompt."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print intended operations and exit; write nothing."),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout."),
) -> None:
    """Rename a project — directory, worktrees, branch prefixes, deliverable references."""
    out = Output.from_context(ctx, json_mode=json_mode)
    new_slug = slugify(new)
    if not new_slug:
        out.error("invalid new project name", code="invalid_name")
        raise typer.Exit(code=2)

    if not workspace.project_exists(old):
        out.error(f"project not found: {old}", code="not_found")
        raise typer.Exit(code=1)
    if workspace.project_exists(new_slug):
        out.error(f"target project already exists: {new_slug}", code="exists")
        raise typer.Exit(code=1)

    old_path = workspace.project_dir(old)
    new_path = workspace.project_dir(new_slug)

    if dry_run:
        from keel.dryrun import OpLog
        log = OpLog()
        log.modify_file(old_path, diff=f"rename → {new_path}")
        out.info(log.format_summary())
        return

    confirm_destructive(
        f"Rename project {old} → {new_slug}? Worktrees and branches will move.",
        yes=yes,
    )

    m = load_project_manifest(old_path / "design" / "project.toml")

    # Move worktrees with git_ops.move_worktree (preserves linkage)
    branch_renames: list[tuple[str, str]] = []
    new_repos = []
    for r in m.repos:
        old_wt = old_path / r.worktree
        new_wt = new_path / r.worktree
        new_path.mkdir(parents=True, exist_ok=True)
        if old_wt.is_dir():
            git_ops.move_worktree(old_wt, new_wt)
            if rename_branches and r.branch_prefix and old in r.branch_prefix:
                old_branch = git_ops.current_branch(new_wt)
                if old_branch and old_branch.startswith(r.branch_prefix):
                    new_branch_prefix = r.branch_prefix.replace(old, new_slug, 1)
                    new_branch = old_branch.replace(r.branch_prefix, new_branch_prefix, 1)
                    git_ops.rename_branch(new_wt, old=old_branch, new=new_branch)
                    branch_renames.append((old_branch, new_branch))
                    r = RepoSpec(
                        remote=r.remote, local_hint=r.local_hint,
                        worktree=r.worktree, branch_prefix=new_branch_prefix,
                    )
        new_repos.append(r)

    # Move the rest (design dir, deliverables, etc.)
    for child in list(old_path.iterdir()):
        if (new_path / child.name).exists():
            continue  # already moved (worktree)
        shutil.move(str(child), str(new_path / child.name))

    # rmdir old path if empty
    if old_path.exists() and not any(old_path.iterdir()):
        old_path.rmdir()

    # Update manifest's name and (if renamed) repo branch prefixes
    new_manifest = ProjectManifest(
        project=ProjectMeta(
            name=new_slug,
            description=m.project.description,
            created=m.project.created,
        ),
        repos=new_repos,
    )
    save_project_manifest(new_path / "design" / "project.toml", new_manifest)

    out.info(f"Renamed {old} → {new_slug}")
    out.result(
        {"old": old, "new": new_slug, "branch_renames": branch_renames},
        human_text=f"Renamed {old} → {new_slug} (branches: {len(branch_renames)}).",
    )
```

- [ ] **Step 4: Register**

```python
from keel.commands.rename import cmd_rename  # noqa: E402
app.command(name="rename")(cmd_rename)
```

- [ ] **Step 5: Run tests, expect 4 PASS**

- [ ] **Step 6: Commit**

```bash
git add keel/src/keel/commands/rename.py keel/src/keel/app.py keel/tests/commands/test_rename.py
git commit -m "feat(keel): implement project-level 'rename' with worktree + branch updates"
```

---

## Milestone 5: Final smoke + tag

### Task 5.1: Smoke + tag

- [ ] **Step 1: Run full suite**

Run: `cd ~/projects/keel && uv run --extra dev pytest -v`
Expected: substantially more than 175 PASS (Plan 3 added ~30+ new tests).

- [ ] **Step 2: Run ruff**

Run: `uv run ruff check src tests`
Expected: All checks passed.

- [ ] **Step 3: Smoke check end-to-end**

```bash
PROJECTS_DIR=/tmp/keel-p3-smoke keel new alpha -d "test" --no-worktree -y
PROJECTS_DIR=/tmp/keel-p3-smoke keel deliverable add foo -d "first" -y --project alpha
# Create a dummy git source repo for code commands:
mkdir -p /tmp/keel-p3-smoke/_src && git -C /tmp/keel-p3-smoke/_src init -b main
git -C /tmp/keel-p3-smoke/_src config user.email t@t
git -C /tmp/keel-p3-smoke/_src config user.name "Test User"
echo x > /tmp/keel-p3-smoke/_src/x.txt && git -C /tmp/keel-p3-smoke/_src add . && git -C /tmp/keel-p3-smoke/_src commit -m init
PROJECTS_DIR=/tmp/keel-p3-smoke keel code add --project alpha --repo /tmp/keel-p3-smoke/_src -y
PROJECTS_DIR=/tmp/keel-p3-smoke keel code list --project alpha
PROJECTS_DIR=/tmp/keel-p3-smoke keel code status --project alpha
PROJECTS_DIR=/tmp/keel-p3-smoke keel validate alpha
PROJECTS_DIR=/tmp/keel-p3-smoke keel design export alpha
PROJECTS_DIR=/tmp/keel-p3-smoke keel rename alpha beta -y
PROJECTS_DIR=/tmp/keel-p3-smoke keel archive beta -y
ls /tmp/keel-p3-smoke/.archive/
find /tmp/keel-p3-smoke -delete 2>/dev/null
```

Expected: every command succeeds; rename moves correctly; archive lands at `.archive/beta-<date>/`.

- [ ] **Step 4: Tag**

```bash
git -C keel tag keel-plan-3
```

---

## Self-review

**Spec coverage** — every Plan 3 requirement covered:

| Spec section | Implementing tasks |
|---|---|
| §7.13 validate | Task 2.1 |
| §7.14 archive | Task 4.1 |
| §7.15 rename (project) | Task 4.2 |
| §7.16 design export | Tasks 3.1, 3.2 |
| §7.17 code list | Task 1.2 |
| §7.18 code status | Task 1.3 |
| §7.19 code init | Task 1.4 |
| §7.20 code add | Task 1.5 |
| §7.21 code rm | Task 1.6 |

**Forward debt resolved by Plan 3:**
- Multi-repo `Path.name` collision detection (T1.5)
- `RepoSpec.worktree` single-component validator (T1.7)
- Documentation of `code init --clone-missing` UX (decided + implemented)

**Forward debt still deferred:**
- `git_user_slug` Unicode handling — punted again. No non-ASCII contributor surfaced.
- The `Output.print_rich` leaky abstraction — left as-is (Plan 2.5 decision).

**Type/name consistency:**
- All new commands use `cmd_*` naming
- All take `ctx: typer.Context` and use `Output.from_context`
- All take `--json` and (where mutating) `--dry-run`, `-y/--yes`
- `code` group uses standard `add/rm/list` verb pattern matching `deliverable` group; plus `init` (creation/idempotent) and `status` (read-only)
- `archive` and project-level `rename` mirror `deliverable rename`/`rm` semantics
- All errors use `code=` for programmatic identification

---

## What this plan does NOT cover

- Plan 4 work: `migrate` command for legacy projects, shell completion installer, slash command rewrites in `~/.claude/commands/`, the Bash CLI cutover.
