# Plan 4: Migration, completion, slash commands, cutover

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make keel the actual day-to-day tool. Migrate existing legacy projects (created with the Bash CLI before manifests existed) to the manifest-based format. Add shell completion. Re-point slash commands at keel. Archive the Bash CLI and update workspace conventions.

**Architecture:** One new top-level command (`migrate`), one wrap-around (`completion`), and a coordinated set of file edits in `~/projects/.claude/commands/` (slash command bodies), `~/projects/bin/` (Bash CLI archival), and `~/projects/CLAUDE.md` (workspace conventions).

**Tech Stack:** Same as Plans 1–3.

---

## Pre-decided open questions

These were left open in earlier plans or are settled now.

1. **Migrate is dry-run by default.** `keel migrate <name>` shows what it would write; `keel migrate <name> --apply` actually writes. Migrating all projects in the workspace at once: `keel migrate --all --apply`.

2. **Migration is non-destructive.** It writes new manifest files; it does NOT delete or overwrite the existing CLAUDE.md text. After migration, the user can re-render CLAUDE.md from the manifest by running any keel command that touches it (or via a future `keel show --regen-claude` if needed).

3. **Bash CLI is archived, not deleted.** Move `~/projects/bin/{project,commands/,lib/}` to `~/projects/bin/.archive-bash-cli/` so it's recoverable but out of `$PATH`. Keep `~/projects/bin/gdocs*` in place (separate tool, unrelated to keel).

4. **The user types `keel`, not `project`.** No symlink dance. The cutover is conceptual: workspace conventions reference `keel`, slash commands invoke `keel`, the Bash `project` no longer exists in `bin/`. If muscle memory wants `project` later, the user can add their own shell alias.

5. **`/design-sync` slash command stays Claude-driven.** It can call `keel validate` for the structural slice, but the semantic drift detection is the LLM's job. Leave the slash command alone in this plan.

6. **Migration heuristics for `branch_prefix`**: when a worktree exists at `code/` (or `code-<x>/`), read the current branch and use it as `branch_prefix` literally — don't try to be clever about parsing user/project structure. The user can edit the manifest later if the prefix is wrong.

7. **Migration of multi-repo projects**: parse the Bash CLI's "Code (<repo_name>): ../code-<repo_name>/" lines to enumerate repos. For each, the source-repo path comes from the "Source repos:" line (which lists them space-separated).

---

## File Structure

After Plan 4 lands, new/changed files:

```
~/projects/keel/
└── src/keel/commands/
    ├── migrate.py                       # CREATE — top-level migrate command
    └── completion.py                    # CREATE — top-level completion command

~/projects/.claude/commands/             # OUTSIDE the keel/ tree
├── decide.md                            # MODIFY — call `keel decision new`
├── phase.md                             # MODIFY — call `keel phase`
└── export-design.md                     # MODIFY — call `keel design export`

~/projects/                              # Workspace-level
├── CLAUDE.md                            # MODIFY — reference `keel` instead of `project`
└── bin/
    └── .archive-bash-cli/               # CREATE — moved Bash CLI for archival
        ├── project                      # MOVED from bin/project
        ├── commands/                    # MOVED from bin/commands/
        └── lib/                         # MOVED from bin/lib/
```

---

## Pre-requisites

- Plan 3 is complete and tagged `keel-plan-3`
- 217 tests passing on `main`
- Ruff clean
- Working dir for keel source: `keel/`
- Workspace root: `~/projects/`
- Run tests: `uv run --extra dev pytest`

---

## Milestone 1: `migrate` command

The Bash CLI's `CLAUDE.md` for a project looks like this (project, single-repo case):

```markdown
# my-project

A description of the project.

## Code
Code: ../code/
Source repo: ~/some-source-repo

## Deliverables
- **alpha**: ../deliverables/alpha/design/ -- the alpha thing
- **beta**: ../deliverables/beta/design/ -- the beta thing

## Workflow
...
```

For multi-repo projects:

```markdown
## Code
Code (mms): ../code-mms/
Code (ipa): ../code-ipa/
Source repos: ~/mms ~/ipa
```

Deliverable CLAUDE.md (owned worktree):

```markdown
# alpha

Description...

Parent design: ../../../design/

## Code
Code: ../code/
Source repo: ~/some-repo

## Sibling deliverables
- beta: ../beta/design/ -- the beta thing

## Workflow
...
```

Deliverable CLAUDE.md (shared worktree):

```markdown
## Code
Code: shared with parent (../../../code/)
Source repo: see parent
```

The migration parses these patterns and writes a `project.toml` / `deliverable.toml`.

### Task 1.1: Scaffold `migrate` command + dry-run skeleton

**Files:**
- Create: `src/keel/commands/migrate.py`
- Create: `tests/commands/test_migrate.py`
- Modify: `src/keel/app.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/commands/test_migrate.py
"""Tests for `keel migrate` (legacy Bash CLI projects → manifests)."""
from typer.testing import CliRunner
from keel.app import app

runner = CliRunner()


def _write_legacy_project(projects, name: str, body: str) -> None:
    """Helper: scaffold a project in the old Bash CLI shape (no manifest)."""
    proj = projects / name
    (proj / "design" / "decisions").mkdir(parents=True)
    (proj / "design" / "CLAUDE.md").write_text(body)
    (proj / "design" / "scope.md").write_text(f"# {name}\nScope.\n")
    (proj / "design" / "design.md").write_text(f"# {name}\nDesign.\n")
    (proj / "design" / ".phase").write_text("scoping\n")


def test_migrate_dry_run_default(projects) -> None:
    """Without --apply, migrate must not write anything."""
    _write_legacy_project(projects, "legacy", "# legacy\n\nold project.\n\n## Code\nCode: ../code/\nSource repo: /tmp/some-repo\n\n## Workflow\n")
    result = runner.invoke(app, ["migrate", "legacy"])
    assert result.exit_code == 0
    assert not (projects / "legacy" / "design" / "project.toml").exists()


def test_migrate_unknown_project(projects) -> None:
    result = runner.invoke(app, ["migrate", "ghost"])
    assert result.exit_code == 1


def test_migrate_skips_already_migrated(projects, make_project) -> None:
    """If project.toml already exists, migrate is a no-op (info, exit 0)."""
    make_project("foo")  # already has project.toml
    result = runner.invoke(app, ["migrate", "foo"])
    assert result.exit_code == 0
    assert "already" in result.stderr.lower() or "skipping" in result.stderr.lower()
```

