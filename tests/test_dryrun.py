"""Tests for the dry-run op tracker."""

from pathlib import Path

from keel.dryrun import OpLog


def test_op_log_records_creates() -> None:
    log = OpLog()
    log.create_file(Path("/p/a.md"), size=100)
    log.create_file(Path("/p/b.md"), size=50)
    assert len(log.ops) == 2
    assert log.ops[0].kind == "create"


def test_op_log_records_modifies_with_diff() -> None:
    log = OpLog()
    log.modify_file(Path("/p/x.md"), diff="+ added line\n")
    assert log.ops[0].kind == "modify"
    assert log.ops[0].diff == "+ added line\n"


def test_op_log_records_git() -> None:
    log = OpLog()
    log.create_worktree(Path("/p/code"), source=Path("/repo"), branch="me/foo")
    assert log.ops[0].kind == "git-worktree-create"


def test_format_summary_groups_by_kind() -> None:
    log = OpLog()
    log.create_file(Path("/p/a"), size=10)
    log.create_file(Path("/p/b"), size=20)
    log.modify_file(Path("/p/c"), diff="+ x\n")
    out = log.format_summary()
    assert "Would create:" in out
    assert "Would modify:" in out
    assert "/p/a" in out
    assert "/p/c" in out
