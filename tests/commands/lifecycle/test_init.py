"""Tests for `keel lifecycle init`."""

from typer.testing import CliRunner

from keel.app import app

runner = CliRunner()


def test_init_creates_template_in_user_library(projects) -> None:
    result = runner.invoke(app, ["lifecycle", "init", "research"])
    assert result.exit_code == 0
    target = projects / ".keel" / "lifecycles" / "research.toml"
    assert target.is_file()
    text = target.read_text()
    assert 'name = "research"' in text


def test_init_refuses_to_overwrite(projects) -> None:
    """A second `init` of the same name fails unless --force."""
    runner.invoke(app, ["lifecycle", "init", "research"])
    result = runner.invoke(app, ["lifecycle", "init", "research"])
    assert result.exit_code != 0


def test_init_rejects_path_name(projects) -> None:
    result = runner.invoke(app, ["lifecycle", "init", "../outside"])
    assert result.exit_code == 2
    assert not (projects / ".keel" / "outside.toml").exists()


def test_init_force_overwrites(projects) -> None:
    runner.invoke(app, ["lifecycle", "init", "research"])
    target = projects / ".keel" / "lifecycles" / "research.toml"
    target.write_text("# user edits")
    result = runner.invoke(app, ["lifecycle", "init", "research", "--force"])
    assert result.exit_code == 0
    assert "user edits" not in target.read_text()


def test_init_validates_after_writing(projects) -> None:
    """The scaffolded file should pass `keel lifecycle validate`."""
    runner.invoke(app, ["lifecycle", "init", "research"])
    target = projects / ".keel" / "lifecycles" / "research.toml"
    result = runner.invoke(app, ["lifecycle", "validate", str(target)])
    assert result.exit_code == 0