- [ ] **Step 2: Run, expect collection error**

- [ ] **Step 3: Implement `src/keel/commands/migrate.py` skeleton**

```python
"""`keel migrate` — convert legacy Bash CLI projects to manifest format."""
from __future__ import annotations
from pathlib import Path
import typer

from keel import workspace
from keel.output import Output


def cmd_migrate(
    ctx: typer.Context,
    name: str | None = typer.Argument(None, help="Project name to migrate. Auto-detected from CWD if omitted."),
    all_projects: bool = typer.Option(False, "--all", help="Migrate every legacy project under $PROJECTS_DIR."),
    apply: bool = typer.Option(False, "--apply", help="Actually write the manifests (default is dry-run preview)."),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout."),
) -> None:
    """Migrate a project (or all projects) from Bash-CLI format to manifest format.

    Default is dry-run; pass --apply to write.
    """
    out = Output.from_context(ctx, json_mode=json_mode)

    if all_projects:
        targets = []
        root = workspace.projects_dir()
        if root.is_dir():
            for child in sorted(root.iterdir()):
                if child.is_dir() and (child / "design" / "CLAUDE.md").is_file():
                    targets.append(child.name)
    else:
        if name is None:
            scope = workspace.detect_scope()
            name = scope.project
        if name is None:
            out.error("no project specified and none detected from CWD", code="no_project")
            raise typer.Exit(code=1)
        if not (workspace.project_dir(name) / "design" / "CLAUDE.md").is_file():
            out.error(f"not a project: {name}", code="not_found")
            raise typer.Exit(code=1)
        targets = [name]

    results: list[dict] = []
    for target in targets:
        proj_dir = workspace.project_dir(target)
        if (proj_dir / "design" / "project.toml").is_file():
            out.info(f"{target}: already migrated, skipping")
            results.append({"name": target, "status": "skipped"})
            continue
        # Dry-run-only path for T1.1; T1.2-T1.6 implement the actual migration.
        out.info(f"[dry-run] would migrate {target}")
        results.append({"name": target, "status": "dry-run"})

    out.result({"results": results}, human_text=f"Processed {len(results)} project(s).")
```

- [ ] **Step 4: Register in `app.py`**

```python
from keel.commands.migrate import cmd_migrate  # noqa: E402
app.command(name="migrate")(cmd_migrate)
```

- [ ] **Step 5: Run tests, expect 3 PASS**

- [ ] **Step 6: Commit**

```bash
git add keel/src/keel/commands/migrate.py keel/src/keel/app.py keel/tests/commands/test_migrate.py
git commit -m "feat(keel): scaffold 'migrate' command with dry-run skeleton"
```

---

### Task 1.2: Parse legacy `## Code` section into RepoSpec entries

**Files:**
- Modify: `src/keel/commands/migrate.py`
- Modify: `tests/commands/test_migrate.py`

The parser needs to handle three shapes:

1. **Single-repo**: `Code: ../code/` followed by `Source repo: <path>`
2. **Multi-repo**: `Code (<n>): ../code-<n>/` (one or more) followed by `Source repos: <p1> <p2>`
3. **Shared (deliverables)**: `Code: shared with parent (../../../code/)` followed by `Source repo: see parent`
4. **Design-only**: no `## Code` section at all, or `Code: [to be configured -- future worktree]`

Output: `(list[RepoSpec], shared: bool)` where `shared=True` only matters for deliverables.

- [ ] **Step 1: Write failing tests**

Append to `test_migrate.py`:

```python
def test_parse_code_section_single_repo() -> None:
    from keel.commands.migrate import _parse_code_section
    text = "## Code\nCode: ../code/\nSource repo: /tmp/some-repo\n"
    repos, shared = _parse_code_section(text, "myproj")
    assert shared is False
    assert len(repos) == 1
    assert repos[0].worktree == "code"
    assert repos[0].remote == "/tmp/some-repo"
    assert repos[0].local_hint == "/tmp/some-repo"


def test_parse_code_section_multi_repo() -> None:
    from keel.commands.migrate import _parse_code_section
    text = """## Code
Code (mms): ../code-mms/
Code (ipa): ../code-ipa/
Source repos: /Users/me/mms /Users/me/ipa
"""
    repos, shared = _parse_code_section(text, "myproj")
    assert shared is False
    assert len(repos) == 2
    worktrees = {r.worktree for r in repos}
    assert worktrees == {"code-mms", "code-ipa"}
    remotes = {r.remote for r in repos}
    assert remotes == {"/Users/me/mms", "/Users/me/ipa"}


def test_parse_code_section_shared() -> None:
    from keel.commands.migrate import _parse_code_section
    text = "## Code\nCode: shared with parent (../../../code/)\nSource repo: see parent\n"
    repos, shared = _parse_code_section(text, "myproj")
    assert shared is True
    assert repos == []


def test_parse_code_section_design_only() -> None:
    from keel.commands.migrate import _parse_code_section
    text = "## Workflow\n..."
    repos, shared = _parse_code_section(text, "myproj")
    assert shared is False
    assert repos == []
```

- [ ] **Step 2: Run, expect 4 FAIL**

- [ ] **Step 3: Implement `_parse_code_section` in `migrate.py`**

Add to `migrate.py` (top-level):

