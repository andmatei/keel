"""Tests for `keel phase`."""

import json

from typer.testing import CliRunner

from keel.app import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# T4.1: show mode
# ---------------------------------------------------------------------------


def test_phase_show_at_project(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    result = runner.invoke(app, ["phase"])
    assert result.exit_code == 0
    assert "scoping" in result.stdout
    assert "foo" in result.stdout


def test_phase_show_at_deliverable(projects, make_deliverable, monkeypatch) -> None:
    deliv = make_deliverable(project_name="foo", name="bar", description="d")
    monkeypatch.chdir(deliv)
    result = runner.invoke(app, ["phase"])
    assert result.exit_code == 0
    assert "scoping" in result.stdout


def test_phase_show_no_scope(projects, monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["phase"])
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# T4.2: forward/backward transitions + auto decision
# ---------------------------------------------------------------------------


def test_phase_forward_transition(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    result = runner.invoke(app, ["phase", "designing", "-m", "scope locked"])
    assert result.exit_code == 0
    phase_text = (proj / ".keel" / "phase").read_text()
    assert phase_text.startswith("designing\n")
    # History line includes transition info:
    assert "scoping → designing" in phase_text or "scoping -> designing" in phase_text


def test_phase_transition_creates_decision_file(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    runner.invoke(app, ["phase", "designing", "-m", "ready"])
    decisions = list((proj / "decisions").glob("*-phase-designing.md"))
    assert len(decisions) == 1


def test_phase_transition_no_decision(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    runner.invoke(app, ["phase", "designing", "--no-decision"])
    decisions = list((proj / "decisions").glob("*-phase-designing.md"))
    assert len(decisions) == 0


def test_phase_invalid_phase(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    result = runner.invoke(app, ["phase", "bogus"])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# T4.3: --next shortcut
# ---------------------------------------------------------------------------


def test_phase_next_advances_one_step(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    result = runner.invoke(app, ["phase", "--next"])
    assert result.exit_code == 0
    assert (proj / ".keel" / "phase").read_text().startswith("designing\n")


def test_phase_next_at_end_of_lifecycle(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    (proj / ".keel" / "phase").write_text("done\n")
    monkeypatch.chdir(proj)
    result = runner.invoke(app, ["phase", "--next"])
    assert result.exit_code == 1
    assert "no forward transition" in result.stderr.lower() or "terminal" in result.stderr.lower()


def test_phase_does_not_print_duplicate_messages(projects, make_project, monkeypatch) -> None:
    """'Phase: X → Y' (stderr) was redundant with 'Phase: X → Y' (stdout)."""
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    result = runner.invoke(app, ["phase", "designing"])
    assert result.exit_code == 0
    # The transition line should appear only once (on stdout via out.result), not also on stderr
    assert "scoping → designing" not in result.stderr
    assert result.stdout  # non-empty


# ---------------------------------------------------------------------------
# Task 2.1: Preflights with --no-verify, -y
# ---------------------------------------------------------------------------


def test_phase_next_warns_on_template_scope(projects, make_project, monkeypatch) -> None:
    from keel import templates

    proj = make_project("foo")
    # Overwrite scope.md with the unedited template
    (proj / "scope.md").write_text(templates.render("scope_md.j2", name="foo", description=""))
    monkeypatch.chdir(proj)
    result = runner.invoke(app, ["phase", "--next", "-y"])
    assert result.exit_code == 0
    assert "scope.md" in result.stderr.lower()


def test_phase_no_verify_skips_preflight(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    result = runner.invoke(app, ["phase", "--next", "--no-verify"])
    assert result.exit_code == 0


def test_phase_blocker_blocks_without_no_verify(projects, make_project, monkeypatch) -> None:
    """poc → implementing without milestones blocks."""
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    # Walk ahead through scoping→designing→poc using --no-verify to bypass intermediate
    # warnings, then try implementing without milestones (blocker, not warning).
    runner.invoke(app, ["phase", "designing", "--no-verify"])
    runner.invoke(app, ["phase", "poc", "--no-verify"])
    result = runner.invoke(app, ["phase", "implementing", "-y"])
    assert result.exit_code != 0
    assert "milestone" in result.stderr.lower()


# ---------------------------------------------------------------------------
# Task 2.2: --list-next flag
# ---------------------------------------------------------------------------


def test_phase_list_next_default(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    result = runner.invoke(app, ["phase", "--list-next", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    # Default lifecycle includes implicit cancelled edge
    assert data["current"] == "scoping"
    assert set(data["next"]) == {"designing", "cancelled"}


def test_phase_list_next_at_end(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    # Write done to the phase file directly (bypass transition validation)
    (proj / ".keel" / "phase").write_text("done\n")
    result = runner.invoke(app, ["phase", "--list-next", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    # Terminal state "done" still has implicit edge to "cancelled"
    assert data == {"current": "done", "next": ["cancelled"]}


# ---------------------------------------------------------------------------
# Task 5.1: FSM-based transitions using project's lifecycle
# ---------------------------------------------------------------------------


def test_phase_uses_project_lifecycle_for_transitions(projects, make_project, monkeypatch) -> None:
    """When the project picks a custom lifecycle, transitions follow that FSM."""
    lib = projects / ".keel" / "lifecycles"
    lib.mkdir(parents=True)
    (lib / "research.toml").write_text(
        """
name = "research"
initial = "proposing"
terminal = ["published", "cancelled"]
[states.proposing]
[states.reviewing]
[states.published]
[states.cancelled]
[transitions]
proposing = ["reviewing"]
reviewing = ["published", "proposing"]
""".strip()
    )
    monkeypatch.chdir(projects)
    runner.invoke(
        app, ["new", "alpha", "-d", "x", "--no-worktree", "-y", "--lifecycle", "research"]
    )
    monkeypatch.chdir(projects / "alpha")

    # Initial phase should be 'proposing'
    result = runner.invoke(app, ["phase", "--list-next", "--json"])
    data = json.loads(result.stdout)
    assert data["current"] == "proposing"
    # Cancelled is implicit (cancellable=true by default)
    assert set(data["next"]) == {"reviewing", "cancelled"}


def test_phase_list_next_branching(projects, make_project, monkeypatch) -> None:
    """A branching state shows multiple successors."""
    lib = projects / ".keel" / "lifecycles"
    lib.mkdir(parents=True)
    (lib / "branchy.toml").write_text(
        """
name = "branchy"
initial = "a"
terminal = ["c"]
[states.a]
[states.b]
[states.c]
[transitions]
a = ["b", "c"]
""".strip()
    )
    monkeypatch.chdir(projects)
    runner.invoke(app, ["new", "alpha", "-d", "x", "--no-worktree", "-y", "--lifecycle", "branchy"])
    monkeypatch.chdir(projects / "alpha")
    result = runner.invoke(app, ["phase", "--list-next", "--json"])
    data = json.loads(result.stdout)
    assert data["current"] == "a"
    assert set(data["next"]) == {"b", "c"}


def test_phase_rejects_invalid_target(projects, make_project, monkeypatch) -> None:
    """Trying to advance to a state not reachable from current fails."""
    lib = projects / ".keel" / "lifecycles"
    lib.mkdir(parents=True)
    (lib / "linear.toml").write_text(
        """
name = "linear"
initial = "a"
terminal = ["c"]
[states.a]
[states.b]
[states.c]
[transitions]
a = ["b"]
b = ["c"]
""".strip()
    )
    monkeypatch.chdir(projects)
    runner.invoke(app, ["new", "alpha", "-d", "x", "--no-worktree", "-y", "--lifecycle", "linear"])
    monkeypatch.chdir(projects / "alpha")
    # 'a' has no edge to 'c' — should fail
    result = runner.invoke(app, ["phase", "c", "--no-verify"])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Task 2.2: hook_event dispatch wiring + --no-verify flag
# ---------------------------------------------------------------------------


def test_phase_no_verify_skips_pre_hooks(projects, make_project, monkeypatch) -> None:
    """--no-verify bypasses pre-phase blockers."""
    from typer.testing import CliRunner

    from keel.app import app

    runner = CliRunner()
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    # Set phase to poc so transitioning to implementing triggers the
    # milestone-exists blocker (which would raise HookAborted).
    (proj / ".keel" / "phase").write_text("poc\n")

    # Without --no-verify: blocked
    result_block = runner.invoke(app, ["phase", "implementing", "-y"])
    assert result_block.exit_code != 0

    # With --no-verify: succeeds
    result_ok = runner.invoke(app, ["phase", "implementing", "-y", "--no-verify"])
    assert result_ok.exit_code == 0, result_ok.stderr


def test_phase_fires_post_phase_subscriber(projects, make_project, monkeypatch) -> None:
    """Successful transition fires post-phase subscribers."""
    from typer.testing import CliRunner

    from keel.app import app
    from keel.hooks import HookEvent, subscribes_to
    from keel.hooks.registry import _clear_registry

    _clear_registry()
    # Re-register builtins after clearing
    from keel.hooks.builtin_listeners import register_builtin_listeners

    register_builtin_listeners()

    captured: list[tuple[str | None, str | None]] = []

    @subscribes_to("project.phase.post")
    def capture(event: HookEvent, *, out) -> None:
        captured.append((event.payload.get("from"), event.payload.get("to")))

    runner = CliRunner()
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    # Edit scope.md so the scope-edited preflight passes
    (proj / "scope.md").write_text("# foo\n\nReal scope content.\n")

    result = runner.invoke(app, ["phase", "designing", "-y"])
    assert result.exit_code == 0, result.stderr
    assert captured == [("scoping", "designing")]


def test_phase_preflight_warning_still_prompts(projects, make_project, monkeypatch) -> None:
    """Subscribers that out.warn produce a confirmation prompt (preserved behavior)."""
    from typer.testing import CliRunner

    from keel.app import app

    runner = CliRunner()
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    # Leave scope.md as scaffold so scope-md-edited fires a warning
    from keel import templates

    (proj / "scope.md").write_text(templates.render("scope_md.j2", name="foo", description=""))

    # -y skips the prompt — must still succeed with warning
    result = runner.invoke(app, ["phase", "designing", "-y"])
    assert result.exit_code == 0
    assert "scope.md is still the template scaffold" in result.stderr
