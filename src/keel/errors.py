"""Error codes and hint constants used across commands."""

from __future__ import annotations

from enum import StrEnum

# Standard hint texts used across commands.
HINT_LIST_PROJECTS = "Hint: run 'keel list' to see available projects."
HINT_LIST_DELIVERABLES = "Hint: run 'keel deliverable list' to see existing deliverables."
HINT_LIST_DECISIONS = "Hint: run 'keel decision list' to see existing decisions."
HINT_PASS_PROJECT = "Hint: pass --project NAME or run from inside a project's directory."


class ErrorCode(StrEnum):
    """Standard error codes emitted in `out.error(..., code=...)` calls.

    Stable across minor releases — plugin authors and JSON-mode consumers
    can rely on these strings.
    """

    INVALID_NAME = "invalid_name"
    NOT_FOUND = "not_found"
    EXISTS = "exists"
    NO_PROJECT = "no_project"
    NOT_A_REPO = "not_a_repo"
    GIT_FAILED = "git_failed"
    INVALID_PHASE = "invalid_phase"
    DUPLICATE_REMOTE = "duplicate_remote"
    DUPLICATE_WORKTREE = "duplicate_worktree"
    SOURCE_MISSING = "source_missing"
    CLONE_FAILED = "clone_failed"
    CONFLICTING_FLAGS = "conflicting_flags"
    INVALID_TITLE = "invalid_title"
    BAD_SHELL = "bad_shell"
    END_OF_LIFECYCLE = "end_of_lifecycle"
    INVALID_STATE = "invalid_state"
    VALIDATION = "validation"
    PREFLIGHT_BLOCKED = "preflight_blocked"