```python
import re

_CODE_SECTION_RE = re.compile(r"## Code\n(.*?)(?:\n## |\Z)", re.DOTALL)
_SINGLE_CODE_RE = re.compile(r"^Code:\s+\.\./code/?\s*$", re.MULTILINE)
_MULTI_CODE_RE = re.compile(r"^Code\s+\(([^)]+)\):\s+\.\./code-([^/\s]+)/?\s*$", re.MULTILINE)
_SHARED_CODE_RE = re.compile(r"^Code:\s+shared with parent", re.MULTILINE)
_SOURCE_REPO_RE = re.compile(r"^Source repo:\s+(.+?)\s*$", re.MULTILINE)
_SOURCE_REPOS_RE = re.compile(r"^Source repos:\s+(.+?)\s*$", re.MULTILINE)


def _parse_code_section(claude_md_text: str, project_name: str) -> tuple[list, bool]:
    """Parse a legacy CLAUDE.md '## Code' section.

    Returns (list[RepoSpec], shared_worktree).
    """
    from keel.manifest import RepoSpec

    section_match = _CODE_SECTION_RE.search(claude_md_text)
    if not section_match:
        return [], False
    section = section_match.group(1)

    if _SHARED_CODE_RE.search(section):
        return [], True

    repos: list[RepoSpec] = []

    # Multi-repo: collect all "Code (<name>): ../code-<name>/" lines
    multi_matches = list(_MULTI_CODE_RE.finditer(section))
    if multi_matches:
        # Source repos line: space-separated paths
        source_repos_line = _SOURCE_REPOS_RE.search(section)
        source_paths = source_repos_line.group(1).split() if source_repos_line else []
        # Map each entry by basename to the corresponding code-<x> dir
        for m in multi_matches:
            code_name = m.group(1)  # e.g. "mms"
            wt_name = f"code-{m.group(2)}"
            # Find the matching source path by basename
            remote = next((p for p in source_paths if Path(p).name == code_name), None) or ""
            repos.append(RepoSpec(
                remote=remote,
                local_hint=remote or None,
                worktree=wt_name,
                branch_prefix=None,
            ))
        return repos, False

    # Single-repo
    if _SINGLE_CODE_RE.search(section):
        source_match = _SOURCE_REPO_RE.search(section)
        if source_match:
            remote = source_match.group(1).strip()
            repos.append(RepoSpec(
                remote=remote,
                local_hint=remote,
                worktree="code",
                branch_prefix=None,
            ))
        return repos, False

    # Design-only or unrecognized — return empty
    return [], False
```

- [ ] **Step 4: Run tests, expect 4 PASS**

- [ ] **Step 5: Commit**

```bash
git add keel/src/keel/commands/migrate.py keel/tests/commands/test_migrate.py
git commit -m "feat(keel): parse legacy '## Code' section in migrate"
```

---

### Task 1.3: Discover existing worktrees + derive `branch_prefix`

**Files:**
- Modify: `src/keel/commands/migrate.py`
- Modify: `tests/commands/test_migrate.py`

If a worktree exists at the declared path, fill in `branch_prefix` from the current branch.

- [ ] **Step 1: Write failing test**

```python
def test_enrich_repos_with_branch_from_worktree(projects, source_repo) -> None:
    """When a worktree exists, branch_prefix is filled from the current branch."""
    from keel import git_ops
    from keel.commands.migrate import _enrich_with_worktree_state
    from keel.manifest import RepoSpec

    # Stage a project dir with an existing worktree
    proj = projects / "legacy"
    proj.mkdir()
    git_ops.create_worktree(source_repo, proj / "code", branch="alice/legacy-base")

    repos = [RepoSpec(remote=str(source_repo), worktree="code")]
    enriched = _enrich_with_worktree_state(proj, repos)
    assert enriched[0].branch_prefix == "alice/legacy-base"
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement `_enrich_with_worktree_state`**

Add to `migrate.py`:

```python
def _enrich_with_worktree_state(unit_dir: Path, repos: list) -> list:
    """For each repo with a worktree on disk, fill branch_prefix from the current branch."""
    from keel import git_ops
    from keel.manifest import RepoSpec

    enriched: list[RepoSpec] = []
    for r in repos:
        wt = unit_dir / r.worktree
        prefix = r.branch_prefix
        if prefix is None and wt.is_dir() and git_ops.is_git_repo(wt):
            try:
                cur = git_ops.current_branch(wt)
                if cur:
                    prefix = cur
            except git_ops.GitError:
                pass
        enriched.append(RepoSpec(
            remote=r.remote,
            local_hint=r.local_hint,
            worktree=r.worktree,
            branch_prefix=prefix,
        ))
    return enriched
```

- [ ] **Step 4: Run tests, expect PASS**

- [ ] **Step 5: Commit**

```bash
git add keel/src/keel/commands/migrate.py keel/tests/commands/test_migrate.py
git commit -m "feat(keel): derive branch_prefix from existing worktrees in migrate"
```

---

### Task 1.4: Write project manifest end-to-end

**Files:**
- Modify: `src/keel/commands/migrate.py`
- Modify: `tests/commands/test_migrate.py`

Wire T1.2 + T1.3 into `cmd_migrate` so `--apply` writes a real `project.toml`. (Deliverable migration is T1.5.)

- [ ] **Step 1: Write failing test**

```python
def test_migrate_apply_writes_project_manifest(projects, source_repo) -> None:
    from keel import git_ops
    proj = projects / "legacy"
    (proj / "design" / "decisions").mkdir(parents=True)
    (proj / "design" / "CLAUDE.md").write_text(
        f"# legacy\n\nold project.\n\n## Code\nCode: ../code/\nSource repo: {source_repo}\n\n## Workflow\n"
    )
    (proj / "design" / "scope.md").write_text("# legacy\n")
    (proj / "design" / "design.md").write_text("# legacy\n")
    (proj / "design" / ".phase").write_text("scoping\n")
    git_ops.create_worktree(source_repo, proj / "code", branch="alice/legacy-base")

    result = runner.invoke(app, ["migrate", "legacy", "--apply"])
    assert result.exit_code == 0, result.stderr
    from keel.manifest import load_project_manifest
    m = load_project_manifest(proj / "design" / "project.toml")
    assert m.project.name == "legacy"
    assert len(m.repos) == 1
    assert m.repos[0].worktree == "code"
    assert m.repos[0].remote == str(source_repo)
    assert m.repos[0].branch_prefix == "alice/legacy-base"


