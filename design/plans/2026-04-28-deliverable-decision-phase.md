# Plan 2: Deliverable, Decision, Phase Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the deliverable, decision, and phase command surfaces to keel, plus the structural restructure of `commands/` into per-group subpackages and the Plan 1 hardening items called out in the foundation review.

**Architecture:** Three new command groups (`deliverable`, `decision`) and one new top-level command (`phase`), all auto-scoping by CWD per A1, all with `--json` and (where mutating) `--dry-run`. Cross-file mutations (parent CLAUDE.md / design.md, sibling deliverable CLAUDE.md files) use the AST helpers from Plan 1. A short structural-prep milestone restructures `commands/` into subpackages (the pattern Plan 2's groups need) and closes the test gaps + the `replace_section` blank-line stability the foundation review flagged.

**Tech Stack:** Same as Plan 1 — Python 3.11+, Typer, Rich, Pydantic v2, markdown-it-py, Jinja2, tomlkit, questionary, pytest.

---

## Pre-decided open questions

These were left open in the foundation plan or flagged as forward debt; settled here.

1. **Subpackage layout for command groups**: each group is a Typer subapp registered via `app.add_typer(group_app, name="...")`. Module per command inside the group. Existing top-level commands (`new`, `list_cmd`, `show`) stay where they are; only the new groups add subpackage hierarchy. Existing `commands/list_cmd.py` is renamed to `commands/list.py` for consistency now that `commands/` has more than one type of file.
2. **`detect_scope` strictness**: `detect_scope` continues to return a `Scope` based on path structure only (cheap, no I/O). New helper `resolve_scope_or_fail` in `workspace.py` validates manifest existence and is what command implementations call when they need a *known-good* scope.
3. **`git_user_slug` Unicode**: deferred. Workspace contributors are ASCII-named today; tighten when a non-ASCII contributor surfaces. Recorded in the existing decisions/ file.
4. **`replace_section` blank-line behavior**: fix here as part of M1 — normalize so re-applying the same body produces identical output (idempotency for the `code` regen path that lands in Plan 3).
5. **`scope.md` at deliverable level**: opt-in (per the spec). `deliverable add` does NOT create scope.md by default; the user runs `/write-scope` from inside the deliverable's `design/` directory if they need one.

---

## File Structure

After Plan 2 lands:

```
~/projects/keel/
└── src/keel/
    ├── ...                          # foundation modules unchanged
    ├── workspace.py                 # MODIFY — add resolve_scope_or_fail, deliverable_exists
    ├── markdown_edit.py             # MODIFY — fix replace_section blank-line normalization
    ├── output.py                    # unchanged
    └── commands/
        ├── __init__.py              # unchanged
        ├── new.py                   # unchanged
        ├── list.py                  # RENAME from list_cmd.py
        ├── show.py                  # unchanged
        ├── phase.py                 # CREATE — Plan 2 (single command, not a group)
        ├── deliverable/             # CREATE — Plan 2 group
        │   ├── __init__.py          # creates Typer subapp + registers commands
        │   ├── add.py
        │   ├── rm.py
        │   ├── rename.py
        │   └── list.py
        └── decision/                # CREATE — Plan 2 group
            ├── __init__.py
            ├── new.py
            ├── list.py
            ├── show.py
            └── rm.py

tests/
├── ...
├── conftest.py                      # MODIFY — add make_deliverable, make_decision fixtures
├── commands/
│   ├── test_list.py                 # already there (covers `keel list`)
│   ├── test_new.py
│   ├── test_show.py
│   ├── test_phase.py                # CREATE
│   ├── deliverable/                 # CREATE
│   │   ├── __init__.py
│   │   ├── test_add.py
│   │   ├── test_rm.py
│   │   ├── test_rename.py
│   │   └── test_list.py
│   └── decision/                    # CREATE
│       ├── __init__.py
│       ├── test_new.py
│       ├── test_list.py
│       ├── test_show.py
│       └── test_rm.py
└── test_workspace.py                # MODIFY — add tests for resolve_scope_or_fail
```

---

## Pre-requisites

- Plan 1 (foundation) is complete and `keel-foundation` (or current main) tests are passing.
- Working dir for code: `keel/`. Git root: `~/projects/`. Branch: `main` (continuing the session pattern).
- Run tests with: `cd ~/projects/keel && uv run --extra dev pytest`.

---

## Milestone 1: Structural prep + Plan 1 hardening

### Task 1.1: Rename `commands/list_cmd.py` to `commands/list.py`

**Files:**
- Rename: `src/keel/commands/list_cmd.py` → `src/keel/commands/list.py`
- Modify: `src/keel/app.py` (update import)

- [ ] **Step 1: Move the file**

```bash
cd ~/projects/keel
git mv src/keel/commands/list_cmd.py src/keel/commands/list.py
```

- [ ] **Step 2: Update `src/keel/app.py`**

Find the line `from keel.commands.list_cmd import cmd_list` and replace with `from keel.commands.list import cmd_list`. The full import block at the bottom of `app.py` should now read:

```python
from keel.commands.new import cmd_new
app.command(name="new")(cmd_new)

from keel.commands.list import cmd_list
app.command(name="list")(cmd_list)

from keel.commands.show import cmd_show
app.command(name="show")(cmd_show)
```

- [ ] **Step 3: Run tests to confirm nothing broke**

Run: `uv run --extra dev pytest`
Expected: 83 PASS.

- [ ] **Step 4: Commit**

```bash
git add keel/src/keel/commands/list.py keel/src/keel/commands/list_cmd.py keel/src/keel/app.py
git commit -m "refactor(keel): rename commands/list_cmd.py to list.py"
```

---

### Task 1.2: Fix `replace_section` blank-line normalization

**Files:**
- Modify: `src/keel/markdown_edit.py`
- Modify: `tests/test_markdown_edit.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_markdown_edit.py`:

```python
def test_replace_section_is_idempotent_on_re_apply() -> None:
    """Re-applying the same body produces identical output (no whitespace drift)."""
    text = """# Title

Intro.

## Section A

- existing item
"""
    once = replace_section(text, "Section A", "- new item\n")
    twice = replace_section(once, "Section A", "- new item\n")
    assert once == twice


def test_replace_section_preserves_blank_line_before_next_heading() -> None:
    """After replacement, there's exactly one blank line between body and next heading."""
    text = """# Title

## A

- old

## B

content
"""
    out = replace_section(text, "A", "- new\n")
    assert "## A\n- new\n" in out or "## A\n\n- new\n" in out
    # Crucially: no triple-newline before "## B"
    assert "\n\n\n## B" not in out


def test_replace_section_appends_with_consistent_spacing() -> None:
    """When the section doesn't exist, the appended section is well-spaced."""
    text = "# Title\n\n## A\n- a\n"
    out = replace_section(text, "B", "- b\n")
    # Existing "## A" body intact:
    assert "## A\n- a\n" in out
    # New "## B" appended with at most one blank line before it:
    assert "\n## B\n- b\n" in out
    assert "\n\n\n## B" not in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_markdown_edit.py -v`
Expected: 3 NEW tests fail (current implementation has the blank-line drift the foundation review flagged).

- [ ] **Step 3: Replace the body of `replace_section` in `src/keel/markdown_edit.py`**

Find the existing `replace_section` and replace with:

```python
def replace_section(text: str, title: str, new_body: str) -> str:
    """Replace the body of a section. If the section doesn't exist, append it.

    Output normalization: the body of the named section is exactly `new_body`
    surrounded by exactly one blank line before the next same-or-higher heading
    (or, at end-of-file, by the existing trailing newline). Re-applying the
    same body produces identical output.
    """
    new_body = _ensure_trailing_newline(new_body)
    text = _ensure_trailing_newline(text)
    sections = _find_sections(text)
    target = next((s for s in sections if s.title == title), None)
    if target is None:
        # Append a new section. Ensure exactly one blank line precedes it.
        prefix = text if text.endswith("\n\n") else (text if text.endswith("\n") else text + "\n")
        if not prefix.endswith("\n\n"):
            prefix = prefix + "\n"
        return prefix + f"## {title}\n{new_body}"
    lines = text.splitlines(keepends=True)
    head = lines[:target.body_start]
    tail = lines[target.body_end:]
    # Normalize: head ends with the heading line + a single newline.
    # New body goes in raw, then exactly one blank line before tail (unless tail is empty).
    body = new_body if new_body.endswith("\n") else new_body + "\n"
    if not body.endswith("\n\n") and tail and tail[0].strip():
        body = body + "\n"
    elif body.endswith("\n\n\n"):
        # Trim accidental triple-newline.
        while body.endswith("\n\n\n"):
            body = body[:-1]
    return "".join(head) + body + "".join(tail)
```

- [ ] **Step 4: Run tests to verify all pass**

Run: `uv run --extra dev pytest tests/test_markdown_edit.py -v`
Expected: 11 PASS (8 existing + 3 new).

- [ ] **Step 5: Commit**

```bash
git add keel/src/keel/markdown_edit.py keel/tests/test_markdown_edit.py
git commit -m "fix(keel): normalize replace_section blank-line behavior to be idempotent"
```

---

### Task 1.3: Add `resolve_scope_or_fail` and `deliverable_exists` to `workspace.py`

**Files:**
- Modify: `src/keel/workspace.py`
- Modify: `tests/test_workspace.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_workspace.py`:

```python
def test_resolve_scope_or_fail_returns_existing_project(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PROJECTS_DIR", str(tmp_path))
    (tmp_path / "foo" / "design").mkdir(parents=True)
    (tmp_path / "foo" / "design" / "project.toml").write_text(
        '[project]\nname = "foo"\ndescription = "d"\ncreated = 2026-04-28\n'
    )
    monkeypatch.chdir(tmp_path / "foo" / "design")
    from keel.workspace import resolve_scope_or_fail
    scope = resolve_scope_or_fail()
    assert scope.project == "foo"
    assert scope.deliverable is None


def test_resolve_scope_or_fail_rejects_missing_manifest(monkeypatch, tmp_path) -> None:
    """Path is structurally inside ~/projects/<X>/ but no project.toml there."""
    monkeypatch.setenv("PROJECTS_DIR", str(tmp_path))
    (tmp_path / "ghost" / "design").mkdir(parents=True)  # no project.toml
    monkeypatch.chdir(tmp_path / "ghost" / "design")
    from keel.workspace import resolve_scope_or_fail
    import typer
    with pytest.raises(typer.Exit) as exc:
        resolve_scope_or_fail()
    assert exc.value.exit_code == 1


def test_deliverable_exists_true(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PROJECTS_DIR", str(tmp_path))
    (tmp_path / "foo" / "deliverables" / "bar" / "design").mkdir(parents=True)
    (tmp_path / "foo" / "deliverables" / "bar" / "design" / "deliverable.toml").write_text(
        '[deliverable]\nname = "bar"\nparent_project = "foo"\ndescription = "d"\ncreated = 2026-04-28\nshared_worktree = false\n'
    )
    from keel.workspace import deliverable_exists
    assert deliverable_exists("foo", "bar") is True


def test_deliverable_exists_false(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PROJECTS_DIR", str(tmp_path))
    from keel.workspace import deliverable_exists
    assert deliverable_exists("foo", "bar") is False


def test_resolve_scope_or_fail_returns_deliverable(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PROJECTS_DIR", str(tmp_path))
    proj = tmp_path / "foo" / "deliverables" / "bar" / "design"
    proj.mkdir(parents=True)
    (proj.parent.parent.parent / "design").mkdir(parents=True)
    (proj.parent.parent.parent / "design" / "project.toml").write_text(
        '[project]\nname = "foo"\ndescription = "d"\ncreated = 2026-04-28\n'
    )
    (proj / "deliverable.toml").write_text(
        '[deliverable]\nname = "bar"\nparent_project = "foo"\ndescription = "d"\ncreated = 2026-04-28\nshared_worktree = false\n'
    )
    monkeypatch.chdir(proj)
    from keel.workspace import resolve_scope_or_fail
    scope = resolve_scope_or_fail()
    assert scope.project == "foo"
    assert scope.deliverable == "bar"
```

Add `import pytest` at the top if not already present.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_workspace.py -v`
Expected: 5 NEW tests fail.

- [ ] **Step 3: Add the helpers to `src/keel/workspace.py`**

Append at the end of `workspace.py`:

```python
def deliverable_exists(project_name: str, deliverable_name: str) -> bool:
    """Check whether a deliverable's manifest exists on disk."""
    return (deliverable_dir(project_name, deliverable_name) / "design" / "deliverable.toml").is_file()


def project_exists(project_name: str) -> bool:
    """Check whether a project's manifest exists on disk."""
    return (project_dir(project_name) / "design" / "project.toml").is_file()


def resolve_scope_or_fail(cwd: Path | None = None) -> Scope:
    """Like detect_scope, but verifies the scope's manifests exist on disk.

    Raises typer.Exit(1) with a clear message if:
    - No project is detected from CWD, OR
    - The detected project's manifest doesn't exist, OR
    - The detected deliverable's manifest doesn't exist.
    """
    import typer  # local import to keep workspace.py lightweight when imported in non-CLI contexts
    scope = detect_scope(cwd)
    if scope.project is None:
        typer.echo("error: no project detected from current directory", err=True)
        raise typer.Exit(code=1)
    if not project_exists(scope.project):
        typer.echo(f"error: project not found: {scope.project}", err=True)
        raise typer.Exit(code=1)
    if scope.deliverable is not None and not deliverable_exists(scope.project, scope.deliverable):
        typer.echo(
            f"error: deliverable not found: {scope.project}/{scope.deliverable}",
            err=True,
        )
        raise typer.Exit(code=1)
    return scope
```

- [ ] **Step 4: Run tests to verify all pass**

Run: `uv run --extra dev pytest tests/test_workspace.py -v`
Expected: 13 PASS (8 existing + 5 new).

- [ ] **Step 5: Commit**

```bash
git add keel/src/keel/workspace.py keel/tests/test_workspace.py
git commit -m "feat(keel): add resolve_scope_or_fail and existence checks for scopes"
```

---

### Task 1.4: Close Plan 1 test gaps — `Output.warn`, `confirm_destructive`, `_slugify`

**Files:**
- Modify: `tests/test_output.py`
- Modify: `tests/test_prompts.py`
- Create: `tests/commands/test_slugify.py`

- [ ] **Step 1: Add `Output.warn` test**

Append to `tests/test_output.py`:

```python
def test_warn_goes_to_stderr_with_yellow(capsys) -> None:
    o = Output(quiet=False)
    o.warn("careful now")
    captured = capsys.readouterr()
    assert "careful now" in captured.err
    assert captured.out == ""


def test_warn_suppressed_when_quiet(capsys) -> None:
    o = Output(quiet=True)
    o.warn("careful now")
    assert capsys.readouterr().err == ""
```

- [ ] **Step 2: Add `confirm_destructive` tests**

Append to `tests/test_prompts.py`:

```python
def test_confirm_destructive_skipped_when_yes() -> None:
    from keel.prompts import confirm_destructive
    confirm_destructive("delete?", yes=True)  # no exception, no prompt


def test_confirm_destructive_fails_loud_non_tty(monkeypatch) -> None:
    monkeypatch.setattr("keel.prompts.is_interactive", lambda: False)
    from keel.prompts import confirm_destructive
    import typer
    with pytest.raises(typer.Exit) as exc:
        confirm_destructive("delete?", yes=False)
    assert exc.value.exit_code == 1


def test_confirm_destructive_decline_exits(monkeypatch) -> None:
    monkeypatch.setattr("keel.prompts.is_interactive", lambda: True)
    class _Q:
        def unsafe_ask(self):
            return False
    monkeypatch.setattr("questionary.confirm", lambda *a, **kw: _Q())
    from keel.prompts import confirm_destructive
    import typer
    with pytest.raises(typer.Exit) as exc:
        confirm_destructive("delete?", yes=False)
    assert exc.value.exit_code == 1


def test_confirm_destructive_accept_returns(monkeypatch) -> None:
    monkeypatch.setattr("keel.prompts.is_interactive", lambda: True)
    class _Q:
        def unsafe_ask(self):
            return True
    monkeypatch.setattr("questionary.confirm", lambda *a, **kw: _Q())
    from keel.prompts import confirm_destructive
    confirm_destructive("delete?", yes=False)  # returns None on accept
```

- [ ] **Step 3: Add `_slugify` edge-case tests**

Create `tests/commands/test_slugify.py`:

```python
"""Edge-case coverage for the slugifier used by `keel new`."""
import pytest
from keel.commands.new import _slugify


def test_slugify_lowercases_and_replaces_spaces() -> None:
    assert _slugify("Foo Bar") == "foo-bar"


def test_slugify_strips_specials() -> None:
    assert _slugify("foo!@#bar") == "foobar"


def test_slugify_empty_input() -> None:
    assert _slugify("") == ""


def test_slugify_whitespace_only() -> None:
    assert _slugify("   ") == ""


def test_slugify_all_specials() -> None:
    assert _slugify("!@#$%") == ""


def test_slugify_unicode_dropped() -> None:
    """Current behavior: non-ASCII characters are stripped silently."""
    assert _slugify("café") == "caf"


def test_slugify_leading_trailing_spaces_trimmed() -> None:
    assert _slugify("  hello  ") == "hello"


def test_slugify_keeps_existing_dashes() -> None:
    assert _slugify("a-b-c") == "a-b-c"
```

- [ ] **Step 4: Run tests to verify all pass**

Run: `uv run --extra dev pytest tests/test_output.py tests/test_prompts.py tests/commands/test_slugify.py -v`
Expected: 17 PASS (8 + 9 = 17 new tests on top of existing).

- [ ] **Step 5: Commit**

```bash
git add keel/tests/test_output.py keel/tests/test_prompts.py keel/tests/commands/test_slugify.py
git commit -m "test(keel): close Plan 1 test gaps (warn, confirm_destructive, _slugify)"
```

---

## Milestone 2: Deliverable group

### Task 2.1: Create `commands/deliverable/` subpackage scaffold

**Files:**
- Create: `src/keel/commands/deliverable/__init__.py`
- Create: `tests/commands/deliverable/__init__.py`
- Modify: `src/keel/app.py` (register the deliverable subapp)

- [ ] **Step 1: Create `src/keel/commands/deliverable/__init__.py`**

```python
"""`keel deliverable ...` command group."""
from __future__ import annotations
import typer

app = typer.Typer(
    name="deliverable",
    help="Manage deliverables (mini-projects nested under a project).",
    no_args_is_help=True,
)
```

- [ ] **Step 2: Create `tests/commands/deliverable/__init__.py`** (empty file)

```python
```

- [ ] **Step 3: Register the subapp in `src/keel/app.py`**

Append to `src/keel/app.py`:

```python
from keel.commands.deliverable import app as deliverable_app
app.add_typer(deliverable_app, name="deliverable")
```

- [ ] **Step 4: Smoke check**

Run:
```bash
uv tool install --editable .
keel deliverable --help
```
Expected: shows `Manage deliverables (...)` help text with no subcommands yet.

- [ ] **Step 5: Run full suite**

Run: `uv run --extra dev pytest`
Expected: 100 PASS (83 + 17 from Task 1.4).

- [ ] **Step 6: Commit**

```bash
git add keel/src/keel/commands/deliverable/ keel/tests/commands/deliverable/ keel/src/keel/app.py
git commit -m "feat(keel): scaffold deliverable command group"
```

---

### Task 2.2: Add `make_deliverable` test fixture

**Files:**
- Modify: `tests/conftest.py`

- [ ] **Step 1: Add the fixture**

Append to `tests/conftest.py`:

```python
from keel.manifest import (
    DeliverableManifest, DeliverableMeta,
    save_deliverable_manifest,
)


@pytest.fixture
def make_deliverable(make_project) -> Callable[..., Path]:
    """Factory: create a deliverable inside a (possibly new) project.

    Usage:
        deliverable = make_deliverable(project_name="foo", name="bar",
                                        description="the bar")
    """
    def _make(
        project_name: str = "foo",
        name: str = "bar",
        description: str = "test deliverable",
        shared_worktree: bool = False,
    ) -> Path:
        # Ensure the parent project exists.
        proj = make_project(project_name) if not (
            (Path.home() / "projects" / project_name / "design" / "project.toml").exists()
            or False  # actual check happens via fixtures' isolation
        ) else None
        # The above is over-careful; simplify: always make the project if not present.
        from keel import workspace
        if not workspace.project_exists(project_name):
            make_project(project_name)
        deliv = workspace.deliverable_dir(project_name, name)
        (deliv / "design" / "decisions").mkdir(parents=True)
        from datetime import date as _date
        m = DeliverableManifest(
            deliverable=DeliverableMeta(
                name=name,
                parent_project=project_name,
                description=description,
                created=_date(2026, 4, 28),
                shared_worktree=shared_worktree,
            ),
            repos=[],
        )
        save_deliverable_manifest(deliv / "design" / "deliverable.toml", m)
        (deliv / "design" / ".phase").write_text("scoping\n")
        return deliv
    return _make
```

- [ ] **Step 2: Verify the fixture imports cleanly**

Run: `uv run --extra dev pytest tests/conftest.py -v` (collects and reports no errors)
Expected: pytest collects fine; no test failures.

- [ ] **Step 3: Commit**

```bash
git add keel/tests/conftest.py
git commit -m "test(keel): add make_deliverable fixture for deliverable commands"
```

---

### Task 2.3: `deliverable add` — basic flow without parent updates

**Files:**
- Create: `src/keel/commands/deliverable/add.py`
- Create: `tests/commands/deliverable/test_add.py`
- Modify: `src/keel/commands/deliverable/__init__.py` (register `add`)

- [ ] **Step 1: Write failing tests**

Create `tests/commands/deliverable/test_add.py`:

```python
"""Tests for `keel deliverable add`."""
from typer.testing import CliRunner
from keel.app import app
from keel.manifest import load_deliverable_manifest

runner = CliRunner()


def test_add_creates_deliverable_design_dir(projects, make_project) -> None:
    make_project("foo")
    result = runner.invoke(
        app,
        ["deliverable", "add", "bar", "-d", "the bar deliverable", "-y", "--project", "foo"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.stderr
    deliv = projects / "foo" / "deliverables" / "bar"
    assert (deliv / "design" / "deliverable.toml").is_file()
    assert (deliv / "design" / "design.md").is_file()
    assert (deliv / "design" / "CLAUDE.md").is_file()
    assert (deliv / "design" / ".phase").read_text().splitlines()[0] == "scoping"
    # No scope.md by default (opt-in):
    assert not (deliv / "design" / "scope.md").exists()


def test_add_writes_valid_manifest(projects, make_project) -> None:
    make_project("foo")
    runner.invoke(app, ["deliverable", "add", "bar", "-d", "d", "-y", "--project", "foo"])
    m = load_deliverable_manifest(projects / "foo" / "deliverables" / "bar" / "design" / "deliverable.toml")
    assert m.deliverable.name == "bar"
    assert m.deliverable.parent_project == "foo"
    assert m.deliverable.shared_worktree is False
    assert m.repos == []


def test_add_fails_if_deliverable_exists(projects, make_project) -> None:
    make_project("foo")
    runner.invoke(app, ["deliverable", "add", "bar", "-d", "d", "-y", "--project", "foo"])
    result = runner.invoke(app, ["deliverable", "add", "bar", "-d", "d", "-y", "--project", "foo"])
    assert result.exit_code == 1
    assert "already exists" in result.stderr.lower()


def test_add_fails_if_parent_project_missing(projects) -> None:
    result = runner.invoke(app, ["deliverable", "add", "bar", "-d", "d", "-y", "--project", "ghost"])
    assert result.exit_code == 1
    assert "ghost" in result.stderr.lower()
```

- [ ] **Step 2: Run tests, expect FAIL**

Run: `uv run --extra dev pytest tests/commands/deliverable/test_add.py -v`
Expected: collection error (`add` not registered yet).

- [ ] **Step 3: Implement `src/keel/commands/deliverable/add.py`**

```python
"""`keel deliverable add <name>`."""
from __future__ import annotations
from datetime import date
from pathlib import Path
import re
import typer

from keel import templates, workspace
from keel.manifest import (
    DeliverableManifest, DeliverableMeta,
    save_deliverable_manifest,
)
from keel.output import Output
from keel.prompts import require_or_fail


_SLUG_RE = re.compile(r"[^a-z0-9-]+")


def _slugify(name: str) -> str:
    s = name.lower().strip().replace(" ", "-")
    return _SLUG_RE.sub("", s)


def cmd_add(
    name: str = typer.Argument(..., help="Deliverable name (will be slugified)."),
    description: str | None = typer.Option(None, "-d", "--description"),
    project: str | None = typer.Option(None, "--project", "-p", help="Parent project (auto-detected from CWD)."),
    repo: str | None = typer.Option(None, "-r", "--repo", help="Source repo for the deliverable's worktree."),
    shared: bool = typer.Option(False, "--shared", help="Share parent's worktree (no own [[repos]])."),
    dry_run: bool = typer.Option(False, "--dry-run"),
    yes: bool = typer.Option(False, "-y", "--yes"),
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    """Create a new deliverable inside a project."""
    out = Output(json_mode=json_mode)

    # Determine parent project: explicit --project overrides; else CWD-detect; else fail.
    if project is None:
        scope = workspace.detect_scope()
        project = scope.project
    if project is None:
        out.error("no parent project specified and none detected from CWD", code="no_project")
        raise typer.Exit(code=1)
    if not workspace.project_exists(project):
        out.error(f"parent project not found: {project}", code="not_found")
        raise typer.Exit(code=1)

    slug = _slugify(name)
    if not slug:
        out.error("invalid deliverable name", code="invalid_name")
        raise typer.Exit(code=2)

    deliv = workspace.deliverable_dir(project, slug)
    if deliv.exists():
        out.error(f"deliverable already exists: {deliv}", code="exists")
        raise typer.Exit(code=1)

    description = require_or_fail(description, arg_name="--description", label="Description")

    if dry_run:
        from keel.dryrun import OpLog
        log = OpLog()
        log.create_file(deliv / "design" / "deliverable.toml", size=0)
        log.create_file(deliv / "design" / "CLAUDE.md", size=0)
        log.create_file(deliv / "design" / "design.md", size=0)
        log.create_file(deliv / "design" / ".phase", size=0)
        today = date.today().isoformat()
        log.create_file(deliv / "design" / "decisions" / f"{today}-deliverable-created.md", size=0)
        out.info(log.format_summary())
        return

    # Create directories
    (deliv / "design" / "decisions").mkdir(parents=True)

    # Manifest
    manifest = DeliverableManifest(
        deliverable=DeliverableMeta(
            name=slug,
            parent_project=project,
            description=description,
            created=date.today(),
            shared_worktree=shared,
        ),
        repos=[],
    )
    save_deliverable_manifest(deliv / "design" / "deliverable.toml", manifest)

    # Templates
    (deliv / "design" / "CLAUDE.md").write_text(
        templates.render("claude_md.j2", name=slug, description=description, repos=[], deliverables=[])
    )
    (deliv / "design" / "design.md").write_text(
        templates.render("design_md.j2", name=slug, description=description)
    )

    # Phase
    (deliv / "design" / ".phase").write_text("scoping\n")

    # Initial decision
    today = date.today().isoformat()
    (deliv / "design" / "decisions" / f"{today}-deliverable-created.md").write_text(
        templates.render("decision_entry.j2", date=today, title=f"Create deliverable {slug}")
    )

    out.info(f"Created deliverable: {deliv}")
    out.result(
        {"deliverable_path": str(deliv), "modified_files": []},
        human_text=f"Deliverable created: {deliv}",
    )
```

- [ ] **Step 4: Register in `src/keel/commands/deliverable/__init__.py`**

Replace the file contents with:

```python
"""`keel deliverable ...` command group."""
from __future__ import annotations
import typer

app = typer.Typer(
    name="deliverable",
    help="Manage deliverables (mini-projects nested under a project).",
    no_args_is_help=True,
)

from keel.commands.deliverable.add import cmd_add
app.command(name="add")(cmd_add)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run --extra dev pytest tests/commands/deliverable/test_add.py -v`
Expected: 4 PASS.

- [ ] **Step 6: Commit**

```bash
git add keel/src/keel/commands/deliverable/add.py keel/src/keel/commands/deliverable/__init__.py keel/tests/commands/deliverable/test_add.py
git commit -m "feat(keel): implement 'deliverable add' basic flow"
```

---

### Task 2.4: `deliverable add` — AST-edit parent CLAUDE.md and design.md

**Files:**
- Modify: `src/keel/commands/deliverable/add.py`
- Modify: `tests/commands/deliverable/test_add.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/commands/deliverable/test_add.py`:

```python
def test_add_inserts_into_parent_claude_md(projects, make_project) -> None:
    make_project("foo")
    runner.invoke(app, ["deliverable", "add", "bar", "-d", "the bar", "-y", "--project", "foo"])
    parent_claude = (projects / "foo" / "design" / "CLAUDE.md").read_text()
    assert "## Deliverables" in parent_claude
    assert "bar" in parent_claude
    assert "the bar" in parent_claude


def test_add_inserts_into_parent_design_md(projects, make_project) -> None:
    make_project("foo")
    runner.invoke(app, ["deliverable", "add", "bar", "-d", "the bar", "-y", "--project", "foo"])
    parent_design = (projects / "foo" / "design" / "design.md").read_text()
    assert "## Deliverables" in parent_design
    assert "bar" in parent_design


def test_add_is_idempotent_in_parent_files(projects, make_project) -> None:
    """Adding the same deliverable twice doesn't duplicate the parent line.

    (We can't add twice via the command — it'll fail with 'already exists' —
    but the AST helper's idempotency means hand-editing won't double-up either.
    Verify by checking the parent's deliverables list contains exactly one
    'bar' entry.)
    """
    make_project("foo")
    runner.invoke(app, ["deliverable", "add", "bar", "-d", "d", "-y", "--project", "foo"])
    parent_claude = (projects / "foo" / "design" / "CLAUDE.md").read_text()
    # Count occurrences of the deliverable bullet line:
    assert parent_claude.count("**bar**") == 1
```

- [ ] **Step 2: Run tests, expect 3 FAIL**

Run: `uv run --extra dev pytest tests/commands/deliverable/test_add.py::test_add_inserts_into_parent_claude_md tests/commands/deliverable/test_add.py::test_add_inserts_into_parent_design_md tests/commands/deliverable/test_add.py::test_add_is_idempotent_in_parent_files -v`
Expected: 3 FAIL.

- [ ] **Step 3: Add parent-file mutation to `cmd_add`**

In `src/keel/commands/deliverable/add.py`, after the line `out.info(f"Created deliverable: {deliv}")` (or just before the `out.result(...)` call), insert:

```python
    # AST-edit the parent's CLAUDE.md to list this deliverable
    from keel.markdown_edit import insert_under_heading
    parent_claude_path = workspace.project_dir(project) / "design" / "CLAUDE.md"
    if parent_claude_path.is_file():
        line = f"- **{slug}**: ../deliverables/{slug}/design/ -- {description}\n"
        new_text = insert_under_heading(parent_claude_path.read_text(), "Deliverables", line)
        parent_claude_path.write_text(new_text)

    # AST-edit the parent's design.md
    parent_design_path = workspace.project_dir(project) / "design" / "design.md"
    if parent_design_path.is_file():
        line = f"- **{slug}**: {description}. See [design](../deliverables/{slug}/design/design.md).\n"
        new_text = insert_under_heading(parent_design_path.read_text(), "Deliverables", line)
        parent_design_path.write_text(new_text)
```

Also update the result payload to include modified files:

```python
    modified_files = []
    if parent_claude_path.is_file():
        modified_files.append(str(parent_claude_path))
    if parent_design_path.is_file():
        modified_files.append(str(parent_design_path))
    out.result(
        {"deliverable_path": str(deliv), "modified_files": modified_files},
        human_text=f"Deliverable created: {deliv}",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --extra dev pytest tests/commands/deliverable/test_add.py -v`
Expected: 7 PASS (4 + 3).

- [ ] **Step 5: Commit**

```bash
git add keel/src/keel/commands/deliverable/add.py keel/tests/commands/deliverable/test_add.py
git commit -m "feat(keel): 'deliverable add' AST-edits parent CLAUDE.md and design.md"
```

---

### Task 2.5: `deliverable add` — sibling deliverable updates

**Files:**
- Modify: `src/keel/commands/deliverable/add.py`
- Modify: `tests/commands/deliverable/test_add.py`

- [ ] **Step 1: Write failing test**

Append to `test_add.py`:

```python
def test_add_updates_sibling_deliverable_claude_md(projects, make_project, make_deliverable) -> None:
    """Adding a new deliverable updates existing siblings' CLAUDE.md."""
    make_deliverable(project_name="foo", name="alpha", description="alpha thing")
    runner.invoke(app, ["deliverable", "add", "beta", "-d", "beta thing", "-y", "--project", "foo"])
    sibling_claude = (projects / "foo" / "deliverables" / "alpha" / "design" / "CLAUDE.md").read_text()
    assert "beta" in sibling_claude
```

Note: `make_deliverable` doesn't currently render a CLAUDE.md with a Sibling deliverables section — this test will likely fail because the fixture skips template rendering. Either update the fixture to render the template, OR update this test to assert on a fresh deliverable created via the command.

Use this version instead — it adds two via the command itself:

```python
def test_add_updates_sibling_deliverable_claude_md(projects, make_project) -> None:
    """Adding a second deliverable updates the first's CLAUDE.md sibling section."""
    make_project("foo")
    runner.invoke(app, ["deliverable", "add", "alpha", "-d", "alpha thing", "-y", "--project", "foo"])
    runner.invoke(app, ["deliverable", "add", "beta", "-d", "beta thing", "-y", "--project", "foo"])
    sibling_claude = (projects / "foo" / "deliverables" / "alpha" / "design" / "CLAUDE.md").read_text()
    # alpha's CLAUDE.md should mention beta (under "Sibling deliverables" or similar):
    assert "beta" in sibling_claude
```

This requires the deliverable's CLAUDE.md to have a "Sibling deliverables" section (possibly empty initially). Update the `claude_md.j2` template to optionally include that — see the next step.

- [ ] **Step 2: Run test, expect FAIL**

Run: `uv run --extra dev pytest tests/commands/deliverable/test_add.py::test_add_updates_sibling_deliverable_claude_md -v`
Expected: FAIL.

- [ ] **Step 3: Update `claude_md.j2` to support a Sibling deliverables section for deliverables**

Modify `src/keel/_templates/claude_md.j2` to include an optional `## Sibling deliverables` section when rendering for a deliverable. Add at the end of the conditional sections (before `## Workflow`):

```jinja
{% if siblings is defined %}

## Sibling deliverables

{% for s in siblings -%}
- {{ s.name }}: ../{{ s.name }}/design/ -- {{ s.description }}
{% endfor %}

{% endif -%}
```

When rendered for a project, `siblings` is undefined and the block emits nothing. When rendered for a deliverable, pass `siblings=[]` (initially empty) to scaffold the section.

- [ ] **Step 4: Update `cmd_add` to render with `siblings=[]` and to update existing siblings on add**

In `src/keel/commands/deliverable/add.py`, change the deliverable's CLAUDE.md render to pass `siblings=[]`:

```python
    (deliv / "design" / "CLAUDE.md").write_text(
        templates.render("claude_md.j2", name=slug, description=description, repos=[], deliverables=[], siblings=[])
    )
```

Then, after the parent-file mutation block, add sibling updates:

```python
    # AST-edit existing siblings' CLAUDE.md to add this new deliverable
    siblings_dir = workspace.project_dir(project) / "deliverables"
    sibling_modifications = []
    if siblings_dir.is_dir():
        for sibling in sorted(siblings_dir.iterdir()):
            if sibling.name == slug or not sibling.is_dir():
                continue
            sibling_claude = sibling / "design" / "CLAUDE.md"
            if sibling_claude.is_file():
                line = f"- {slug}: ../{slug}/design/ -- {description}\n"
                new_text = insert_under_heading(sibling_claude.read_text(), "Sibling deliverables", line)
                sibling_claude.write_text(new_text)
                sibling_modifications.append(str(sibling_claude))
    modified_files.extend(sibling_modifications)
```

- [ ] **Step 5: Run tests to verify all pass**

Run: `uv run --extra dev pytest tests/commands/deliverable/test_add.py -v`
Expected: 8 PASS.

- [ ] **Step 6: Commit**

```bash
git add keel/src/keel/_templates/claude_md.j2 keel/src/keel/commands/deliverable/add.py keel/tests/commands/deliverable/test_add.py
git commit -m "feat(keel): 'deliverable add' updates sibling deliverable CLAUDE.md files"
```

---

### Task 2.6: `deliverable list`

**Files:**
- Create: `src/keel/commands/deliverable/list.py`
- Create: `tests/commands/deliverable/test_list.py`
- Modify: `src/keel/commands/deliverable/__init__.py`

- [ ] **Step 1: Write failing tests**

Create `tests/commands/deliverable/test_list.py`:

```python
"""Tests for `keel deliverable list`."""
import json
from typer.testing import CliRunner
from keel.app import app

runner = CliRunner()


def test_list_empty(projects, make_project) -> None:
    make_project("foo")
    result = runner.invoke(app, ["deliverable", "list", "--project", "foo"])
    assert result.exit_code == 0
    # Empty output or "(no deliverables)" — accept either.
    assert "no deliverables" in result.stdout.lower() or result.stdout.strip() == ""


def test_list_one_deliverable(projects, make_project, make_deliverable) -> None:
    make_deliverable(project_name="foo", name="bar", description="the bar")
    result = runner.invoke(app, ["deliverable", "list", "--project", "foo"])
    assert result.exit_code == 0
    assert "bar" in result.stdout


def test_list_json_shape(projects, make_project, make_deliverable) -> None:
    make_deliverable(project_name="foo", name="bar", description="the bar")
    result = runner.invoke(app, ["deliverable", "list", "--project", "foo", "--json"])
    payload = json.loads(result.stdout)
    assert "deliverables" in payload
    assert payload["deliverables"][0]["name"] == "bar"
    assert payload["deliverables"][0]["phase"] == "scoping"
    assert payload["deliverables"][0]["description"] == "the bar"


def test_list_auto_detects_project_from_cwd(projects, make_project, make_deliverable, monkeypatch) -> None:
    proj = make_deliverable(project_name="foo", name="bar", description="d").parent.parent
    monkeypatch.chdir(proj / "design")
    result = runner.invoke(app, ["deliverable", "list"])
    assert result.exit_code == 0
    assert "bar" in result.stdout
```

- [ ] **Step 2: Run tests, expect FAIL**

Run: `uv run --extra dev pytest tests/commands/deliverable/test_list.py -v`
Expected: collection error (no `list` command yet).

- [ ] **Step 3: Implement `src/keel/commands/deliverable/list.py`**

```python
"""`keel deliverable list`."""
from __future__ import annotations
from dataclasses import dataclass
import typer
from rich.table import Table

from keel import workspace
from keel.manifest import load_deliverable_manifest
from keel.output import Output


@dataclass
class _DeliverableRow:
    name: str
    phase: str
    description: str
    shared_worktree: bool


def _scan(project_name: str) -> list[_DeliverableRow]:
    rows: list[_DeliverableRow] = []
    deliv_dir = workspace.project_dir(project_name) / "deliverables"
    if not deliv_dir.is_dir():
        return rows
    for child in sorted(deliv_dir.iterdir()):
        manifest_path = child / "design" / "deliverable.toml"
        if not manifest_path.is_file():
            continue
        m = load_deliverable_manifest(manifest_path)
        phase_file = child / "design" / ".phase"
        phase = phase_file.read_text().splitlines()[0].strip() if phase_file.is_file() else "scoping"
        rows.append(_DeliverableRow(
            name=m.deliverable.name,
            phase=phase,
            description=m.deliverable.description,
            shared_worktree=m.deliverable.shared_worktree,
        ))
    return rows


def cmd_list(
    project: str | None = typer.Option(None, "--project", "-p"),
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    """List deliverables in a project."""
    out = Output(json_mode=json_mode)
    if project is None:
        scope = workspace.detect_scope()
        project = scope.project
    if project is None:
        out.error("no project specified and none detected from CWD", code="no_project")
        raise typer.Exit(code=1)
    if not workspace.project_exists(project):
        out.error(f"project not found: {project}", code="not_found")
        raise typer.Exit(code=1)

    rows = _scan(project)

    if json_mode:
        out.result({
            "deliverables": [
                {"name": r.name, "phase": r.phase, "description": r.description,
                 "shared_worktree": r.shared_worktree}
                for r in rows
            ]
        })
        return

    if not rows:
        out.result(None, human_text="(no deliverables)")
        return

    table = Table(title=f"Deliverables of {project}")
    table.add_column("Name")
    table.add_column("Phase")
    table.add_column("Shared")
    table.add_column("Description")
    for r in rows:
        table.add_row(r.name, r.phase, "yes" if r.shared_worktree else "no", r.description)
    out.print_rich(table)
```

- [ ] **Step 4: Register in `src/keel/commands/deliverable/__init__.py`**

Append:

```python
from keel.commands.deliverable.list import cmd_list
app.command(name="list")(cmd_list)
```

- [ ] **Step 5: Run tests, expect 4 PASS**

Run: `uv run --extra dev pytest tests/commands/deliverable/test_list.py -v`

- [ ] **Step 6: Commit**

```bash
git add keel/src/keel/commands/deliverable/list.py keel/src/keel/commands/deliverable/__init__.py keel/tests/commands/deliverable/test_list.py
git commit -m "feat(keel): implement 'deliverable list'"
```

---

### Task 2.7: `deliverable rm` — basic flow with confirmation and parent cleanup

**Files:**
- Create: `src/keel/commands/deliverable/rm.py`
- Create: `tests/commands/deliverable/test_rm.py`
- Modify: `src/keel/commands/deliverable/__init__.py`

- [ ] **Step 1: Write failing tests**

Create `tests/commands/deliverable/test_rm.py`:

```python
"""Tests for `keel deliverable rm`."""
from typer.testing import CliRunner
from keel.app import app

runner = CliRunner()


def test_rm_removes_design_dir(projects, make_project, make_deliverable) -> None:
    deliv = make_deliverable(project_name="foo", name="bar", description="d")
    result = runner.invoke(
        app,
        ["deliverable", "rm", "bar", "-y", "--project", "foo"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.stderr
    assert not deliv.exists()


def test_rm_cleans_parent_claude_md(projects, make_project) -> None:
    """After deliverable rm, the parent's CLAUDE.md no longer mentions it."""
    make_project("foo")
    runner.invoke(app, ["deliverable", "add", "bar", "-d", "d", "-y", "--project", "foo"])
    parent_claude = (projects / "foo" / "design" / "CLAUDE.md").read_text()
    assert "bar" in parent_claude  # Sanity: it's there before rm
    runner.invoke(app, ["deliverable", "rm", "bar", "-y", "--project", "foo"])
    parent_claude_after = (projects / "foo" / "design" / "CLAUDE.md").read_text()
    # The deliverable line is removed (not the heading itself necessarily):
    assert "**bar**" not in parent_claude_after


def test_rm_fails_for_unknown_deliverable(projects, make_project) -> None:
    make_project("foo")
    result = runner.invoke(app, ["deliverable", "rm", "ghost", "-y", "--project", "foo"])
    assert result.exit_code == 1
    assert "ghost" in result.stderr.lower()


def test_rm_dry_run_writes_nothing(projects, make_project, make_deliverable) -> None:
    deliv = make_deliverable(project_name="foo", name="bar", description="d")
    result = runner.invoke(app, ["deliverable", "rm", "bar", "-y", "--project", "foo", "--dry-run"])
    assert result.exit_code == 0
    assert deliv.exists()  # not actually removed
    assert "[dry-run]" in result.stderr
```

- [ ] **Step 2: Run tests, expect FAIL**

Run: `uv run --extra dev pytest tests/commands/deliverable/test_rm.py -v`
Expected: collection error.

- [ ] **Step 3: Implement `src/keel/commands/deliverable/rm.py`**

```python
"""`keel deliverable rm <name>`."""
from __future__ import annotations
import shutil
import typer

from keel import workspace
from keel.markdown_edit import remove_line_under_heading
from keel.output import Output
from keel.prompts import confirm_destructive


def cmd_rm(
    name: str = typer.Argument(...),
    project: str | None = typer.Option(None, "--project", "-p"),
    keep_code: bool = typer.Option(False, "--keep-code"),
    keep_design: bool = typer.Option(False, "--keep-design"),
    force: bool = typer.Option(False, "--force", help="Allow even if worktree is dirty."),
    yes: bool = typer.Option(False, "-y", "--yes"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    """Remove a deliverable, including its design dir, worktree, and parent references."""
    out = Output(json_mode=json_mode)

    if project is None:
        scope = workspace.detect_scope()
        project = scope.project
    if project is None:
        out.error("no project specified and none detected from CWD", code="no_project")
        raise typer.Exit(code=1)
    if not workspace.deliverable_exists(project, name):
        out.error(f"deliverable not found: {project}/{name}", code="not_found")
        raise typer.Exit(code=1)

    deliv = workspace.deliverable_dir(project, name)

    if dry_run:
        from keel.dryrun import OpLog
        log = OpLog()
        if not keep_design:
            log.delete_file(deliv)
        log.modify_file(
            workspace.project_dir(project) / "design" / "CLAUDE.md",
            diff=f"- - **{name}**: ...",
        )
        log.modify_file(
            workspace.project_dir(project) / "design" / "design.md",
            diff=f"- - **{name}**: ...",
        )
        out.info(log.format_summary())
        return

    confirm_destructive(
        f"Remove deliverable {project}/{name}? This deletes its design dir.",
        yes=yes,
    )

    # Remove design dir
    if not keep_design:
        shutil.rmtree(deliv)

    # Clean up parent CLAUDE.md
    parent_claude = workspace.project_dir(project) / "design" / "CLAUDE.md"
    if parent_claude.is_file():
        # Match the format used by `deliverable add`: `- **{name}**: ...`
        text = parent_claude.read_text()
        # Find the line(s) starting with the deliverable bullet and remove them
        new_lines = [
            line for line in text.splitlines(keepends=True)
            if not line.lstrip().startswith(f"- **{name}**:")
        ]
        parent_claude.write_text("".join(new_lines))

    # Clean up parent design.md
    parent_design = workspace.project_dir(project) / "design" / "design.md"
    if parent_design.is_file():
        text = parent_design.read_text()
        new_lines = [
            line for line in text.splitlines(keepends=True)
            if not line.lstrip().startswith(f"- **{name}**:")
        ]
        parent_design.write_text("".join(new_lines))

    # Clean up sibling deliverable CLAUDE.md files
    siblings_dir = workspace.project_dir(project) / "deliverables"
    if siblings_dir.is_dir():
        for sibling in siblings_dir.iterdir():
            if not sibling.is_dir():
                continue
            sibling_claude = sibling / "design" / "CLAUDE.md"
            if sibling_claude.is_file():
                text = sibling_claude.read_text()
                # Sibling lines look like: `- {name}: ../{name}/design/ -- description`
                new_lines = [
                    line for line in text.splitlines(keepends=True)
                    if not line.lstrip().startswith(f"- {name}:")
                ]
                sibling_claude.write_text("".join(new_lines))

    out.info(f"Removed deliverable: {deliv}")
    out.result({"removed": str(deliv)}, human_text=f"Deliverable removed: {deliv}")
```

- [ ] **Step 4: Register in `__init__.py`**

```python
from keel.commands.deliverable.rm import cmd_rm
app.command(name="rm")(cmd_rm)
```

- [ ] **Step 5: Run tests**

Run: `uv run --extra dev pytest tests/commands/deliverable/test_rm.py -v`
Expected: 4 PASS.

- [ ] **Step 6: Commit**

```bash
git add keel/src/keel/commands/deliverable/rm.py keel/src/keel/commands/deliverable/__init__.py keel/tests/commands/deliverable/test_rm.py
git commit -m "feat(keel): implement 'deliverable rm' with parent and sibling cleanup"
```

---

### Task 2.8: `deliverable rm` — handle worktree

**Files:**
- Modify: `src/keel/commands/deliverable/rm.py`
- Modify: `tests/commands/deliverable/test_rm.py`

- [ ] **Step 1: Write failing test**

Append to `test_rm.py`:

```python
def test_rm_removes_worktree_when_present(projects, make_project, source_repo) -> None:
    """If the deliverable was created with --repo, rm removes its worktree."""
    make_project("foo")
    runner.invoke(
        app,
        ["deliverable", "add", "bar", "-d", "d", "-y", "--project", "foo", "-r", str(source_repo)],
    )
    deliv = projects / "foo" / "deliverables" / "bar"
    # After Plan 2 Task 2.9 lands, --repo creates the worktree at deliv/code/
    # For now the test assumes that's wired; if not, mark xfail.
    assert (deliv / "code").is_dir() or True  # tolerant until 2.9
    runner.invoke(app, ["deliverable", "rm", "bar", "-y", "--project", "foo"])
    assert not deliv.exists()
```

Note: this test is forward-looking — `deliverable add --repo` lands in Task 2.9. Mark this test `@pytest.mark.skip(reason="depends on Task 2.9")` for now and unskip it when 2.9 ships. OR: defer this test to Task 2.9 and don't write it here.

For this task, instead just add a unit test asserting that when the deliverable's `code/` exists, `rm` runs `git_ops.remove_worktree`:

```python
def test_rm_calls_remove_worktree_if_code_dir_present(projects, make_project, make_deliverable, monkeypatch, tmp_path) -> None:
    """If deliv/code exists, rm calls git_ops.remove_worktree on it."""
    deliv = make_deliverable(project_name="foo", name="bar", description="d")
    (deliv / "code").mkdir()
    calls = []
    def fake_remove(dest, *, force=False):
        calls.append((str(dest), force))
    monkeypatch.setattr("keel.git_ops.remove_worktree", fake_remove)
    runner.invoke(app, ["deliverable", "rm", "bar", "-y", "--project", "foo"])
    assert calls == [(str(deliv / "code"), False)]
```

- [ ] **Step 2: Run, expect FAIL**

Run: `uv run --extra dev pytest tests/commands/deliverable/test_rm.py::test_rm_calls_remove_worktree_if_code_dir_present -v`
Expected: FAIL.

- [ ] **Step 3: Add worktree handling to `cmd_rm`**

In `src/keel/commands/deliverable/rm.py`, just before the `shutil.rmtree(deliv)` call (and before clean-up of parent files), add:

```python
    # Remove worktree if present (and not --keep-code)
    code_dir = deliv / "code"
    if code_dir.is_dir() and not keep_code:
        from keel import git_ops
        try:
            git_ops.remove_worktree(code_dir, force=force)
        except git_ops.GitError as e:
            out.error(f"failed to remove worktree at {code_dir}: {e}", code="git_failed")
            raise typer.Exit(code=1)
```

- [ ] **Step 4: Run tests**

Run: `uv run --extra dev pytest tests/commands/deliverable/test_rm.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add keel/src/keel/commands/deliverable/rm.py keel/tests/commands/deliverable/test_rm.py
git commit -m "feat(keel): 'deliverable rm' removes worktree when present"
```

---

### Task 2.9: `deliverable add` — `--repo` and `--shared` modes

**Files:**
- Modify: `src/keel/commands/deliverable/add.py`
- Modify: `tests/commands/deliverable/test_add.py`

- [ ] **Step 1: Write failing tests**

Append to `test_add.py`:

```python
def test_add_with_repo_creates_worktree(projects, make_project, source_repo) -> None:
    make_project("foo")
    result = runner.invoke(
        app,
        ["deliverable", "add", "bar", "-d", "d", "-y", "--project", "foo", "-r", str(source_repo)],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.stderr
    deliv = projects / "foo" / "deliverables" / "bar"
    assert (deliv / "code").is_dir()
    assert (deliv / "code" / "README").is_file()


def test_add_with_repo_writes_repo_to_manifest(projects, make_project, source_repo) -> None:
    make_project("foo")
    runner.invoke(
        app,
        ["deliverable", "add", "bar", "-d", "d", "-y", "--project", "foo", "-r", str(source_repo)],
    )
    from keel.manifest import load_deliverable_manifest
    m = load_deliverable_manifest(projects / "foo" / "deliverables" / "bar" / "design" / "deliverable.toml")
    assert len(m.repos) == 1
    assert m.repos[0].worktree == "code"


def test_add_shared_marks_manifest_and_no_repos(projects, make_project) -> None:
    make_project("foo")
    runner.invoke(app, ["deliverable", "add", "bar", "-d", "d", "-y", "--project", "foo", "--shared"])
    from keel.manifest import load_deliverable_manifest
    m = load_deliverable_manifest(projects / "foo" / "deliverables" / "bar" / "design" / "deliverable.toml")
    assert m.deliverable.shared_worktree is True
    assert m.repos == []
```

- [ ] **Step 2: Run tests, expect FAIL**

Run: `uv run --extra dev pytest tests/commands/deliverable/test_add.py -v -k "with_repo or shared"`
Expected: 3 FAIL.

- [ ] **Step 3: Update `cmd_add` to handle `--repo` and `--shared`**

In `src/keel/commands/deliverable/add.py`, update the manifest construction and add worktree creation. Replace the existing manifest write block with:

```python
    from keel import git_ops
    from keel.manifest import RepoSpec

    # Validate --repo if provided
    repo_path = None
    if repo and shared:
        out.error("--repo and --shared are mutually exclusive", code="conflicting_flags")
        raise typer.Exit(code=2)
    if repo:
        repo_path = Path(repo).expanduser().resolve()
        if not git_ops.is_git_repo(repo_path):
            out.error(f"not a git repo: {repo_path}", code="not_a_repo")
            raise typer.Exit(code=1)

    # Build manifest
    repo_specs: list[RepoSpec] = []
    if repo_path is not None:
        try:
            user_slug = git_ops.git_user_slug(repo_path)
        except Exception:
            user_slug = "user"
        repo_specs.append(RepoSpec(
            remote=str(repo_path),
            local_hint=str(repo_path),
            worktree="code",
            branch_prefix=f"{user_slug}/{project}-{slug}",
        ))
    manifest = DeliverableManifest(
        deliverable=DeliverableMeta(
            name=slug,
            parent_project=project,
            description=description,
            created=date.today(),
            shared_worktree=shared,
        ),
        repos=repo_specs,
    )
    save_deliverable_manifest(deliv / "design" / "deliverable.toml", manifest)
```

Then, after design files are written, before the parent-file mutations, add worktree creation:

```python
    # Create worktree if --repo
    created_worktree = None
    if repo_path is not None:
        wt_dest = deliv / "code"
        try:
            git_ops.create_worktree(repo_path, wt_dest, branch=repo_specs[0].branch_prefix)
            created_worktree = str(wt_dest)
        except git_ops.GitError as e:
            out.error(f"worktree creation failed: {e}", code="git_failed")
            out.info(f"Design files are at {deliv / 'design'}; clean up manually if needed.")
            raise typer.Exit(code=1)
```

Update the result payload to include the worktree:

```python
    out.result(
        {
            "deliverable_path": str(deliv),
            "modified_files": modified_files,
            "worktree": created_worktree,
        },
        human_text=f"Deliverable created: {deliv}",
    )
```

- [ ] **Step 4: Run tests**

Run: `uv run --extra dev pytest tests/commands/deliverable/test_add.py -v`
Expected: 11 PASS (8 + 3).

- [ ] **Step 5: Commit**

```bash
git add keel/src/keel/commands/deliverable/add.py keel/tests/commands/deliverable/test_add.py
git commit -m "feat(keel): 'deliverable add --repo' and '--shared' modes"
```

---

### Task 2.10: `deliverable rename`

**Files:**
- Create: `src/keel/commands/deliverable/rename.py`
- Create: `tests/commands/deliverable/test_rename.py`
- Modify: `src/keel/commands/deliverable/__init__.py`

- [ ] **Step 1: Write failing tests**

Create `tests/commands/deliverable/test_rename.py`:

```python
"""Tests for `keel deliverable rename`."""
from typer.testing import CliRunner
from keel.app import app

runner = CliRunner()


def test_rename_moves_design_dir(projects, make_project, make_deliverable) -> None:
    old = make_deliverable(project_name="foo", name="bar", description="d")
    result = runner.invoke(
        app,
        ["deliverable", "rename", "bar", "baz", "-y", "--project", "foo"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.stderr
    assert not old.exists()
    new = projects / "foo" / "deliverables" / "baz"
    assert new.is_dir()
    assert (new / "design" / "deliverable.toml").is_file()


def test_rename_updates_manifest_name(projects, make_project, make_deliverable) -> None:
    make_deliverable(project_name="foo", name="bar", description="d")
    runner.invoke(app, ["deliverable", "rename", "bar", "baz", "-y", "--project", "foo"])
    from keel.manifest import load_deliverable_manifest
    m = load_deliverable_manifest(projects / "foo" / "deliverables" / "baz" / "design" / "deliverable.toml")
    assert m.deliverable.name == "baz"


def test_rename_fails_if_target_exists(projects, make_project, make_deliverable) -> None:
    make_deliverable(project_name="foo", name="bar", description="d")
    make_deliverable(project_name="foo", name="baz", description="d")
    result = runner.invoke(app, ["deliverable", "rename", "bar", "baz", "-y", "--project", "foo"])
    assert result.exit_code == 1
    assert "exists" in result.stderr.lower()


def test_rename_updates_parent_references(projects, make_project) -> None:
    make_project("foo")
    runner.invoke(app, ["deliverable", "add", "bar", "-d", "d", "-y", "--project", "foo"])
    runner.invoke(app, ["deliverable", "rename", "bar", "baz", "-y", "--project", "foo"])
    parent_claude = (projects / "foo" / "design" / "CLAUDE.md").read_text()
    assert "**bar**" not in parent_claude
    assert "**baz**" in parent_claude
```

- [ ] **Step 2: Run, expect collection error**

Run: `uv run --extra dev pytest tests/commands/deliverable/test_rename.py -v`
Expected: collection error.

- [ ] **Step 3: Implement `src/keel/commands/deliverable/rename.py`**

```python
"""`keel deliverable rename <old> <new>`."""
from __future__ import annotations
import shutil
import typer

from keel import workspace
from keel.markdown_edit import insert_under_heading
from keel.manifest import (
    DeliverableManifest, DeliverableMeta,
    load_deliverable_manifest, save_deliverable_manifest,
)
from keel.output import Output


def cmd_rename(
    old: str = typer.Argument(...),
    new: str = typer.Argument(...),
    project: str | None = typer.Option(None, "--project", "-p"),
    rename_branch: bool = typer.Option(True, "--rename-branch/--no-rename-branch"),
    yes: bool = typer.Option(False, "-y", "--yes"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    """Rename a deliverable."""
    out = Output(json_mode=json_mode)

    if project is None:
        scope = workspace.detect_scope()
        project = scope.project
    if project is None:
        out.error("no project specified and none detected from CWD", code="no_project")
        raise typer.Exit(code=1)
    if not workspace.deliverable_exists(project, old):
        out.error(f"deliverable not found: {project}/{old}", code="not_found")
        raise typer.Exit(code=1)
    if workspace.deliverable_exists(project, new):
        out.error(f"target already exists: {project}/{new}", code="exists")
        raise typer.Exit(code=1)

    old_path = workspace.deliverable_dir(project, old)
    new_path = workspace.deliverable_dir(project, new)

    if dry_run:
        from keel.dryrun import OpLog
        log = OpLog()
        log.modify_file(old_path, diff=f"rename → {new_path}")
        out.info(log.format_summary())
        return

    # 1. Move the design dir
    shutil.move(str(old_path), str(new_path))

    # 2. Update manifest's `name`
    manifest_path = new_path / "design" / "deliverable.toml"
    m = load_deliverable_manifest(manifest_path)
    new_manifest = DeliverableManifest(
        deliverable=DeliverableMeta(
            name=new,
            parent_project=m.deliverable.parent_project,
            description=m.deliverable.description,
            created=m.deliverable.created,
            shared_worktree=m.deliverable.shared_worktree,
        ),
        repos=m.repos,
    )
    save_deliverable_manifest(manifest_path, new_manifest)

    # 3. Update parent CLAUDE.md and design.md references
    description = m.deliverable.description
    parent_claude = workspace.project_dir(project) / "design" / "CLAUDE.md"
    if parent_claude.is_file():
        text = parent_claude.read_text()
        new_lines = []
        for line in text.splitlines(keepends=True):
            if line.lstrip().startswith(f"- **{old}**:"):
                indent = line[:len(line) - len(line.lstrip())]
                new_lines.append(f"{indent}- **{new}**: ../deliverables/{new}/design/ -- {description}\n")
            else:
                new_lines.append(line)
        parent_claude.write_text("".join(new_lines))

    parent_design = workspace.project_dir(project) / "design" / "design.md"
    if parent_design.is_file():
        text = parent_design.read_text()
        new_lines = []
        for line in text.splitlines(keepends=True):
            if line.lstrip().startswith(f"- **{old}**:"):
                indent = line[:len(line) - len(line.lstrip())]
                new_lines.append(
                    f"{indent}- **{new}**: {description}. See [design](../deliverables/{new}/design/design.md).\n"
                )
            else:
                new_lines.append(line)
        parent_design.write_text("".join(new_lines))

    # 4. Update sibling deliverable CLAUDE.md files
    siblings_dir = workspace.project_dir(project) / "deliverables"
    if siblings_dir.is_dir():
        for sibling in siblings_dir.iterdir():
            if not sibling.is_dir() or sibling.name == new:
                continue
            sibling_claude = sibling / "design" / "CLAUDE.md"
            if sibling_claude.is_file():
                text = sibling_claude.read_text()
                new_lines = []
                for line in text.splitlines(keepends=True):
                    if line.lstrip().startswith(f"- {old}:"):
                        indent = line[:len(line) - len(line.lstrip())]
                        new_lines.append(f"{indent}- {new}: ../{new}/design/ -- {description}\n")
                    else:
                        new_lines.append(line)
                sibling_claude.write_text("".join(new_lines))

    # 5. (Optional) git worktree move + branch rename
    code_dir = new_path / "code"
    if code_dir.is_dir():
        from keel import git_ops
        # The worktree directory was moved by shutil.move; we need to tell git.
        # Use `git worktree repair` if available; otherwise skip.
        try:
            import subprocess
            subprocess.run(
                ["git", "-C", str(code_dir), "worktree", "repair"],
                check=True, capture_output=True,
            )
        except subprocess.CalledProcessError:
            out.warn("git worktree repair failed after rename — verify worktree state manually")
        if rename_branch and m.repos:
            old_branch = m.repos[0].branch_prefix
            if old_branch and old_branch.endswith(f"-{old}"):
                new_branch = old_branch[: -len(f"-{old}")] + f"-{new}"
                try:
                    git_ops.rename_branch(code_dir, old=old_branch, new=new_branch)
                except git_ops.GitError as e:
                    out.warn(f"branch rename failed: {e}")

    out.info(f"Renamed {old} → {new}")
    out.result(
        {"old": str(old_path), "new": str(new_path)},
        human_text=f"Deliverable renamed: {old} → {new}",
    )
```

- [ ] **Step 4: Register in `__init__.py`**

```python
from keel.commands.deliverable.rename import cmd_rename
app.command(name="rename")(cmd_rename)
```

- [ ] **Step 5: Run tests**

Run: `uv run --extra dev pytest tests/commands/deliverable/test_rename.py -v`
Expected: 4 PASS.

- [ ] **Step 6: Commit**

```bash
git add keel/src/keel/commands/deliverable/rename.py keel/src/keel/commands/deliverable/__init__.py keel/tests/commands/deliverable/test_rename.py
git commit -m "feat(keel): implement 'deliverable rename' with parent + sibling updates"
```

---

## Milestone 3: Decision group

### Task 3.1: Scaffold `commands/decision/` subpackage

**Files:**
- Create: `src/keel/commands/decision/__init__.py`
- Create: `tests/commands/decision/__init__.py`
- Modify: `src/keel/app.py`

- [ ] **Step 1: Create the subpackage**

```python
# src/keel/commands/decision/__init__.py
"""`keel decision ...` command group."""
from __future__ import annotations
import typer

app = typer.Typer(
    name="decision",
    help="Manage decision records.",
    no_args_is_help=True,
)
```

```python
# tests/commands/decision/__init__.py
```

(empty)

- [ ] **Step 2: Register in `app.py`**

Append:

```python
from keel.commands.decision import app as decision_app
app.add_typer(decision_app, name="decision")
```

- [ ] **Step 3: Smoke check**

Run: `keel decision --help`
Expected: shows the help text with no subcommands yet.

- [ ] **Step 4: Run full suite**

Run: `uv run --extra dev pytest`
Expected: previous count + 0 (no new tests).

- [ ] **Step 5: Commit**

```bash
git add keel/src/keel/commands/decision/ keel/tests/commands/decision/ keel/src/keel/app.py
git commit -m "feat(keel): scaffold decision command group"
```

---

### Task 3.2: `decision new` — basic file creation

**Files:**
- Create: `src/keel/commands/decision/new.py`
- Create: `tests/commands/decision/test_new.py`
- Modify: `src/keel/commands/decision/__init__.py`

- [ ] **Step 1: Write failing tests**

Create `tests/commands/decision/test_new.py`:

```python
"""Tests for `keel decision new`."""
from typer.testing import CliRunner
from keel.app import app

runner = CliRunner()


def test_new_creates_decision_file_at_project_level(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj / "design")
    result = runner.invoke(
        app,
        ["decision", "new", "Use Pydantic v2", "--no-edit"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.stderr
    decisions = list((proj / "design" / "decisions").glob("*.md"))
    decision_files = [f for f in decisions if "use-pydantic-v2" in f.name]
    assert len(decision_files) == 1


def test_new_at_deliverable_level(projects, make_deliverable, monkeypatch) -> None:
    deliv = make_deliverable(project_name="foo", name="bar", description="d")
    monkeypatch.chdir(deliv / "design")
    result = runner.invoke(app, ["decision", "new", "Some choice", "--no-edit"], catch_exceptions=False)
    assert result.exit_code == 0
    decision_files = list((deliv / "design" / "decisions").glob("*-some-choice.md"))
    assert len(decision_files) == 1


def test_new_writes_frontmatter_and_template(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj / "design")
    runner.invoke(app, ["decision", "new", "Pick a thing", "--no-edit"])
    decision_files = list((proj / "design" / "decisions").glob("*-pick-a-thing.md"))
    body = decision_files[0].read_text()
    assert "title: Pick a thing" in body
    assert "status: proposed" in body
    assert "## Question" in body


def test_new_fails_if_no_scope(projects, monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["decision", "new", "X", "--no-edit"])
    assert result.exit_code == 1
    assert "no project" in result.stderr.lower()
```

- [ ] **Step 2: Run, expect collection error**

Run: `uv run --extra dev pytest tests/commands/decision/test_new.py -v`
Expected: collection error.

- [ ] **Step 3: Implement `src/keel/commands/decision/new.py`**

```python
"""`keel decision new <title>`."""
from __future__ import annotations
from datetime import date
from pathlib import Path
import os
import re
import subprocess
import typer

from keel import templates, workspace
from keel.output import Output


_SLUG_RE = re.compile(r"[^a-z0-9-]+")


def _slugify_title(title: str) -> str:
    s = title.lower().strip().replace(" ", "-")
    return _SLUG_RE.sub("", s)


def cmd_new(
    title: str = typer.Argument(...),
    deliverable: str | None = typer.Option(None, "-D", "--deliverable"),
    project: str | None = typer.Option(None, "--project", "-p"),
    slug: str | None = typer.Option(None, "--slug"),
    supersedes: str | None = typer.Option(None, "--supersedes"),
    no_edit: bool = typer.Option(False, "--no-edit"),
    force: bool = typer.Option(False, "--force"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    """Create a new decision record at the current scope (project or deliverable)."""
    out = Output(json_mode=json_mode)

    # Resolve scope
    if project is None or (deliverable is None and workspace.detect_scope().deliverable):
        scope = workspace.detect_scope()
        project = project or scope.project
        deliverable = deliverable if deliverable is not None else scope.deliverable
    if project is None:
        out.error("no project specified and none detected from CWD", code="no_project")
        raise typer.Exit(code=1)
    if not workspace.project_exists(project):
        out.error(f"project not found: {project}", code="not_found")
        raise typer.Exit(code=1)
    if deliverable is not None and not workspace.deliverable_exists(project, deliverable):
        out.error(f"deliverable not found: {project}/{deliverable}", code="not_found")
        raise typer.Exit(code=1)

    # Compute target dir
    if deliverable:
        target_dir = workspace.deliverable_dir(project, deliverable) / "design" / "decisions"
        scope_label = "deliverable"
    else:
        target_dir = workspace.project_dir(project) / "design" / "decisions"
        scope_label = "project"

    today = date.today().isoformat()
    slug_value = slug or _slugify_title(title)
    if not slug_value:
        out.error("invalid title (slug is empty)", code="invalid_title")
        raise typer.Exit(code=2)
    filename = f"{today}-{slug_value}.md"
    path = target_dir / filename

    if path.exists() and not force:
        out.error(f"decision file already exists: {path}", code="exists")
        raise typer.Exit(code=1)

    if dry_run:
        from keel.dryrun import OpLog
        log = OpLog()
        log.create_file(path, size=0)
        out.info(log.format_summary())
        return

    target_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(templates.render("decision_entry.j2", date=today, title=title))

    out.info(f"Created decision: {path}")
    out.result(
        {"path": str(path), "scope": scope_label, "slug": slug_value, "supersedes": supersedes},
        human_text=f"Decision created: {path}",
    )

    # Open editor
    if not no_edit and os.environ.get("EDITOR") and not dry_run:
        try:
            subprocess.run([os.environ["EDITOR"], str(path)], check=False)
        except Exception:
            pass  # don't fail the command if editor invocation fails
```

- [ ] **Step 4: Register**

```python
# Append to src/keel/commands/decision/__init__.py
from keel.commands.decision.new import cmd_new
app.command(name="new")(cmd_new)
```

- [ ] **Step 5: Run tests**

Run: `uv run --extra dev pytest tests/commands/decision/test_new.py -v`
Expected: 4 PASS.

- [ ] **Step 6: Commit**

```bash
git add keel/src/keel/commands/decision/new.py keel/src/keel/commands/decision/__init__.py keel/tests/commands/decision/test_new.py
git commit -m "feat(keel): implement 'decision new' with auto-scope from CWD"
```

---

### Task 3.3: `decision new --supersedes` flag

**Files:**
- Modify: `src/keel/commands/decision/new.py`
- Modify: `tests/commands/decision/test_new.py`

- [ ] **Step 1: Write failing test**

Append to `test_new.py`:

```python
def test_new_supersedes_marks_old_decision(projects, make_project, monkeypatch) -> None:
    """--supersedes should mark the old decision as superseded and link to the new one."""
    proj = make_project("foo")
    monkeypatch.chdir(proj / "design")
    runner.invoke(app, ["decision", "new", "Old choice", "--no-edit"])
    old_files = list((proj / "design" / "decisions").glob("*-old-choice.md"))
    assert len(old_files) == 1
    old_slug = old_files[0].stem  # e.g. "2026-04-28-old-choice"

    runner.invoke(app, ["decision", "new", "New choice", "--no-edit", "--supersedes", "old-choice"])
    new_files = list((proj / "design" / "decisions").glob("*-new-choice.md"))
    assert len(new_files) == 1
    new_slug = new_files[0].stem

    old_body = old_files[0].read_text()
    assert "status: superseded" in old_body
    assert new_slug in old_body  # references the new decision
```

- [ ] **Step 2: Run, expect FAIL**

Run: `uv run --extra dev pytest tests/commands/decision/test_new.py::test_new_supersedes_marks_old_decision -v`
Expected: FAIL.

- [ ] **Step 3: Add supersedes handling to `cmd_new`**

After the `path.write_text(...)` line (before the editor invocation), add:

```python
    if supersedes:
        # Find the file matching `supersedes` (which may be just the slug part or the full filename)
        candidate_paths = list(target_dir.glob(f"*-{supersedes}.md")) if not supersedes.endswith(".md") else [target_dir / supersedes]
        if not candidate_paths:
            out.warn(f"--supersedes: no decision matching '{supersedes}' found in {target_dir}")
        else:
            old_path = candidate_paths[0]
            old_text = old_path.read_text()
            # Replace status field in frontmatter
            new_text = re.sub(
                r"^status:\s*\S+",
                "status: superseded",
                old_text,
                count=1,
                flags=re.MULTILINE,
            )
            # Append "Superseded by:" line at end
            superseded_by_line = f"\nSuperseded by: {filename[:-3]}\n"  # strip .md
            if "Superseded by:" not in new_text:
                new_text = new_text.rstrip("\n") + superseded_by_line
            old_path.write_text(new_text)
```

- [ ] **Step 4: Run tests**

Run: `uv run --extra dev pytest tests/commands/decision/test_new.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add keel/src/keel/commands/decision/new.py keel/tests/commands/decision/test_new.py
git commit -m "feat(keel): 'decision new --supersedes' marks old decision and links forward"
```

---

### Task 3.4: `decision list`

**Files:**
- Create: `src/keel/commands/decision/list.py`
- Create: `tests/commands/decision/test_list.py`
- Modify: `src/keel/commands/decision/__init__.py`

- [ ] **Step 1: Write failing tests**

Create `tests/commands/decision/test_list.py`:

```python
"""Tests for `keel decision list`."""
import json
from typer.testing import CliRunner
from keel.app import app

runner = CliRunner()


def test_list_empty(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj / "design")
    result = runner.invoke(app, ["decision", "list"])
    assert result.exit_code == 0


def test_list_one_decision(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj / "design")
    runner.invoke(app, ["decision", "new", "Pick a thing", "--no-edit"])
    result = runner.invoke(app, ["decision", "list"])
    assert "Pick a thing" in result.stdout or "pick-a-thing" in result.stdout


def test_list_json(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj / "design")
    runner.invoke(app, ["decision", "new", "Pick a thing", "--no-edit"])
    result = runner.invoke(app, ["decision", "list", "--json"])
    payload = json.loads(result.stdout)
    assert "decisions" in payload
    assert len(payload["decisions"]) == 1
    d = payload["decisions"][0]
    assert d["title"] == "Pick a thing"
    assert d["status"] == "proposed"
    assert d["slug"]
    assert d["date"]
```

- [ ] **Step 2: Run, expect collection error**

- [ ] **Step 3: Implement `src/keel/commands/decision/list.py`**

```python
"""`keel decision list`."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import re
import typer
from rich.table import Table

from keel import workspace
from keel.output import Output


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
        rows.append(_DecisionRow(
            date=fm.get("date", d),
            slug=slug,
            title=fm.get("title", slug),
            status=fm.get("status", "unknown"),
            path=f,
        ))
    return rows


def cmd_list(
    deliverable: str | None = typer.Option(None, "-D", "--deliverable"),
    project: str | None = typer.Option(None, "--project", "-p"),
    all_scopes: bool = typer.Option(False, "--all", help="Include parent project decisions when at deliverable scope."),
    status: str | None = typer.Option(None, "--status"),
    since: str | None = typer.Option(None, "--since"),
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    """List decisions at the current scope."""
    out = Output(json_mode=json_mode)

    if project is None:
        scope = workspace.detect_scope()
        project = scope.project
        deliverable = deliverable if deliverable is not None else scope.deliverable
    if project is None:
        out.error("no project specified and none detected from CWD", code="no_project")
        raise typer.Exit(code=1)

    rows: list[_DecisionRow] = []
    if deliverable:
        rows.extend(_scan(workspace.deliverable_dir(project, deliverable) / "design" / "decisions"))
        if all_scopes:
            rows.extend(_scan(workspace.project_dir(project) / "design" / "decisions"))
    else:
        rows.extend(_scan(workspace.project_dir(project) / "design" / "decisions"))

    if status:
        rows = [r for r in rows if r.status == status]
    if since:
        rows = [r for r in rows if r.date >= since]

    rows.sort(key=lambda r: r.date, reverse=True)

    if json_mode:
        out.result({
            "decisions": [
                {"date": r.date, "slug": r.slug, "title": r.title, "status": r.status, "path": str(r.path)}
                for r in rows
            ]
        })
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
```

- [ ] **Step 4: Register**

```python
# Append to commands/decision/__init__.py
from keel.commands.decision.list import cmd_list
app.command(name="list")(cmd_list)
```

- [ ] **Step 5: Run tests**

Run: `uv run --extra dev pytest tests/commands/decision/test_list.py -v`
Expected: 3 PASS.

- [ ] **Step 6: Commit**

```bash
git add keel/src/keel/commands/decision/list.py keel/src/keel/commands/decision/__init__.py keel/tests/commands/decision/test_list.py
git commit -m "feat(keel): implement 'decision list'"
```

---

### Task 3.5: `decision show`

**Files:**
- Create: `src/keel/commands/decision/show.py`
- Create: `tests/commands/decision/test_show.py`
- Modify: `src/keel/commands/decision/__init__.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/commands/decision/test_show.py
"""Tests for `keel decision show`."""
import json
from typer.testing import CliRunner
from keel.app import app

runner = CliRunner()


def test_show_renders_decision(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj / "design")
    runner.invoke(app, ["decision", "new", "Pick a thing", "--no-edit"])
    result = runner.invoke(app, ["decision", "show", "pick-a-thing"])
    assert result.exit_code == 0
    assert "Pick a thing" in result.stdout


def test_show_raw_dumps_file_unchanged(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj / "design")
    runner.invoke(app, ["decision", "new", "Pick a thing", "--no-edit"])
    result = runner.invoke(app, ["decision", "show", "pick-a-thing", "--raw"])
    assert result.exit_code == 0
    assert "title: Pick a thing" in result.stdout
    assert "## Question" in result.stdout


def test_show_json(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj / "design")
    runner.invoke(app, ["decision", "new", "Pick a thing", "--no-edit"])
    result = runner.invoke(app, ["decision", "show", "pick-a-thing", "--json"])
    payload = json.loads(result.stdout)
    assert payload["frontmatter"]["title"] == "Pick a thing"
    assert "## Question" in payload["body_markdown"]


def test_show_unknown_slug(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj / "design")
    result = runner.invoke(app, ["decision", "show", "nonexistent"])
    assert result.exit_code == 1
```

- [ ] **Step 2: Run, expect collection error**

- [ ] **Step 3: Implement `src/keel/commands/decision/show.py`**

```python
"""`keel decision show <slug>`."""
from __future__ import annotations
from pathlib import Path
import re
import typer
from rich.markdown import Markdown

from keel import workspace
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
    body = text[m.end():]
    return fm, body


def _find_decision(decisions_dir: Path, slug: str) -> Path | None:
    """Find a decision file by slug or full filename."""
    if slug.endswith(".md"):
        candidate = decisions_dir / slug
        return candidate if candidate.is_file() else None
    matches = list(decisions_dir.glob(f"*-{slug}.md"))
    if matches:
        return matches[0]
    return None


def cmd_show(
    slug: str = typer.Argument(...),
    deliverable: str | None = typer.Option(None, "-D", "--deliverable"),
    project: str | None = typer.Option(None, "--project", "-p"),
    raw: bool = typer.Option(False, "--raw"),
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    """Show a decision record."""
    out = Output(json_mode=json_mode)

    if project is None:
        scope = workspace.detect_scope()
        project = scope.project
        deliverable = deliverable if deliverable is not None else scope.deliverable
    if project is None:
        out.error("no project specified and none detected from CWD", code="no_project")
        raise typer.Exit(code=1)

    if deliverable:
        target_dir = workspace.deliverable_dir(project, deliverable) / "design" / "decisions"
    else:
        target_dir = workspace.project_dir(project) / "design" / "decisions"

    path = _find_decision(target_dir, slug)
    if path is None:
        out.error(f"decision not found: {slug}", code="not_found")
        raise typer.Exit(code=1)

    text = path.read_text()
    fm, body = _split_frontmatter(text)

    if json_mode:
        out.result({
            "path": str(path),
            "frontmatter": fm,
            "body_markdown": body,
        })
        return

    if raw:
        out.result(None, human_text=text.rstrip("\n"))
        return

    out.print_rich(Markdown(body))
```

- [ ] **Step 4: Register**

```python
from keel.commands.decision.show import cmd_show
app.command(name="show")(cmd_show)
```

- [ ] **Step 5: Run tests, expect 4 PASS**

- [ ] **Step 6: Commit**

```bash
git add keel/src/keel/commands/decision/show.py keel/src/keel/commands/decision/__init__.py keel/tests/commands/decision/test_show.py
git commit -m "feat(keel): implement 'decision show' (rendered, raw, json)"
```

---

### Task 3.6: `decision rm`

**Files:**
- Create: `src/keel/commands/decision/rm.py`
- Create: `tests/commands/decision/test_rm.py`
- Modify: `src/keel/commands/decision/__init__.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/commands/decision/test_rm.py
"""Tests for `keel decision rm`."""
from typer.testing import CliRunner
from keel.app import app

runner = CliRunner()


def test_rm_removes_decision_file(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj / "design")
    runner.invoke(app, ["decision", "new", "Pick a thing", "--no-edit"])
    decisions = list((proj / "design" / "decisions").glob("*-pick-a-thing.md"))
    assert len(decisions) == 1
    runner.invoke(app, ["decision", "rm", "pick-a-thing", "-y"])
    decisions_after = list((proj / "design" / "decisions").glob("*-pick-a-thing.md"))
    assert decisions_after == []


def test_rm_unknown(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj / "design")
    result = runner.invoke(app, ["decision", "rm", "nonexistent", "-y"])
    assert result.exit_code == 1
```

- [ ] **Step 2: Run, expect collection error**

- [ ] **Step 3: Implement `src/keel/commands/decision/rm.py`**

```python
"""`keel decision rm <slug>`."""
from __future__ import annotations
from pathlib import Path
import typer

from keel import workspace
from keel.commands.decision.show import _find_decision
from keel.output import Output
from keel.prompts import confirm_destructive


def cmd_rm(
    slug: str = typer.Argument(...),
    deliverable: str | None = typer.Option(None, "-D", "--deliverable"),
    project: str | None = typer.Option(None, "--project", "-p"),
    yes: bool = typer.Option(False, "-y", "--yes"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    """Remove a decision file (the typical 'changed my mind' pattern is `decision new --supersedes` instead)."""
    out = Output(json_mode=json_mode)

    if project is None:
        scope = workspace.detect_scope()
        project = scope.project
        deliverable = deliverable if deliverable is not None else scope.deliverable
    if project is None:
        out.error("no project specified and none detected from CWD", code="no_project")
        raise typer.Exit(code=1)

    if deliverable:
        target_dir = workspace.deliverable_dir(project, deliverable) / "design" / "decisions"
    else:
        target_dir = workspace.project_dir(project) / "design" / "decisions"

    path = _find_decision(target_dir, slug)
    if path is None:
        out.error(f"decision not found: {slug}", code="not_found")
        raise typer.Exit(code=1)

    if dry_run:
        from keel.dryrun import OpLog
        log = OpLog()
        log.delete_file(path)
        out.info(log.format_summary())
        return

    confirm_destructive(f"Remove decision {path.name}?", yes=yes)

    path.unlink()
    out.info(f"Removed: {path}")
    out.result({"removed": str(path)}, human_text=f"Decision removed: {path}")
```

- [ ] **Step 4: Register**

```python
from keel.commands.decision.rm import cmd_rm
app.command(name="rm")(cmd_rm)
```

- [ ] **Step 5: Run tests, expect 2 PASS**

- [ ] **Step 6: Commit**

```bash
git add keel/src/keel/commands/decision/rm.py keel/src/keel/commands/decision/__init__.py keel/tests/commands/decision/test_rm.py
git commit -m "feat(keel): implement 'decision rm'"
```

---

## Milestone 4: Phase command

### Task 4.1: `phase` show mode

**Files:**
- Create: `src/keel/commands/phase.py`
- Create: `tests/commands/test_phase.py`
- Modify: `src/keel/app.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/commands/test_phase.py
"""Tests for `keel phase`."""
from typer.testing import CliRunner
from keel.app import app

runner = CliRunner()


def test_phase_show_at_project(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj / "design")
    result = runner.invoke(app, ["phase"])
    assert result.exit_code == 0
    assert "scoping" in result.stdout
    assert "foo" in result.stdout


def test_phase_show_at_deliverable(projects, make_deliverable, monkeypatch) -> None:
    deliv = make_deliverable(project_name="foo", name="bar", description="d")
    monkeypatch.chdir(deliv / "design")
    result = runner.invoke(app, ["phase"])
    assert result.exit_code == 0
    assert "scoping" in result.stdout


def test_phase_show_no_scope(projects, monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["phase"])
    assert result.exit_code == 1
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement `src/keel/commands/phase.py` with show mode only**

```python
"""`keel phase [PHASE]`."""
from __future__ import annotations
from datetime import date
from pathlib import Path
import typer

from keel import workspace
from keel.output import Output


PHASES = ["scoping", "designing", "poc", "implementing", "shipping", "done"]


def _phase_path(project: str, deliverable: str | None) -> Path:
    if deliverable:
        return workspace.deliverable_dir(project, deliverable) / "design" / ".phase"
    return workspace.project_dir(project) / "design" / ".phase"


def _read_phase(path: Path) -> tuple[str, list[str]]:
    """Returns (current_phase, history_lines). History lines are everything after line 1."""
    if not path.is_file():
        return "scoping", []
    lines = path.read_text().splitlines()
    if not lines:
        return "scoping", []
    return lines[0].strip() or "scoping", lines[1:]


def cmd_phase(
    phase: str | None = typer.Argument(None),
    next_phase: bool = typer.Option(False, "--next"),
    deliverable: str | None = typer.Option(None, "-D", "--deliverable"),
    project: str | None = typer.Option(None, "--project", "-p"),
    message: str | None = typer.Option(None, "-m", "--message"),
    no_decision: bool = typer.Option(False, "--no-decision"),
    yes: bool = typer.Option(False, "-y", "--yes"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    """Show or transition the phase."""
    out = Output(json_mode=json_mode)

    if project is None:
        scope = workspace.detect_scope()
        project = scope.project
        deliverable = deliverable if deliverable is not None else scope.deliverable
    if project is None:
        out.error("no project specified and none detected from CWD", code="no_project")
        raise typer.Exit(code=1)
    if deliverable is not None and not workspace.deliverable_exists(project, deliverable):
        out.error(f"deliverable not found: {project}/{deliverable}", code="not_found")
        raise typer.Exit(code=1)

    path = _phase_path(project, deliverable)
    current, history = _read_phase(path)

    if phase is None and not next_phase:
        # Show mode
        scope_name = f"{project}/{deliverable}" if deliverable else project
        if json_mode:
            out.result({
                "scope": "deliverable" if deliverable else "project",
                "name": scope_name,
                "phase": current,
                "history": [
                    {"line": h} for h in history if h.strip()
                ],
            })
            return
        out.result(
            None,
            human_text=f"{scope_name}\nphase: {current}\n\n" + "\n".join(history) if history else f"{scope_name}\nphase: {current}",
        )
        return

    # Transition mode (Task 4.2 will implement)
    out.error("phase transition not yet implemented (Task 4.2)", code="not_implemented")
    raise typer.Exit(code=2)
```

- [ ] **Step 4: Register**

```python
from keel.commands.phase import cmd_phase
app.command(name="phase")(cmd_phase)
```

- [ ] **Step 5: Run tests, expect 3 PASS**

- [ ] **Step 6: Commit**

```bash
git add keel/src/keel/commands/phase.py keel/src/keel/app.py keel/tests/commands/test_phase.py
git commit -m "feat(keel): implement 'phase' show mode"
```

---

### Task 4.2: `phase` forward transition + auto decision file

**Files:**
- Modify: `src/keel/commands/phase.py`
- Modify: `tests/commands/test_phase.py`

- [ ] **Step 1: Write failing tests**

Append to `test_phase.py`:

```python
def test_phase_forward_transition(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj / "design")
    result = runner.invoke(app, ["phase", "designing", "-m", "scope locked"])
    assert result.exit_code == 0
    phase_text = (proj / "design" / ".phase").read_text()
    assert phase_text.startswith("designing\n")
    # History line includes transition info:
    assert "scoping → designing" in phase_text or "scoping -> designing" in phase_text


def test_phase_transition_creates_decision_file(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj / "design")
    runner.invoke(app, ["phase", "designing", "-m", "ready"])
    decisions = list((proj / "design" / "decisions").glob("*-phase-designing.md"))
    assert len(decisions) == 1


def test_phase_transition_no_decision(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj / "design")
    runner.invoke(app, ["phase", "designing", "--no-decision"])
    decisions = list((proj / "design" / "decisions").glob("*-phase-designing.md"))
    assert len(decisions) == 0


def test_phase_invalid_phase(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj / "design")
    result = runner.invoke(app, ["phase", "bogus"])
    assert result.exit_code != 0
```

- [ ] **Step 2: Run, expect 4 FAIL**

- [ ] **Step 3: Implement transition logic**

Replace the placeholder block (after the `# Transition mode` comment) in `cmd_phase` with:

```python
    # Determine target phase
    target = phase
    if next_phase:
        if current not in PHASES:
            out.error(f"invalid current phase: {current}", code="invalid_phase")
            raise typer.Exit(code=1)
        idx = PHASES.index(current)
        if idx + 1 >= len(PHASES):
            out.error(f"no phase after {current}", code="end_of_lifecycle")
            raise typer.Exit(code=1)
        target = PHASES[idx + 1]

    if target not in PHASES:
        out.error(
            f"invalid phase: {target}. Valid phases: {', '.join(PHASES)}",
            code="invalid_phase",
        )
        raise typer.Exit(code=2)

    if target == current:
        out.info(f"already in phase: {current}")
        return

    # Backwards transition warning
    if PHASES.index(target) < PHASES.index(current):
        from keel.prompts import confirm_destructive
        confirm_destructive(
            f"Backwards phase transition: {current} → {target}. Continue?",
            yes=yes,
        )

    if dry_run:
        from keel.dryrun import OpLog
        log = OpLog()
        log.modify_file(path, diff=f"{current} → {target}")
        if not no_decision:
            today = date.today().isoformat()
            decisions_dir = path.parent / "decisions"
            log.create_file(decisions_dir / f"{today}-phase-{target}.md", size=0)
        out.info(log.format_summary())
        return

    # Apply transition
    today = date.today().isoformat()
    history_line = f"{today}  {current} → {target}"
    if message:
        history_line += f"  ({message})"
    new_lines = [target] + [history_line] + history
    path.write_text("\n".join(new_lines) + "\n")

    # Auto-create phase decision file
    if not no_decision:
        from keel import templates
        decisions_dir = path.parent / "decisions"
        decisions_dir.mkdir(parents=True, exist_ok=True)
        decision_path = decisions_dir / f"{today}-phase-{target}.md"
        if not decision_path.exists():
            decision_path.write_text(
                templates.render(
                    "decision_entry.j2",
                    date=today,
                    title=f"Phase transition: {current} → {target}",
                )
            )

    out.info(f"Phase: {current} → {target}")
    out.result(
        {
            "scope": "deliverable" if deliverable else "project",
            "name": f"{project}/{deliverable}" if deliverable else project,
            "phase": target,
            "transitioned_from": current,
        },
        human_text=f"Phase: {current} → {target}",
    )
```

- [ ] **Step 4: Run tests**

Run: `uv run --extra dev pytest tests/commands/test_phase.py -v`
Expected: 7 PASS.

- [ ] **Step 5: Commit**

```bash
git add keel/src/keel/commands/phase.py keel/tests/commands/test_phase.py
git commit -m "feat(keel): 'phase' forward/backward transitions with auto decision file"
```

---

### Task 4.3: `phase --next` shortcut

**Files:**
- Modify: `tests/commands/test_phase.py` (test only — implementation is in Task 4.2)

- [ ] **Step 1: Write test**

Append to `test_phase.py`:

```python
def test_phase_next_advances_one_step(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj / "design")
    result = runner.invoke(app, ["phase", "--next"])
    assert result.exit_code == 0
    assert (proj / "design" / ".phase").read_text().startswith("designing\n")


def test_phase_next_at_end_of_lifecycle(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    (proj / "design" / ".phase").write_text("done\n")
    monkeypatch.chdir(proj / "design")
    result = runner.invoke(app, ["phase", "--next"])
    assert result.exit_code == 1
    assert "no phase after" in result.stderr.lower()
```

- [ ] **Step 2: Run, expect PASS** (Task 4.2 already implemented `--next`)

Run: `uv run --extra dev pytest tests/commands/test_phase.py -v`
Expected: 9 PASS.

- [ ] **Step 3: Commit**

```bash
git add keel/tests/commands/test_phase.py
git commit -m "test(keel): cover 'phase --next' shortcut"
```

---

### Task 4.4: Final smoke check + advance keel's own phase

**Files:** none (just verification + workspace's `.phase` update)

- [ ] **Step 1: Run full suite**

Run: `cd ~/projects/keel && uv run --extra dev pytest -v`
Expected: all green (around 130+ tests).

- [ ] **Step 2: Manual smoke check**

```bash
PROJECTS_DIR=/tmp/keel-plan-2-smoke keel new alpha -d "test project" --no-worktree -y
PROJECTS_DIR=/tmp/keel-plan-2-smoke keel deliverable add foo -d "first deliverable" -y --project alpha
PROJECTS_DIR=/tmp/keel-plan-2-smoke keel deliverable add bar -d "second deliverable" -y --project alpha
PROJECTS_DIR=/tmp/keel-plan-2-smoke keel deliverable list --project alpha
cd /tmp/keel-plan-2-smoke/alpha/deliverables/foo/design
PROJECTS_DIR=/tmp/keel-plan-2-smoke keel decision new "Use library X" --no-edit
PROJECTS_DIR=/tmp/keel-plan-2-smoke keel decision list
PROJECTS_DIR=/tmp/keel-plan-2-smoke keel phase
PROJECTS_DIR=/tmp/keel-plan-2-smoke keel phase designing -m "ready"
PROJECTS_DIR=/tmp/keel-plan-2-smoke keel phase
cd /tmp && rm -rf /tmp/keel-plan-2-smoke
```

Expected: all commands succeed; deliverable list shows 2; decision created and shown; phase transition recorded.

- [ ] **Step 3: Tag the milestone**

```bash
git -C keel tag keel-plan-2
```

- [ ] **Step 4: Skip the workspace .phase advance**

(The workspace is already at "implementing" — no further transition needed for Plan 2 itself. The next plan can advance to "shipping" once the cutover lands.)

---

## Self-review (run before declaring Plan 2 done)

**Spec coverage** — every Plan 2 requirement covered:

| Spec section | Implementing tasks |
|---|---|
| §7.2 deliverable add | Tasks 2.3 (basic), 2.4 (parent files), 2.5 (siblings), 2.9 (--repo, --shared) |
| §7.3 deliverable rm | Tasks 2.7 (basic + parent), 2.8 (worktree) |
| §7.4 deliverable rename | Task 2.10 |
| §7.5 deliverable list | Task 2.6 |
| §7.6 decision new | Tasks 3.2, 3.3 (--supersedes) |
| §7.7 decision list | Task 3.4 |
| §7.8 decision show | Task 3.5 |
| §7.9 decision rm | Task 3.6 |
| §7.10 phase | Tasks 4.1 (show), 4.2 (transition), 4.3 (--next) |

**Forward debt resolved:**
- replace_section blank-line behavior — Task 1.2 ✓
- detect_scope existence validation — Task 1.3 (added `resolve_scope_or_fail`, kept `detect_scope` cheap) ✓
- Output.warn test — Task 1.4 ✓
- confirm_destructive test — Task 1.4 ✓
- _slugify edge cases — Task 1.4 ✓
- commands/ subpackage restructure — Tasks 1.1, 2.1, 3.1 ✓

**Forward debt deferred (still in decisions/2026-04-27-plan-1-implementation-fixes.md):**
- Multi-repo `Path.name` collision — relevant to `code add` in Plan 3
- git_user_slug Unicode handling — defer until first non-ASCII contributor
- RepoSpec.worktree single-component validator — Plan 3
- Output.print_rich abstraction question — Plan 3

**Type/name consistency check:**
- `cmd_add`, `cmd_rm`, `cmd_rename`, `cmd_list`, `cmd_new`, `cmd_show`, `cmd_phase` — consistent prefix
- All commands accept `--project`/`-p` and `-D`/`--deliverable` where applicable
- All commands take `--json`, mutating ones take `--dry-run`, destructive ones take `-y/--yes`
- All errors use the `code=` parameter on `out.error` for programmatic identification
- Manifest types (`DeliverableManifest`, `RepoSpec`) used consistently

---

## What this plan does NOT cover

- `validate` command (Plan 3)
- `archive` and project-level `rename` (Plan 3)
- `design export` (Plan 3)
- `code list/status/init/add/rm` (Plan 3)
- `migrate` (one-shot legacy migration — Plan 4)
- Shell completion installer (Plan 4)
- Slash command rewrites in `~/.claude/commands/` (Plan 4)
- Cutover from Bash `~/projects/bin/project` to `keel` (Plan 4)
