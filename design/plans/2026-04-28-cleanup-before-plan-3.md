# Plan 2.5: Cleanup before Plan 3

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Address the Important-tier issues from the post-Plan-2 review so Plan 3's 5+ new commands inherit cleaner foundations. Fix two bugs, extract 5 duplicated patterns into helpers, wire global flags + help text, sync public-repo best-practice files into the local workspace.

**Architecture:** Mostly refactoring + small bug fixes. Extracts shared command boilerplate (scope resolution, decisions-dir computation, phase reading, slugify, bullet-line removal) into 3 modules: `keel/util.py` (slugify), `keel/workspace.py` (scope/dir/phase helpers), `keel/markdown_edit.py` (one new editor function). Each command then drops ~15 lines of repeated logic. No new user-visible commands; behavioral changes are limited to bug fixes and surface UX.

**Tech Stack:** Same as Plans 1+2. Adds **ruff** for lint/format and a CI lint step.

---

## File Structure

After Plan 2.5 lands, new/changed files:

```
~/projects/keel/
├── LICENSE                              # NEW (synced from public repo)
├── CONTRIBUTING.md                      # NEW
├── SECURITY.md                          # NEW
├── README.md                            # OVERWRITE (rich public version)
├── .editorconfig                        # NEW
├── .github/                             # NEW (workflows, templates, dependabot)
├── pyproject.toml                       # MODIFY — add ruff config
├── src/keel/
│   ├── util.py                          # NEW — single slugify()
│   ├── workspace.py                     # MODIFY — add resolve_cli_scope, decisions_dir, read_phase
│   ├── markdown_edit.py                 # MODIFY — add remove_bullet_under_heading
│   ├── output.py                        # MODIFY — accept quiet/verbose from app context
│   ├── app.py                           # MODIFY — store quiet/verbose in Typer context
│   ├── _templates/claude_md.j2          # MODIFY — fix sibling-heading guard
│   └── commands/
│       ├── new.py                       # MODIFY — use util.slugify; help= strings
│       ├── list.py                      # MODIFY — use workspace.read_phase
│       ├── show.py                      # MODIFY — use workspace.read_phase + drop unused Path
│       ├── phase.py                     # MODIFY — use workspace.read_phase + helpers
│       ├── deliverable/
│       │   ├── add.py                   # MODIFY — fix sibling pass; util.slugify; help=
│       │   ├── rm.py                    # MODIFY — markdown_edit.remove_bullet_under_heading
│       │   ├── rename.py                # MODIFY — same
│       │   └── list.py                  # MODIFY — workspace.resolve_cli_scope
│       └── decision/
│           ├── new.py                   # MODIFY — util.slugify; workspace.decisions_dir; drop Path
│           ├── list.py                  # MODIFY — workspace.decisions_dir; drop Path
│           ├── show.py                  # MODIFY — workspace.decisions_dir
│           └── rm.py                    # MODIFY — workspace.decisions_dir; drop Path
└── design/decisions/
    └── 2026-04-28-plan-2-implementation-fixes.md  # NEW — record what Plan 2 fixed and what's deferred to Plan 3+
```

---

## Pre-requisites

- Plan 2 is complete and tagged `keel-plan-2`
- 157 tests passing on `main`
- Working dir: `keel/`
- Run tests: `uv run --extra dev pytest`

---

## Milestone 1: Two remaining correctness bugs

### Task 1.1: Fix sibling-consistency bug — newly added deliverable lists existing siblings

**Files:**
- Modify: `src/keel/commands/deliverable/add.py`
- Modify: `tests/commands/deliverable/test_add.py`

**Background**: When `keel deliverable add B` runs, B's CLAUDE.md is rendered with `siblings=[]` (a hardcoded empty list at `add.py:117`). Existing siblings (A, C, ...) get B added to their CLAUDE.md, but B never learns about them.

- [ ] **Step 1: Write failing test**

Append to `tests/commands/deliverable/test_add.py`:

```python
def test_add_lists_existing_siblings_in_new_deliverable_claude(projects, make_project) -> None:
    """When adding B after A exists, B's own CLAUDE.md should list A as a sibling."""
    make_project("foo")
    runner.invoke(app, ["deliverable", "add", "alpha", "-d", "alpha thing", "-y", "--project", "foo"])
    runner.invoke(app, ["deliverable", "add", "beta", "-d", "beta thing", "-y", "--project", "foo"])
    beta_claude = (projects / "foo" / "deliverables" / "beta" / "design" / "CLAUDE.md").read_text()
    # Both directions of sibling reference should be present:
    assert "alpha" in beta_claude
```

- [ ] **Step 2: Run, expect FAIL**

Run: `uv run --extra dev pytest tests/commands/deliverable/test_add.py::test_add_lists_existing_siblings_in_new_deliverable_claude -v`
Expected: FAIL.

- [ ] **Step 3: Fix `cmd_add` in `src/keel/commands/deliverable/add.py`**

Find the line:
```python
    (deliv / "design" / "CLAUDE.md").write_text(
        templates.render("claude_md.j2", name=slug, description=description, repos=[], deliverables=[], siblings=[])
    )
```

Replace with this block (added BEFORE the write):

```python
    # Discover existing siblings for the new deliverable's CLAUDE.md
    existing_siblings: list[dict[str, str]] = []
    siblings_dir_for_render = workspace.project_dir(project) / "deliverables"
    if siblings_dir_for_render.is_dir():
        for sibling in sorted(siblings_dir_for_render.iterdir()):
            if not sibling.is_dir():
                continue
            sib_manifest = sibling / "design" / "deliverable.toml"
            if not sib_manifest.is_file():
                continue
            from keel.manifest import load_deliverable_manifest
            sm = load_deliverable_manifest(sib_manifest)
            existing_siblings.append({"name": sm.deliverable.name, "description": sm.deliverable.description})

    (deliv / "design" / "CLAUDE.md").write_text(
        templates.render(
            "claude_md.j2",
            name=slug, description=description,
            repos=[], deliverables=[], siblings=existing_siblings,
        )
    )
```