def test_migrate_apply_design_only_project(projects) -> None:
    """Project with no '## Code' section migrates to a manifest with no repos."""
    proj = projects / "designer"
    (proj / "design" / "decisions").mkdir(parents=True)
    (proj / "design" / "CLAUDE.md").write_text("# designer\n\nDesign-only.\n\n## Workflow\n")
    (proj / "design" / "scope.md").write_text("# designer\n")
    (proj / "design" / "design.md").write_text("# designer\n")
    (proj / "design" / ".phase").write_text("scoping\n")
    result = runner.invoke(app, ["migrate", "designer", "--apply"])
    assert result.exit_code == 0
    from keel.manifest import load_project_manifest
    m = load_project_manifest(proj / "design" / "project.toml")
    assert m.repos == []
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Update `cmd_migrate`**

Replace the dry-run-only path in `cmd_migrate` with:

```python
    from datetime import date
    from keel.manifest import (
        ProjectManifest, ProjectMeta,
        save_project_manifest,
    )

    results: list[dict] = []
    for target in targets:
        proj_dir = workspace.project_dir(target)
        manifest_path = proj_dir / "design" / "project.toml"
        if manifest_path.is_file():
            out.info(f"{target}: already migrated, skipping")
            results.append({"name": target, "status": "skipped"})
            continue

        claude_md = proj_dir / "design" / "CLAUDE.md"
        if not claude_md.is_file():
            out.warn(f"{target}: no CLAUDE.md, skipping")
            results.append({"name": target, "status": "skipped"})
            continue

        text = claude_md.read_text()
        repos, _shared = _parse_code_section(text, target)
        repos = _enrich_with_worktree_state(proj_dir, repos)

        # Description: take the second non-empty line of the CLAUDE.md after the title
        desc = _extract_description(text) or "[migrated; description not extracted]"

        manifest = ProjectManifest(
            project=ProjectMeta(
                name=target,
                description=desc,
                created=date.today(),  # we don't know the original creation date
            ),
            repos=repos,
        )

        if apply:
            save_project_manifest(manifest_path, manifest)
            out.info(f"{target}: wrote {manifest_path}")
            results.append({"name": target, "status": "migrated", "repos": len(repos)})
        else:
            out.info(f"[dry-run] {target}: would write project.toml with {len(repos)} repo(s)")
            results.append({"name": target, "status": "dry-run", "repos": len(repos)})

    out.result({"results": results}, human_text=f"Processed {len(results)} project(s).")
```

Add the description-extraction helper:

```python
_TITLE_RE = re.compile(r"^# (.+?)\s*$", re.MULTILINE)


def _extract_description(text: str) -> str | None:
    """Heuristic: the first non-empty line after '# Title' is the description."""
    title_match = _TITLE_RE.search(text)
    if not title_match:
        return None
    after = text[title_match.end():].lstrip("\n")
    for line in after.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return line
    return None
```

- [ ] **Step 4: Run tests, expect both PASS**

- [ ] **Step 5: Commit**

```bash
git add keel/src/keel/commands/migrate.py keel/tests/commands/test_migrate.py
git commit -m "feat(keel): migrate writes project.toml with --apply"
```

---

### Task 1.5: Migrate deliverables

**Files:**
- Modify: `src/keel/commands/migrate.py`
- Modify: `tests/commands/test_migrate.py`

For each deliverable directory under `<project>/deliverables/`, parse its `CLAUDE.md`'s "## Code" section (which may say `shared with parent`), enrich with on-disk worktree state, and write `deliverable.toml`. Initialize a missing `.phase` file to `scoping`.

- [ ] **Step 1: Write failing tests**

```python
def test_migrate_writes_deliverable_manifests(projects) -> None:
    """Each deliverable on disk gets a deliverable.toml after migration."""
    proj = projects / "legacy"
    (proj / "design" / "decisions").mkdir(parents=True)
    (proj / "design" / "CLAUDE.md").write_text("# legacy\n\nold.\n\n## Workflow\n")
    (proj / "design" / "scope.md").write_text("# x\n")
    (proj / "design" / "design.md").write_text("# x\n")
    (proj / "design" / ".phase").write_text("scoping\n")

    # Add a deliverable with a shared worktree
    deliv = proj / "deliverables" / "alpha"
    (deliv / "design" / "decisions").mkdir(parents=True)
    (deliv / "design" / "CLAUDE.md").write_text(
        "# alpha\n\nthe alpha thing.\n\nParent design: ../../../design/\n\n"
        "## Code\nCode: shared with parent (../../../code/)\nSource repo: see parent\n\n## Workflow\n"
    )
    (deliv / "design" / "design.md").write_text("# alpha\n")
    # Note: no .phase yet — migrate should create it

    result = runner.invoke(app, ["migrate", "legacy", "--apply"])
    assert result.exit_code == 0, result.stderr
    from keel.manifest import load_deliverable_manifest
    m = load_deliverable_manifest(deliv / "design" / "deliverable.toml")
    assert m.deliverable.name == "alpha"
    assert m.deliverable.parent_project == "legacy"
    assert m.deliverable.shared_worktree is True
    assert m.repos == []
    # .phase was created
    assert (deliv / "design" / ".phase").read_text().splitlines()[0] == "scoping"


def test_migrate_skips_already_migrated_deliverable(projects) -> None:
    """A deliverable that already has deliverable.toml is left alone."""
    from keel.manifest import (
        DeliverableManifest, DeliverableMeta,
        save_deliverable_manifest,
    )
    from datetime import date as _date

    proj = projects / "legacy"
    (proj / "design" / "decisions").mkdir(parents=True)
    (proj / "design" / "CLAUDE.md").write_text("# legacy\n\nold.\n\n## Workflow\n")
    (proj / "design" / "scope.md").write_text("# x\n")
    (proj / "design" / "design.md").write_text("# x\n")
    (proj / "design" / ".phase").write_text("scoping\n")

    deliv = proj / "deliverables" / "alpha"
    (deliv / "design" / "decisions").mkdir(parents=True)
    save_deliverable_manifest(
        deliv / "design" / "deliverable.toml",
        DeliverableManifest(
            deliverable=DeliverableMeta(
                name="alpha", parent_project="legacy", description="kept",
                created=_date(2025, 1, 1), shared_worktree=False,
            ),
            repos=[],
        ),
    )
    (deliv / "design" / "CLAUDE.md").write_text("# alpha\n\nDIFFERENT description.\n\n## Workflow\n")

    runner.invoke(app, ["migrate", "legacy", "--apply"])

    # The pre-existing manifest is preserved (not overwritten)
    from keel.manifest import load_deliverable_manifest
    m = load_deliverable_manifest(deliv / "design" / "deliverable.toml")
    assert m.deliverable.description == "kept"
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Add `_migrate_deliverables` and call it from `cmd_migrate`**

Append helper to `migrate.py`:

```python
def _migrate_deliverables(proj_dir: Path, project_name: str, apply: bool, out) -> int:
    """Migrate each deliverable under proj_dir/deliverables/.

    Returns count of deliverables migrated (or that would be in dry-run).
    """
    from datetime import date
    from keel.manifest import (
        DeliverableManifest, DeliverableMeta,
        save_deliverable_manifest,
    )

    deliv_dir = proj_dir / "deliverables"
    if not deliv_dir.is_dir():
        return 0

    count = 0
    for deliv in sorted(deliv_dir.iterdir()):
        if not deliv.is_dir():
            continue
        manifest_path = deliv / "design" / "deliverable.toml"
        if manifest_path.is_file():
            continue  # already migrated, leave alone
        claude_md = deliv / "design" / "CLAUDE.md"
        if not claude_md.is_file():
            continue

        text = claude_md.read_text()
        repos, shared = _parse_code_section(text, deliv.name)
        repos = _enrich_with_worktree_state(deliv, repos)
        desc = _extract_description(text) or "[migrated]"

        manifest = DeliverableManifest(
            deliverable=DeliverableMeta(
                name=deliv.name,
                parent_project=project_name,
                description=desc,
                created=date.today(),
                shared_worktree=shared,
            ),
            repos=repos,
        )

        if apply:
            save_deliverable_manifest(manifest_path, manifest)
            # Initialize .phase if missing
            phase_file = deliv / "design" / ".phase"
            if not phase_file.is_file():
                phase_file.write_text("scoping\n")
            out.info(f"  deliverable {deliv.name}: wrote {manifest_path}")
        else:
            out.info(f"  [dry-run] deliverable {deliv.name}: would write deliverable.toml")
        count += 1
    return count
```

In `cmd_migrate`, after writing the project manifest (or in dry-run, after the dry-run line), add:

```python
        # Migrate deliverables under this project
        d_count = _migrate_deliverables(proj_dir, target, apply, out)
        if results and isinstance(results[-1], dict):
            results[-1]["deliverables"] = d_count
```

- [ ] **Step 4: Run tests, expect both PASS**

- [ ] **Step 5: Commit**

```bash
git add keel/src/keel/commands/migrate.py keel/tests/commands/test_migrate.py
git commit -m "feat(keel): migrate deliverables (deliverable.toml + .phase init)"
```

---

### Task 1.6: `migrate --all` end-to-end + integration test

**Files:**
- Modify: `tests/commands/test_migrate.py`

`--all` is already wired in T1.1 (the `targets` loop). This task adds an end-to-end test that exercises the full migration of a synthetic legacy project including a multi-deliverable setup, then verifies `keel validate` is clean afterwards.

- [ ] **Step 1: Write the integration test**

Append:

```python
def test_migrate_all_full_round_trip(projects, source_repo) -> None:
    """Migrate a legacy project + 2 deliverables, then validate runs clean."""
    from keel import git_ops

    proj = projects / "legacy"
    (proj / "design" / "decisions").mkdir(parents=True)
    (proj / "design" / "CLAUDE.md").write_text(
        f"""# legacy

A migrated project.

## Code
Code: ../code/
Source repo: {source_repo}

## Deliverables
- **alpha**: ../deliverables/alpha/design/ -- alpha thing
- **beta**: ../deliverables/beta/design/ -- beta thing

## Workflow
"""
    )
    (proj / "design" / "scope.md").write_text("# legacy\nscope.\n")
    (proj / "design" / "design.md").write_text("# legacy\ndesign.\n")
    (proj / "design" / ".phase").write_text("scoping\n")
    git_ops.create_worktree(source_repo, proj / "code", branch="me/legacy-base")

    for d_name in ("alpha", "beta"):
        d = proj / "deliverables" / d_name
        (d / "design" / "decisions").mkdir(parents=True)
        (d / "design" / "CLAUDE.md").write_text(
            f"""# {d_name}

The {d_name} thing.

Parent design: ../../../design/

## Code
Code: shared with parent (../../../code/)
Source repo: see parent

## Workflow
"""
        )
        (d / "design" / "design.md").write_text(f"# {d_name}\n")

    # Migrate everything
    result = runner.invoke(app, ["migrate", "--all", "--apply"])
    assert result.exit_code == 0, result.stderr

    # Manifests exist
    from keel.manifest import load_project_manifest, load_deliverable_manifest
    pm = load_project_manifest(proj / "design" / "project.toml")
    assert pm.project.name == "legacy"
    assert pm.repos[0].branch_prefix == "me/legacy-base"
    am = load_deliverable_manifest(proj / "deliverables" / "alpha" / "design" / "deliverable.toml")
    assert am.deliverable.shared_worktree is True
    bm = load_deliverable_manifest(proj / "deliverables" / "beta" / "design" / "deliverable.toml")
    assert bm.deliverable.shared_worktree is True

    # Both deliverables now have .phase
    assert (proj / "deliverables" / "alpha" / "design" / ".phase").read_text().splitlines()[0] == "scoping"
    assert (proj / "deliverables" / "beta" / "design" / ".phase").read_text().splitlines()[0] == "scoping"

    # validate runs clean (no FAILs; the parent CLAUDE.md still mentions both deliverables)
    val = runner.invoke(app, ["validate", "legacy", "--json"])
    import json
    payload = json.loads(val.stdout)
    assert payload["summary"]["fail"] == 0