- [ ] **Step 4: Run tests, watch them pass**

Run: `uv run --extra dev pytest tests/commands/deliverable/test_add.py -v`
Expected: 12 PASS (existing 11 + 1 new).

- [ ] **Step 5: Commit**

```bash
git add keel/src/keel/commands/deliverable/add.py keel/tests/commands/deliverable/test_add.py
git commit -m "fix(keel): new deliverable's CLAUDE.md lists existing siblings"
```

---

### Task 1.2: Fix empty `## Sibling deliverables` heading

**Files:**
- Modify: `src/keel/_templates/claude_md.j2`
- Modify: `tests/test_templates.py`

**Background**: The template uses `{% if siblings is defined %}` which is true even when `siblings=[]`. So every newly created deliverable gets an empty `## Sibling deliverables` heading injected before `## Workflow`. Use a truthy check instead.

- [ ] **Step 1: Write failing test**

Append to `tests/test_templates.py`:

```python
def test_claude_md_no_empty_sibling_heading() -> None:
    """siblings=[] must not render an empty '## Sibling deliverables' heading."""
    out = render(
        "claude_md.j2",
        name="x", description="d",
        repos=[], deliverables=[], siblings=[],
    )
    assert "## Sibling deliverables" not in out


def test_claude_md_renders_sibling_heading_when_siblings_present() -> None:
    """When siblings is non-empty, the heading should render with bullets."""
    out = render(
        "claude_md.j2",
        name="x", description="d",
        repos=[], deliverables=[],
        siblings=[{"name": "alpha", "description": "the alpha"}],
    )
    assert "## Sibling deliverables" in out
    assert "- alpha:" in out
    assert "the alpha" in out
```

- [ ] **Step 2: Run, expect FAIL**

Run: `uv run --extra dev pytest tests/test_templates.py -v`
Expected: 1 FAIL (`test_claude_md_no_empty_sibling_heading`); the second test should already pass with current template.

- [ ] **Step 3: Fix `_templates/claude_md.j2`**

Find the line `{% if siblings is defined %}` and replace with `{% if siblings %}`. Save.

- [ ] **Step 4: Run tests, watch them pass**

Run: `uv run --extra dev pytest tests/test_templates.py tests/commands/deliverable/test_add.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add keel/src/keel/_templates/claude_md.j2 keel/tests/test_templates.py
git commit -m "fix(keel): suppress empty '## Sibling deliverables' heading"
```

---

## Milestone 2: Extract duplicated helpers

### Task 2.1: `keel/util.py` with single `slugify()`

**Files:**
- Create: `src/keel/util.py`
- Modify: `src/keel/commands/new.py`, `src/keel/commands/deliverable/add.py`, `src/keel/commands/decision/new.py`
- Modify: `tests/commands/test_slugify.py` (point at new location; keep existing test cases)

- [ ] **Step 1: Create `src/keel/util.py`**

```python
"""Cross-cutting utilities used by multiple commands."""
from __future__ import annotations
import re

_SLUG_RE = re.compile(r"[^a-z0-9-]+")


def slugify(name: str) -> str:
    """Lowercase, replace spaces with `-`, drop everything that isn't [a-z0-9-].

    Returns an empty string if the input has no slug-safe characters; callers
    should treat empty-result as invalid input.
    """
    s = name.lower().strip().replace(" ", "-")
    return _SLUG_RE.sub("", s)
```

- [ ] **Step 2: Point existing slugify tests at the new location**

In `tests/commands/test_slugify.py`, change `from keel.commands.new import _slugify` to `from keel.util import slugify as _slugify`. (Keep the test function bodies as-is.)

- [ ] **Step 3: Run, expect 8 PASS**

- [ ] **Step 4: Update the 3 callers to use `util.slugify`**

In each of `src/keel/commands/new.py`, `src/keel/commands/deliverable/add.py`, `src/keel/commands/decision/new.py`:
- Delete the local `_SLUG_RE` constant and the `_slugify`/`_slugify_title` function
- Add `from keel.util import slugify` at the top
- Replace each `_slugify(name)` / `_slugify_title(title)` call with `slugify(name)` / `slugify(title)`

- [ ] **Step 5: Run full suite**