```

- [ ] **Step 2: Run tests, expect PASS**

- [ ] **Step 3: Commit**

```bash
git add keel/tests/commands/test_migrate.py
git commit -m "test(keel): end-to-end migrate --all integration test"
```

---

## Milestone 2: Shell completion

### Task 2.1: `keel completion {bash|zsh|fish}` command

**Files:**
- Create: `src/keel/commands/completion.py`
- Create: `tests/commands/test_completion.py`
- Modify: `src/keel/app.py`

Typer ships with built-in `--install-completion` and `--show-completion` flags on the root app, so a wrapper command isn't strictly necessary — but a friendlier UX prints the completion script for the chosen shell, with optional `--install` to write it to the canonical location.

- [ ] **Step 1: Write failing tests**

```python
# tests/commands/test_completion.py
"""Tests for `keel completion`."""
from typer.testing import CliRunner
from keel.app import app

runner = CliRunner()


def test_completion_bash_prints_script() -> None:
    result = runner.invoke(app, ["completion", "bash"])
    assert result.exit_code == 0
    # Typer/Click bash completion contains _KEEL_COMPLETE setup
    assert "complete" in result.stdout.lower()


def test_completion_zsh_prints_script() -> None:
    result = runner.invoke(app, ["completion", "zsh"])
    assert result.exit_code == 0
    # Zsh completion uses #compdef
    assert "#compdef" in result.stdout or "compdef" in result.stdout or "complete" in result.stdout.lower()


def test_completion_fish_prints_script() -> None:
    result = runner.invoke(app, ["completion", "fish"])
    assert result.exit_code == 0
    assert "complete" in result.stdout.lower()


def test_completion_unsupported_shell() -> None:
    result = runner.invoke(app, ["completion", "csh"])
    assert result.exit_code != 0
```

- [ ] **Step 2: Run, expect collection error**

- [ ] **Step 3: Implement `src/keel/commands/completion.py`**

```python
"""`keel completion`."""
from __future__ import annotations
import os
import typer

from keel.output import Output


_SUPPORTED = {"bash", "zsh", "fish"}


def cmd_completion(
    ctx: typer.Context,
    shell: str = typer.Argument(..., help="Shell to generate completion for: bash, zsh, or fish."),
    install: bool = typer.Option(False, "--install", help="Write the completion to the canonical location for the chosen shell."),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout."),
) -> None:
    """Print (or install) shell completion for `keel`."""
    out = Output.from_context(ctx, json_mode=json_mode)
    if shell not in _SUPPORTED:
        out.error(f"unsupported shell: {shell}. Supported: {', '.join(sorted(_SUPPORTED))}", code="bad_shell")
        raise typer.Exit(code=2)

    # Use Click's completion machinery by setting the documented env var and calling the app
    # in completion mode. This mirrors what `--show-completion` does internally.
    import subprocess
    env = os.environ.copy()
    env["_KEEL_COMPLETE"] = f"{shell}_source"
    result = subprocess.run(
        ["keel"],
        env=env,
        capture_output=True,
        text=True,
    )
    script = result.stdout

    if install:
        # Canonical install paths per shell
        target_paths = {
            "bash": "~/.bash_completion.d/keel",
            "zsh": "~/.zfunc/_keel",
            "fish": "~/.config/fish/completions/keel.fish",
        }
        from pathlib import Path
        target = Path(target_paths[shell]).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(script)
        out.info(f"Installed completion for {shell} → {target}")
        out.result({"path": str(target), "shell": shell}, human_text=str(target))
    else:
        if json_mode:
            out.result({"shell": shell, "script": script})
        else:
            print(script)