Run: `uv run --extra dev pytest`
Expected: 158 PASS (157 + 1 sibling test from M1; this task doesn't add tests).

- [ ] **Step 6: Commit**

```bash
git add keel/src/keel/util.py keel/src/keel/commands/new.py keel/src/keel/commands/deliverable/add.py keel/src/keel/commands/decision/new.py keel/tests/commands/test_slugify.py
git commit -m "refactor(keel): centralize slugify in keel.util"
```

---

### Task 2.2: `workspace.resolve_cli_scope()` — extract scope-resolution boilerplate

**Files:**
- Modify: `src/keel/workspace.py`
- Modify: `tests/test_workspace.py`
- Refactor 8 command sites to use the new helper

**The pattern being extracted**:

```python
if project is None:
    scope = workspace.detect_scope()
    project = scope.project
    deliverable = deliverable if deliverable is not None else scope.deliverable
if project is None:
    out.error("no project specified and none detected from CWD", code="no_project")
    raise typer.Exit(code=1)
if not workspace.project_exists(project):
    out.error(f"project not found: {project}", code="not_found")
    raise typer.Exit(code=1)
# (sometimes followed by deliverable existence check)
```

- [ ] **Step 1: Add `resolve_cli_scope` to `src/keel/workspace.py`**

```python
def resolve_cli_scope(
    project: str | None,
    deliverable: str | None = None,
    *,
    allow_deliverable: bool = True,
    require_deliverable: bool = False,
) -> Scope:
    """Resolve the (project, deliverable) scope for a CLI command.

    Resolution order:
    1. If `project` is None, fall back to CWD detection.
    2. If `deliverable` is None and `allow_deliverable=True`, fall back to CWD detection for it too.
    3. Validate that the resolved project exists. Exit 1 with a clear message if not.
    4. If a deliverable is in scope, validate its manifest exists. Exit 1 if not.
    5. If `require_deliverable=True` and no deliverable resolved, exit 1.

    Always exits 1 (via typer.Exit) when scope can't be resolved.
    """
    import typer
    if project is None:
        scope = detect_scope()
        project = scope.project
        if allow_deliverable and deliverable is None:
            deliverable = scope.deliverable
    if project is None:
        typer.echo("error: no project specified and none detected from CWD", err=True)
        raise typer.Exit(code=1)
    if not project_exists(project):
        typer.echo(f"error: project not found: {project}", err=True)
        raise typer.Exit(code=1)
    if deliverable is not None and not deliverable_exists(project, deliverable):
        typer.echo(f"error: deliverable not found: {project}/{deliverable}", err=True)
        raise typer.Exit(code=1)
    if require_deliverable and deliverable is None:
        typer.echo("error: deliverable required for this command", err=True)
        raise typer.Exit(code=1)
    return Scope(project=project, deliverable=deliverable)
```

- [ ] **Step 2: Write tests**

Append to `tests/test_workspace.py`:

```python
def test_resolve_cli_scope_explicit_project(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PROJECTS_DIR", str(tmp_path))
    (tmp_path / "foo" / "design").mkdir(parents=True)
    (tmp_path / "foo" / "design" / "project.toml").write_text(
        '[project]\nname = "foo"\ndescription = "d"\ncreated = 2026-04-28\n'
    )
    from keel.workspace import resolve_cli_scope
    scope = resolve_cli_scope(project="foo", deliverable=None)
    assert scope.project == "foo"
    assert scope.deliverable is None


def test_resolve_cli_scope_falls_back_to_cwd(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PROJECTS_DIR", str(tmp_path))
    (tmp_path / "foo" / "design").mkdir(parents=True)
    (tmp_path / "foo" / "design" / "project.toml").write_text(
        '[project]\nname = "foo"\ndescription = "d"\ncreated = 2026-04-28\n'
    )
    monkeypatch.chdir(tmp_path / "foo" / "design")
    from keel.workspace import resolve_cli_scope
    scope = resolve_cli_scope(project=None)
    assert scope.project == "foo"


def test_resolve_cli_scope_missing_project_exits(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PROJECTS_DIR", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    from keel.workspace import resolve_cli_scope
    import typer
    with pytest.raises(typer.Exit) as exc:
        resolve_cli_scope(project=None)
    assert exc.value.exit_code == 1


def test_resolve_cli_scope_unknown_project_exits(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PROJECTS_DIR", str(tmp_path))
    from keel.workspace import resolve_cli_scope
    import typer
    with pytest.raises(typer.Exit) as exc:
        resolve_cli_scope(project="ghost")
    assert exc.value.exit_code == 1
```

- [ ] **Step 3: Run, expect 4 PASS**

Run: `uv run --extra dev pytest tests/test_workspace.py -v`

- [ ] **Step 4: Refactor 8 command sites to use `resolve_cli_scope`**

Replace the boilerplate in each of these files:
- `src/keel/commands/show.py`
- `src/keel/commands/deliverable/add.py` (use `allow_deliverable=False` since deliverable is the *child*, not the scope)
- `src/keel/commands/deliverable/rm.py`
- `src/keel/commands/deliverable/rename.py`
- `src/keel/commands/deliverable/list.py`
- `src/keel/commands/decision/new.py`
- `src/keel/commands/decision/list.py`
- `src/keel/commands/decision/show.py`
- `src/keel/commands/decision/rm.py`
- `src/keel/commands/phase.py`

Pattern: where the command currently does the multi-line scope resolution + project_exists check, replace with:

```python
    from keel.workspace import resolve_cli_scope
    scope = resolve_cli_scope(project, deliverable)  # or just `project` for project-only commands
    project = scope.project
    deliverable = scope.deliverable
```

For `deliverable add`: pass `allow_deliverable=False` because the deliverable name in `add` is a NEW name being created, not the active scope. The CWD scope-detect should still resolve `project` from `~/projects/<X>/`, but `deliverable` should remain `None` (it's the name being created).

For `decision new`, `decision list`, `decision show`, `decision rm`, `phase`: all use the standard `resolve_cli_scope(project, deliverable)`.

For `show`: it's project-only — call `resolve_cli_scope(project, None, allow_deliverable=False)`. The `--deliverable` flag handling there is a separate concern.

- [ ] **Step 5: Run full suite, watch all 162 PASS**

Run: `uv run --extra dev pytest`

- [ ] **Step 6: Commit**

```bash
git add keel/src/keel/workspace.py keel/tests/test_workspace.py keel/src/keel/commands/
git commit -m "refactor(keel): extract resolve_cli_scope helper, remove 8 sites of boilerplate"
```

---

### Task 2.3: `workspace.decisions_dir()` — single source of decision-dir paths

**Files:**
- Modify: `src/keel/workspace.py`
- Modify: `tests/test_workspace.py`
- Refactor 5 command sites in `commands/decision/` and `commands/phase.py`

- [ ] **Step 1: Add helper**

Append to `src/keel/workspace.py`:

```python
def decisions_dir(project: str, deliverable: str | None = None) -> Path:
    """Path to the decisions/ directory for the given scope."""
    if deliverable:
        return deliverable_dir(project, deliverable) / "design" / "decisions"
    return project_dir(project) / "design" / "decisions"
```

- [ ] **Step 2: Test**

Append to `tests/test_workspace.py`:

```python
def test_decisions_dir_project(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PROJECTS_DIR", str(tmp_path))
    from keel.workspace import decisions_dir
    assert decisions_dir("foo") == tmp_path / "foo" / "design" / "decisions"


def test_decisions_dir_deliverable(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PROJECTS_DIR", str(tmp_path))
    from keel.workspace import decisions_dir
    assert decisions_dir("foo", "bar") == tmp_path / "foo" / "deliverables" / "bar" / "design" / "decisions"
```

- [ ] **Step 3: Run tests, expect 2 PASS**

- [ ] **Step 4: Refactor 5 command sites**

In each of `src/keel/commands/decision/{new,list,show,rm}.py` and `src/keel/commands/phase.py`, find the inline pattern:

```python
if deliverable:
    target_dir = workspace.deliverable_dir(project, deliverable) / "design" / "decisions"
else:
    target_dir = workspace.project_dir(project) / "design" / "decisions"
```

Replace with:

```python
target_dir = workspace.decisions_dir(project, deliverable)
```

In `phase.py`, the equivalent computation for the phase decision file path can also use `decisions_dir`.

- [ ] **Step 5: Run full suite**

Expected: 164 PASS.

- [ ] **Step 6: Commit**

```bash
git add keel/src/keel/workspace.py keel/tests/test_workspace.py keel/src/keel/commands/
git commit -m "refactor(keel): centralize decisions/ path computation in workspace.decisions_dir"
```

---

### Task 2.4: `workspace.read_phase()` — single source of `.phase` reading

**Files:**
- Modify: `src/keel/workspace.py`
- Refactor 3 sites: `commands/list.py`, `commands/show.py`, `commands/deliverable/list.py`, `commands/phase.py`

- [ ] **Step 1: Add helper**

Append to `src/keel/workspace.py`:

```python
def read_phase(design_dir: Path) -> str:
    """Read the current phase from `<design_dir>/.phase`. Returns 'scoping' if the file is missing or empty."""
    phase_file = design_dir / ".phase"
    if not phase_file.is_file():
        return "scoping"
    lines = phase_file.read_text().splitlines()
    if not lines:
        return "scoping"
    return lines[0].strip() or "scoping"
```

- [ ] **Step 2: Test**

Append to `tests/test_workspace.py`:

```python
def test_read_phase_default_when_missing(tmp_path) -> None:
    from keel.workspace import read_phase
    assert read_phase(tmp_path) == "scoping"


def test_read_phase_default_when_empty(tmp_path) -> None:
    (tmp_path / ".phase").write_text("")
    from keel.workspace import read_phase
    assert read_phase(tmp_path) == "scoping"


def test_read_phase_value(tmp_path) -> None:
    (tmp_path / ".phase").write_text("implementing\n2026-04-28  scoping → implementing\n")
    from keel.workspace import read_phase
    assert read_phase(tmp_path) == "implementing"
```

- [ ] **Step 3: Run, expect 3 PASS**

- [ ] **Step 4: Refactor 4 sites**

In `commands/list.py`, `commands/show.py`, `commands/deliverable/list.py`: replace the pattern

```python
phase_file = ... / ".phase"
phase = phase_file.read_text().splitlines()[0].strip() if phase_file.is_file() else "scoping"
```

with `phase = workspace.read_phase(... / "design")`.

In `commands/phase.py`, the existing `_read_phase` private function can be replaced by calls to `workspace.read_phase(path.parent)` (where `path` is the `.phase` file path) — but the local function returns a tuple `(current, history)`. Keep `_read_phase` in `phase.py` but have it delegate the current-phase line to `workspace.read_phase`.

- [ ] **Step 5: Run full suite**

Expected: 167 PASS.

- [ ] **Step 6: Commit**

```bash
git add keel/src/keel/workspace.py keel/tests/test_workspace.py keel/src/keel/commands/
git commit -m "refactor(keel): centralize .phase reading in workspace.read_phase"
```

---

### Task 2.5: `markdown_edit.remove_bullet_under_heading()` — single source of bullet removal

**Files:**
- Modify: `src/keel/markdown_edit.py`
- Modify: `tests/test_markdown_edit.py`
- Refactor 6 sites in `commands/deliverable/{rm,rename}.py`

The pattern being extracted (currently appears 6 times):

```python
text = path.read_text()
new_lines = [
    line for line in text.splitlines(keepends=True)
    if not line.lstrip().startswith(f"- **{name}**:")  # or "- {name}:" for siblings
]
path.write_text("".join(new_lines))
```

The current `remove_line_under_heading` function only matches exact-byte equality. We need a pattern-prefix match.

- [ ] **Step 1: Test**

Append to `tests/test_markdown_edit.py`:

```python
def test_remove_bullet_by_prefix() -> None:
    """Remove all body lines under a section that start with the given prefix."""
    text = """# Title

## Deliverables

- **alpha**: ../deliverables/alpha/design/ -- the alpha
- **beta**: ../deliverables/beta/design/ -- the beta
- **gamma**: ../deliverables/gamma/design/ -- the gamma

## Other
"""
    from keel.markdown_edit import remove_bullet_under_heading
    out = remove_bullet_under_heading(text, "Deliverables", "- **beta**:")
    assert "**beta**" not in out
    assert "**alpha**" in out
    assert "**gamma**" in out
    assert "## Other" in out


def test_remove_bullet_no_match_is_noop() -> None:
    text = "# T\n\n## D\n- **a**: x\n"
    from keel.markdown_edit import remove_bullet_under_heading
    out = remove_bullet_under_heading(text, "D", "- **z**:")
    assert out == text
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Add helper**

Append to `src/keel/markdown_edit.py`:

```python
def remove_bullet_under_heading(text: str, title: str, line_prefix: str) -> str:
    """Remove every line in section `title` whose left-stripped form starts with `line_prefix`.

    Useful for removing bullet entries by their bullet-prefix pattern (e.g.
    `- **alpha**:` or `- alpha:`) without needing exact-byte equality.
    """
    text = _ensure_trailing_newline(text)
    sections = _find_sections(text)
    target = next((s for s in sections if s.title == title), None)
    if target is None:
        return text
    lines = text.splitlines(keepends=True)
    body = [
        line for line in lines[target.body_start:target.body_end]
        if not line.lstrip().startswith(line_prefix)
    ]
    return "".join(lines[:target.body_start]) + "".join(body) + "".join(lines[target.body_end:])
```

- [ ] **Step 4: Run, expect 2 PASS**

- [ ] **Step 5: Refactor 6 sites**

In `commands/deliverable/rm.py`, the parent-CLAUDE.md/design.md cleanup blocks:

```python
parent_claude = workspace.project_dir(project) / "design" / "CLAUDE.md"
if parent_claude.is_file():
    text = parent_claude.read_text()
    new_lines = [...]
    parent_claude.write_text("".join(new_lines))
```

Replace with:

```python
from keel.markdown_edit import remove_bullet_under_heading
parent_claude = workspace.project_dir(project) / "design" / "CLAUDE.md"
if parent_claude.is_file():
    parent_claude.write_text(
        remove_bullet_under_heading(parent_claude.read_text(), "Deliverables", f"- **{name}**:")
    )
```

Same pattern for parent_design (with `## Deliverables` heading and `- **{name}**:` prefix), and for sibling cleanup (`## Sibling deliverables` heading + `- {name}:` prefix).

In `commands/deliverable/rename.py`: similar refactor — there's the same prefix-line filtering for old-name removal and a separate explicit re-add for new-name. The refactor shrinks the explicit list-comprehensions to one-liners using `remove_bullet_under_heading` for the old-name removal portions.

- [ ] **Step 6: Run full suite**

Expected: 169 PASS.

- [ ] **Step 7: Commit**

```bash
git add keel/src/keel/markdown_edit.py keel/tests/test_markdown_edit.py keel/src/keel/commands/
git commit -m "refactor(keel): extract remove_bullet_under_heading, dedupe rm + rename"
```

---

## Milestone 3: User-facing UX gaps

### Task 3.1: Wire global `--quiet` / `--verbose` to `Output`

**Files:**
- Modify: `src/keel/app.py`
- Modify: `src/keel/output.py`
- Modify: every command (12 sites): instantiate Output from context state instead of bare flags
- Modify: `tests/test_output.py`

**Background**: `app.py:24-26` declares `--quiet` and `--verbose` Typer options on the root callback. `app.py:30-31` validates mutual exclusion. But the values never reach the `Output` instance: every command does `Output(json_mode=json_mode)` and ignores quiet/verbose.

Fix using a Typer `Context` object stashed at app callback level and read by commands.

- [ ] **Step 1: Modify `app.py` to stash flags on context**

Replace the existing `main` callback in `app.py` with:

```python
@app.callback()
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True,
        help="Show version and exit.",
    ),
    quiet: bool = typer.Option(False, "-q", "--quiet", help="Suppress info logs."),
    verbose: bool = typer.Option(False, "-v", "--verbose", help="Verbose logs."),
) -> None:
    """keel: scope-driven development scaffolder for ~/projects/."""
    if quiet and verbose:
        raise typer.BadParameter("--quiet and --verbose are mutually exclusive.")
    ctx.obj = {"quiet": quiet, "verbose": verbose}
```

- [ ] **Step 2: Add an `Output.from_context` factory**

Append to `src/keel/output.py`:

```python
    @classmethod
    def from_context(cls, ctx, *, json_mode: bool = False) -> "Output":
        """Build an Output instance using global --quiet/--verbose flags from a Typer context."""
        obj = (ctx.obj or {}) if hasattr(ctx, "obj") else {}
        return cls(
            quiet=obj.get("quiet", False),
            verbose=obj.get("verbose", False),
            json_mode=json_mode,
        )
```

- [ ] **Step 3: Tests**

Append to `tests/test_output.py`:

```python
def test_from_context_picks_up_quiet() -> None:
    """Output.from_context honors quiet=True from ctx.obj."""
    class _Ctx:
        obj = {"quiet": True, "verbose": False}
    o = Output.from_context(_Ctx())
    assert o.quiet is True


def test_from_context_picks_up_verbose() -> None:
    class _Ctx:
        obj = {"quiet": False, "verbose": True}
    o = Output.from_context(_Ctx())
    assert o.verbose is True


def test_from_context_with_json_mode_overrides_quiet() -> None:
    """--json forces quiet (existing constructor behavior)."""
    class _Ctx:
        obj = {"quiet": False, "verbose": False}
    o = Output.from_context(_Ctx(), json_mode=True)
    assert o.json_mode is True
    assert o.quiet is True


def test_from_context_handles_no_ctx_obj() -> None:
    """Don't crash if ctx.obj is None (subcommand invoked without root callback)."""
    class _Ctx:
        obj = None
    o = Output.from_context(_Ctx())
    assert o.quiet is False
    assert o.verbose is False
```

- [ ] **Step 4: Update every command to take a `ctx: typer.Context` and use `Output.from_context`**

Pattern for each command function signature: add `ctx: typer.Context` as the first parameter (Typer auto-injects). Replace `out = Output(json_mode=json_mode)` with `out = Output.from_context(ctx, json_mode=json_mode)`.

12 functions to update:
- `commands/new.py::cmd_new`
- `commands/list.py::cmd_list`
- `commands/show.py::cmd_show`
- `commands/phase.py::cmd_phase`
- `commands/deliverable/add.py::cmd_add`
- `commands/deliverable/rm.py::cmd_rm`
- `commands/deliverable/rename.py::cmd_rename`
- `commands/deliverable/list.py::cmd_list`
- `commands/decision/new.py::cmd_new`
- `commands/decision/list.py::cmd_list`
- `commands/decision/show.py::cmd_show`
- `commands/decision/rm.py::cmd_rm`

- [ ] **Step 5: Run full suite**

Expected: 173 PASS.

- [ ] **Step 6: Commit**

```bash
git add keel/src/keel/app.py keel/src/keel/output.py keel/src/keel/commands/ keel/tests/test_output.py
git commit -m "feat(keel): wire global --quiet/--verbose to Output via Typer context"
```

---

### Task 3.2: Fill in `help=` text on every command option

**Files:**
- Modify: every `commands/**/*.py` Typer option declaration

**Background**: Most options like `--slug`, `--supersedes`, `--no-edit`, `--shared`, `--keep-code`, etc. have no `help=` argument, so `keel <cmd> --help` shows the option name with no description. The success criterion in scope.md says `keel --help` is self-documenting; this fixes the gap.

- [ ] **Step 1: Audit current state**

Run: `keel new --help; keel list --help; keel show --help; keel phase --help; keel deliverable add --help; keel deliverable rm --help; keel deliverable rename --help; keel deliverable list --help; keel decision new --help; keel decision list --help; keel decision show --help; keel decision rm --help`

For every option that shows without a help description, fill in.

- [ ] **Step 2: Fill in `help=` for every Typer option**

Apply the help texts below. (Add `help="..."` to each Option's declaration in the corresponding command file.)

Ranking the cmds by number of options → most help text needed first:

`commands/new.py` (cmd_new):
- `description`: `"Brief project description; required (prompted on TTY if missing)."`
- `repo`: `"Source git repo for a worktree. Repeatable for multi-repo projects."`
- `no_worktree`: `"Skip worktree creation even if --repo provided."`
- `dry_run`: `"Print intended operations and exit; write nothing."`
- `yes`: `"Skip interactive prompts (description, etc.)."`
- `json_mode`: `"Emit machine-readable JSON to stdout."`

`commands/list.py` (cmd_list):
- `phase`: `"Filter to projects in the given phase."`
- `json_mode`: same as above

`commands/show.py` (cmd_show):
- `name`: `"Project name to show. Auto-detected from CWD if omitted."`
- `deliverable`: `"Show this deliverable instead of the project (--deliverable NAME)."`
- `json_mode`: same

`commands/phase.py`:
- `phase`: `"Target phase to transition to. Mutually exclusive with --next."`
- `next_phase`: `"Advance one step in the lifecycle."`
- `deliverable`: `"Phase scope: deliverable instead of project."`
- `project`: `"Project name. Auto-detected from CWD if omitted."`
- `message`: `"Optional note recorded in the phase history."`
- `no_decision`: `"Skip auto-creating a phase-transition decision file."`
- `yes`, `dry_run`, `json_mode`: same

`commands/deliverable/add.py`:
- `description`: `"Brief deliverable description; required."`
- `project`: `"Parent project. Auto-detected from CWD if omitted."`
- `repo`: `"Source git repo for the deliverable's own worktree. Mutually exclusive with --shared."`
- `shared`: `"Use the parent project's worktree (no own [[repos]])."`
- `dry_run`, `yes`, `json_mode`: same

`commands/deliverable/rm.py`:
- `keep_code`: `"Preserve the worktree dir even when removing the deliverable."`
- `keep_design`: `"Preserve the design dir (rare; use to keep records of a removed deliverable)."`
- `force`: `"Allow removal even if the worktree has uncommitted changes."`
- `project`, `yes`, `dry_run`, `json_mode`: same

`commands/deliverable/rename.py`:
- `rename_branch`: `"Also rename the worktree's git branch (default true)."`
- `project`, `yes`, `dry_run`, `json_mode`: same

`commands/deliverable/list.py`:
- `project`, `json_mode`: same

`commands/decision/new.py`:
- `deliverable`: `"Decision scope: a deliverable instead of the project. Auto-detected from CWD."`
- `project`: same as above
- `slug`: `"Override the auto-generated slug from the title."`
- `supersedes`: `"Mark an existing decision as superseded and link forward to this one. Pass the slug or the full filename."`
- `no_edit`: `"Don't open $EDITOR after creating the decision file."`
- `force`: `"Overwrite an existing decision file with the same name."`
- `dry_run`, `json_mode`: same

`commands/decision/list.py`:
- `all_scopes`: `"Include parent project decisions when at deliverable scope."`
- `status`: `"Filter by frontmatter 'status' (e.g., proposed, accepted, superseded)."`
- `since`: `"Show only decisions on or after this date (YYYY-MM-DD)."`
- `deliverable`, `project`, `json_mode`: same

`commands/decision/show.py`:
- `slug`: `"Decision slug (date prefix optional) or full filename."`
- `raw`: `"Print the raw file contents unchanged (pipe-friendly)."`
- `deliverable`, `project`, `json_mode`: same

`commands/decision/rm.py`:
- `deliverable`, `project`, `yes`, `dry_run`, `json_mode`: same

- [ ] **Step 3: Smoke check**

Run: `keel deliverable add --help` and `keel decision new --help` and `keel phase --help`. Confirm every option line has a description.

- [ ] **Step 4: Run full suite**

Expected: still 173 PASS (test count unchanged).

- [ ] **Step 5: Commit**

```bash
git add keel/src/keel/commands/
git commit -m "docs(keel): fill in help= text on every command option"
```

---

## Milestone 4: Tooling and best-practice file sync

### Task 4.1: Sync best-practice files into local workspace

**Files:**
- Copy from `` into `keel/`:
  - `LICENSE`
  - `CONTRIBUTING.md`
  - `SECURITY.md`
  - `README.md` (overwrite the 11-line stub with the rich version)
  - `.editorconfig`
  - `.github/dependabot.yml`
  - `.github/workflows/ci.yml`
  - `.github/ISSUE_TEMPLATE/bug.md`
  - `.github/ISSUE_TEMPLATE/feature.md`
  - `.github/PULL_REQUEST_TEMPLATE.md`

- [ ] **Step 1: Copy files**

```bash
cd ~/projects/keel
cp LICENSE .
cp CONTRIBUTING.md .
cp SECURITY.md .
cp README.md .
cp .editorconfig .
mkdir -p .github/workflows .github/ISSUE_TEMPLATE
cp .github/dependabot.yml .github/
cp .github/workflows/ci.yml .github/workflows/
cp .github/ISSUE_TEMPLATE/bug.md .github/ISSUE_TEMPLATE/
cp .github/ISSUE_TEMPLATE/feature.md .github/ISSUE_TEMPLATE/
cp .github/PULL_REQUEST_TEMPLATE.md .github/
```

- [ ] **Step 2: Run tests sanity check**

Run: `uv run --extra dev pytest`. Expected: 173 PASS. (Files added are docs-only.)

- [ ] **Step 3: Commit**

```bash
git add keel/LICENSE keel/CONTRIBUTING.md keel/SECURITY.md keel/README.md keel/.editorconfig keel/.github/
git commit -m "chore(keel): sync public-repo best-practice files into local workspace"
```

---

### Task 4.2: Add ruff config and lint CI step

**Files:**
- Modify: `pyproject.toml`
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Add `[tool.ruff]` config to `pyproject.toml`**

Append to `pyproject.toml`:

```toml
[tool.ruff]
line-length = 100
target-version = "py311"
src = ["src", "tests"]

[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors
    "F",   # pyflakes
    "I",   # isort
    "B",   # bugbear
    "UP",  # pyupgrade
    "SIM", # simplifications
]
ignore = [
    "E501",  # line too long (handled by formatter)
    "B008",  # function call in argument default (Typer requires this)
]

[tool.ruff.lint.per-file-ignores]
"tests/**/*.py" = ["B"]  # tests can have less-strict bugbear

[tool.ruff.format]
quote-style = "double"
```

Add `ruff>=0.6` to `[project.optional-dependencies].dev`.

- [ ] **Step 2: Run ruff fix on the codebase**

```bash
cd ~/projects/keel
uv sync --extra dev
uv run ruff check --fix src tests
uv run ruff format src tests
```

Expected output: a number of small fixes (unused imports including the `Path` ones flagged in the review, import ordering, etc.). NO behavioral changes.

- [ ] **Step 3: Run full suite to confirm no breakage**

Run: `uv run --extra dev pytest`. Expected: 173 PASS.

- [ ] **Step 4: Add lint step to CI**

In `.github/workflows/ci.yml`, append a `lint` job after the `test` job (and update `build`'s `needs:` to also include `lint`):

```yaml
  lint:
    name: Lint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6

      - name: Install uv
        uses: astral-sh/setup-uv@v7
        with:
          version: latest
          enable-cache: true

      - name: Set up Python 3.13
        run: uv python install 3.13

      - name: Ruff check
        run: uv run --extra dev ruff check src tests

      - name: Ruff format check
        run: uv run --extra dev ruff format --check src tests
```

Update `build` job's `needs: test` to `needs: [test, lint]`.

- [ ] **Step 5: Commit**

```bash
git add keel/pyproject.toml keel/.github/workflows/ci.yml keel/src keel/tests
git commit -m "chore(keel): add ruff config + lint step in CI"
```

---

### Task 4.3: Update stale forward-debt decision file

**Files:**
- Create: `design/decisions/2026-04-28-plan-2-implementation-fixes.md`
- Modify: `design/decisions/2026-04-27-plan-1-implementation-fixes.md` (mark superseded for the resolved items)

- [ ] **Step 1: Create the new decision file**

Create `keel/design/decisions/2026-04-28-plan-2-implementation-fixes.md`:

```markdown
---
date: 2026-04-28
title: Plan 2 implementation fixes and forward debt update
status: accepted
---

# Plan 2 implementation fixes and forward debt update

Captures Plan 2's implementation-time fixes plus an updated view of the
forward-debt list from the Plan 1 fixes decision (which is now partially
stale).

## Implementation-time fixes (already committed during Plan 2 execution)

- **Test isolation for `make_project`** — the `make_project` fixture was
  extended to render `CLAUDE.md` and `design.md` via the templates so
  AST-edit tests had something to mutate. Was previously creating only
  `project.toml` and `.phase`. (Plan 2 commit history.)

## Critical bugs found in post-Plan-2 review and fixed in Plan 2.5

- **`deliverable rm --keep-code` silently destroyed the worktree dir.**
  Fixed in commit `ef730f0`. The unconditional `shutil.rmtree(deliv)` at the
  end of `cmd_rm` was rmtreeing the worktree the flag was meant to preserve;
  changed to `shutil.rmtree(deliv / "design")` then conditional rmdir of the
  parent dir.
- **`deliverable rename` broke worktree git linkage.** Fixed in `dd59b96`.
  Used `shutil.move` for the whole `deliv/` dir, breaking git's worktree
  registration; now uses `git_ops.move_worktree` for the `code/` subdir
  followed by `shutil.move` for the rest. Removed the unreliable
  `git worktree repair` recovery dance.
- **`decision new --supersedes <wrong-slug>` silently succeeded.** Fixed in
  `ed454fc`. Validation moved before file creation; on no match, exits 1
  with `code="not_found"`.

## Forward-debt items from Plan 1 fixes decision — status update

| Item from Plan 1 fixes | Status as of Plan 2.5 |
|---|---|
| `replace_section` blank-line stability | Resolved (Plan 2 commit `d04ad8e`). |
| `detect_scope` existence validation | Resolved — `resolve_scope_or_fail` added in Plan 2; `resolve_cli_scope` (CLI-flavored) added in Plan 2.5 (replaces 8 sites of duplicated boilerplate). |
| `Output.warn` test gap | Resolved in Plan 2. |
| `confirm_destructive` test gap | Resolved in Plan 2. |
| `_slugify` edge case test gap | Resolved in Plan 2; in Plan 2.5 the function moved to `keel/util.py` and the test was rewired. |
| `commands/` subpackage restructure | Done in Plan 2. |
| Multi-repo `Path.name` collision | Still deferred. Plan 3's `code add` is the natural place to add the upfront duplicate-name check. |
| `git_user_slug` Unicode handling | Still deferred. No non-ASCII contributor surfaced yet. |
| `RepoSpec.worktree` single-component validator | Still deferred. Plan 3's `code add` / `validate` will tighten. |
| `Output.print_rich` leaky abstraction | Plan 2.5 leaves Rich-aware; commands import Rich types directly and use `out.print_rich(...)` for the actual print. Decision: stay Rich-aware, don't add per-type wrappers. |

## New forward debt from Plan 2 (resolved or deferred in Plan 2.5)

| Issue | Resolution |
|---|---|
| `deliverable rm --keep-code` data loss | Fixed (above). |
| `deliverable rename` worktree breakage | Fixed (above). |
| `decision new --supersedes` silent success | Fixed (above). |
| Sibling-consistency bug (B's CLAUDE.md doesn't list A) | Fixed in Plan 2.5 T1.1. |
| Empty `## Sibling deliverables` heading | Fixed in Plan 2.5 T1.2. |
| Global `--quiet`/`--verbose` flags didn't reach `Output` | Fixed in Plan 2.5 T3.1 (Typer Context). |
| Help text missing on ~80% of options | Fixed in Plan 2.5 T3.2. |
| 5 cross-command duplications | Fixed in Plan 2.5 M2 (3 helpers added: `slugify`, `resolve_cli_scope`, `decisions_dir`, `read_phase`, `remove_bullet_under_heading`). |
| Stale `dist/project_cli-*.whl` artifacts | Removed in Plan 2.5 (cleanup commit). |

## Consequences

- All Plan 1 forward-debt items either resolved or marked clearly deferred.
- Plan 3 inherits cleaner foundations — 5 utility helpers already in place
  for the 5+ new commands.
- Plan 1 fixes decision file remains as historical record but its forward-debt
  table is no longer load-bearing; this Plan 2 fixes file is the current
  source of truth for what's deferred.
```

- [ ] **Step 2: Mark the Plan 1 fixes file as superseded**

In `keel/design/decisions/2026-04-27-plan-1-implementation-fixes.md`, change frontmatter `status: accepted` to `status: superseded` and add at the top of the body:

```markdown
> **Superseded by `2026-04-28-plan-2-implementation-fixes.md`** for the
> forward-debt list. The implementation-fixes section below is still
> historically accurate; the forward-debt section is now stale (most items
> resolved by Plan 2 or Plan 2.5).
```

- [ ] **Step 3: Commit**

```bash
git add keel/design/decisions/
git commit -m "docs(keel): record Plan 2 fixes and supersede Plan 1 forward-debt list"
```

---

### Task 4.4: Final smoke + tag

- [ ] **Step 1: Run full suite**

Run: `cd ~/projects/keel && uv run --extra dev pytest -v`
Expected: 173 PASS.

- [ ] **Step 2: Run ruff check (must be clean)**

Run: `uv run ruff check src tests` — expect "All checks passed!"

- [ ] **Step 3: Smoke test the help output**

Run `keel --help`, `keel deliverable add --help`, `keel decision new --help`, `keel phase --help`. Confirm every option has a help description.

- [ ] **Step 4: Tag**

```bash
git -C keel tag keel-plan-2.5
```

---

## Self-review

**Spec coverage** — every Plan 2.5 item maps to a task:
- 2 bug fixes from review (#4, #5) → T1.1, T1.2
- 5 duplications (#8, #9, #10, #11, #14) → T2.1–T2.5
- Global flags (#6) → T3.1
- Help text (#13) → T3.2
- Best-practice files in local (#24, #25) → T4.1
- Tooling (#26) → T4.2
- Stale forward-debt doc (#15) → T4.3

**Type/name consistency:**
- `slugify` (not `_slugify`) is the new public name in `keel/util.py`
- `resolve_cli_scope` is the CLI-flavored helper; `resolve_scope_or_fail` (Plan 2) stays as the lower-level Path-based helper
- `decisions_dir`, `read_phase` are clear, scoped helper names
- `remove_bullet_under_heading` matches the existing `insert_under_heading`/`remove_line_under_heading`/`replace_section`/`section_exists` family in `markdown_edit.py`

**No placeholders.**

---

## What this plan does NOT cover

- Plan 3 work (`validate`, `archive`, `rename` at project level, `design export`, `code` group)
- Plan 4 work (migration, completion installer, slash command rewrites, cutover)
- Mypy / pre-commit / coverage tooling — deferred; ruff is enough for now