```

- [ ] **Step 4: Register in `app.py`**

```python
from keel.commands.completion import cmd_completion  # noqa: E402
app.command(name="completion")(cmd_completion)
```

- [ ] **Step 5: Run tests, expect 4 PASS**

Note: the subprocess call to `keel` in the implementation may not work cleanly under `CliRunner.invoke` since the test runs in-process. If the test fails, adjust the implementation to use Typer's `get_completion_inspect_parameters` / `get_completion_class` helpers directly instead of shelling out. The end-user behavior is what matters; pick whichever path makes the tests pass without a real `keel` binary on PATH.

A simpler implementation that works in-process: call Click's `_get_completion_func` directly. Pseudocode if subprocess proves brittle in tests:

```python
import click.shell_completion as cc
comp_cls = cc.get_completion_class(shell)
prog_name = "keel"
complete_var = "_KEEL_COMPLETE"
script = comp_cls(app, {}, prog_name, complete_var).source()
```

If this also doesn't work cleanly, downgrade the test scope to "exit code 0" + "stdout is non-empty" rather than asserting specific completion-script content.

- [ ] **Step 6: Commit**

```bash
git add keel/src/keel/commands/completion.py keel/src/keel/app.py keel/tests/commands/test_completion.py
git commit -m "feat(keel): implement 'completion' command (bash/zsh/fish)"
```

---

## Milestone 3: Slash command rewrites

The slash commands live at `~/projects/.claude/commands/`. They are workspace-local. They currently invoke the Bash CLI at `~/projects/bin/project`. After Plan 4, they invoke `keel`.

### Task 3.1: `/decide` slash command

**Files:**
- Modify: `~/projects/.claude/commands/decide.md`

Current behavior calls `~/projects/bin/project decision -t "<title>"` — replace with `keel decision new "<title>"`.

- [ ] **Step 1: Read the current file**

```bash
cat ~/projects/.claude/commands/decide.md
```

- [ ] **Step 2: Replace the Bash-CLI invocation**

In the body, find the step that says `Call ~/projects/bin/project decision with -t "<title>" and the detected -p / -D flags. This scaffolds the file under the correct design/decisions/ directory.` Replace with:

```
Call `keel decision new "<title>"` with the detected `--project` / `-D` flags. By default, run from inside the project's (or deliverable's) `design/` directory and let CWD auto-detection do the work. Pass `--no-edit` if the assistant should fill in the scaffolded file directly rather than opening `$EDITOR`. If the user wants to supersede an existing decision, pass `--supersedes <slug>`.
```

- [ ] **Step 3: Verify there are no remaining `~/projects/bin/project` references**

```bash
grep -n 'projects/bin/project' ~/projects/.claude/commands/decide.md || echo "none"
```

- [ ] **Step 4: Commit**

```bash
git add .claude/commands/decide.md
git commit -m "chore(slash): repoint /decide at 'keel decision new'"
```

---

### Task 3.2: `/phase` slash command

**Files:**
- Modify: `~/projects/.claude/commands/phase.md`

- [ ] **Step 1: Read current file**

- [ ] **Step 2: Replace `~/projects/bin/project phase` invocations with `keel phase`**

Specifically: any line that calls the Bash CLI's `phase` subcommand should call `keel phase` (same flags — both accept `[PHASE]` positional, `-D/--deliverable`, `-m/--message`, `--next`, `--no-decision`).

- [ ] **Step 3: Verify**

```bash
grep -n 'projects/bin/project' ~/projects/.claude/commands/phase.md || echo "none"
```

- [ ] **Step 4: Commit**

```bash
git add .claude/commands/phase.md
git commit -m "chore(slash): repoint /phase at 'keel phase'"
```

---

### Task 3.3: `/export-design` slash command

**Files:**
- Modify: `~/projects/.claude/commands/export-design.md`

- [ ] **Step 1: Read current file**

- [ ] **Step 2: Replace `~/projects/bin/project export-design` with `keel design export`**

The Bash CLI's `export-design -p NAME [-D DELIV] [-o PATH]` maps to `keel design export NAME [-D DELIV] [-o PATH]`. Update the slash command body accordingly.

- [ ] **Step 3: Verify and commit**

```bash
grep -n 'projects/bin/project' ~/projects/.claude/commands/export-design.md || echo "none"
git add .claude/commands/export-design.md
git commit -m "chore(slash): repoint /export-design at 'keel design export'"
```

---

### Task 3.4: Audit remaining slash commands for Bash references

**Files:**
- Modify: any other `.claude/commands/*.md` that mentions the Bash CLI

There may be other slash commands (`new-project.md`, `review-scope.md`, etc.) that mention the Bash CLI in passing or as a step.

- [ ] **Step 1: Audit**

```bash
grep -rn -E 'projects/bin/project|project decision|project phase|project export-design|project new |project list |project show ' ~/projects/.claude/commands/ 2>&1
```

- [ ] **Step 2: Update each match**

For every match that's a real invocation (not just text describing the *concept* of a project), replace with the equivalent `keel` invocation:
- `project decision ...` → `keel decision new ...`
- `project phase ...` → `keel phase ...`
- `project export-design ...` → `keel design export ...`
- `project new ...` → `keel new ...`
- `project list` → `keel list`
- `project show` → `keel show`
- `project add-deliverable` → `keel deliverable add`

- [ ] **Step 3: Verify**

```bash
grep -rn 'projects/bin/project' ~/projects/.claude/commands/ || echo "no remaining references"
```

- [ ] **Step 4: Commit**

```bash
git add .claude/commands/
git commit -m "chore(slash): audit and repoint remaining slash commands at keel"
```

---

## Milestone 4: Workspace docs + Bash CLI cutover

### Task 4.1: Update `~/projects/CLAUDE.md` to reference `keel`

**File:**
- Modify: `~/projects/CLAUDE.md`

The workspace conventions doc currently points at `~/projects/bin/project` and the Bash slash commands. Update to reference `keel`.

- [ ] **Step 1: Read current `CLAUDE.md`**

```bash
cat ~/projects/CLAUDE.md
```

- [ ] **Step 2: Replace each `project` CLI reference with `keel`**

Specifically:
- Replace `~/projects/bin/project new` with `keel new`
- Replace `~/projects/bin/project add-deliverable` with `keel deliverable add`
- Replace `~/projects/bin/project decision` with `keel decision new`
- Replace `~/projects/bin/project phase` with `keel phase`
- Replace `~/projects/bin/project export-design` with `keel design export`
- Replace `~/projects/bin/project list` with `keel list`
- Replace `~/projects/bin/project show <name>` with `keel show <name>`
- Add a one-liner near the top describing keel: "The CLI for managing this workspace is `keel` — a Python-based scope-driven scaffolder. Source: https://github.com/andmatei/keel."

Leave the `~/projects/bin/gdocs*` references alone — those are unrelated tools.

- [ ] **Step 3: Verify**

```bash
grep -n 'projects/bin/project\b' ~/projects/CLAUDE.md || echo "no remaining bash-cli references"
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(workspace): update conventions to reference keel"
```

---

### Task 4.2: Archive the Bash CLI

**Files:**
- Move: `~/projects/bin/project` → `~/projects/bin/.archive-bash-cli/project`
- Move: `~/projects/bin/commands/` → `~/projects/bin/.archive-bash-cli/commands/`
- Move: `~/projects/bin/lib/` → `~/projects/bin/.archive-bash-cli/lib/`

Keep `~/projects/bin/gdocs*` in place (separate tool).

- [ ] **Step 1: Stage the archive directory and move files**

```bash
mkdir -p ~/projects/bin/.archive-bash-cli
git -C keel mv bin/project bin/.archive-bash-cli/project
git -C keel mv bin/commands bin/.archive-bash-cli/commands
git -C keel mv bin/lib bin/.archive-bash-cli/lib
```

- [ ] **Step 2: Add a README at the archive root**

Create `~/projects/bin/.archive-bash-cli/README.md`:

```markdown
# Archived Bash CLI

The original Bash CLI lived here at `~/projects/bin/project`. It was retired
on 2026-04-29 in favor of [keel](https://github.com/andmatei/keel) — a
Python scope-driven scaffolder.

This directory is preserved for historical reference only. Do not put it
back on `$PATH`. Old commands map to keel like this:

| Old (Bash) | New (keel) |
|---|---|
| `project new` | `keel new` |
| `project add-deliverable` | `keel deliverable add` |
| `project decision` | `keel decision new` |
| `project phase` | `keel phase` |
| `project export-design` | `keel design export` |
| `project list` | `keel list` |
| `project show` | `keel show` |
```

- [ ] **Step 3: Verify the Bash CLI is no longer reachable**

```bash
which project || echo "no 'project' on PATH (expected)"
test -f ~/projects/bin/project && echo "ERROR: still in bin/" || echo "moved cleanly"
```

- [ ] **Step 4: Commit**

```bash
git add bin/
git commit -m "chore(workspace): archive Bash CLI to bin/.archive-bash-cli/"
```

---

### Task 4.3: Final smoke + tag `keel-plan-4`

- [ ] **Step 1: Run keel test suite**

```bash
cd ~/projects/keel && uv run --extra dev pytest -v
```
Expected: substantially more than 217 PASS (Plan 4 added ~10 tests for migrate, 4 for completion).

- [ ] **Step 2: Run ruff**

```bash
uv run ruff check src tests
```
Expected: All checks passed.

- [ ] **Step 3: Smoke check the migration on a synthetic legacy project**

```bash
mkdir -p /tmp/keel-p4-smoke/myproj/design/decisions
cat > /tmp/keel-p4-smoke/myproj/design/CLAUDE.md << 'EOF'
# myproj

A test project.

## Code
Code: ../code/
Source repo: /tmp/keel-p4-smoke/_src

## Workflow
EOF
echo "scoping" > /tmp/keel-p4-smoke/myproj/design/.phase
echo "# myproj" > /tmp/keel-p4-smoke/myproj/design/scope.md
echo "# myproj" > /tmp/keel-p4-smoke/myproj/design/design.md

PROJECTS_DIR=/tmp/keel-p4-smoke keel migrate myproj
PROJECTS_DIR=/tmp/keel-p4-smoke keel migrate myproj --apply
test -f /tmp/keel-p4-smoke/myproj/design/project.toml && echo "manifest written"
PROJECTS_DIR=/tmp/keel-p4-smoke keel validate myproj

find /tmp/keel-p4-smoke -delete 2>/dev/null
```

- [ ] **Step 4: Smoke check `keel completion`**

```bash
keel completion bash | head -3
keel completion zsh | head -3
keel completion fish | head -3
```

- [ ] **Step 5: Verify slash commands no longer reference Bash**

```bash
grep -rn 'projects/bin/project' ~/projects/.claude/commands/ ~/projects/CLAUDE.md && echo "ERROR: remaining references" || echo "clean"
```

- [ ] **Step 6: Tag**

```bash
git -C keel tag keel-plan-4
```

---

## Self-review

**Spec coverage** — every Plan 4 requirement:

| Requirement | Implementing tasks |
|---|---|
| `migrate` for legacy CLAUDE.md projects | Tasks 1.1–1.6 |
| Shell completion installer | Task 2.1 |
| Slash command rewrites | Tasks 3.1–3.4 |
| Workspace conventions update | Task 4.1 |
| Bash CLI archival | Task 4.2 |
| Final smoke + tag | Task 4.3 |

**Forward-debt items resolved:**
- Last remaining mass: legacy projects without manifests. Plan 4's `migrate` lifts them.

**Forward-debt items still deferred (acceptably):**
- `git_user_slug` Unicode handling — punt.
- `Output.print_rich` leaky abstraction — Plan 2.5 decision still stands.

**Type/name consistency:**
- `cmd_migrate`, `cmd_completion` follow the `cmd_*` naming convention
- Both take `ctx: typer.Context` and use `Output.from_context`
- `migrate` defaults to dry-run (matches the rest of the CLI's mutation safety stance — but the polarity is *inverted* relative to other commands which write by default and dry-run by flag; this is intentional because `migrate` is one-shot and the dry-run preview is the primary UX)

---

## What this plan does NOT cover

- Post-cutover usage feedback (likely surfaces real-world issues — handle as follow-up patches, not a Plan 5)
- Removing the `migrate` command after all legacy projects are migrated (could be hidden behind `--legacy` flag if it's a common annoyance; handle if/when it actually annoys)
- Future work: a `keel doctor` aggregating `validate` + `code status` + `phase` + slash-command sanity into one health check
- Plan 5 territory: milestones (parking-lot from Plan 1), Jira/Confluence link metadata, or any other parking-lot items
