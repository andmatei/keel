"""Smoke tests for the public API surface.

Anything imported here is considered stable across minor releases.
"""


def test_keel_api_exports() -> None:
    """The public API surface is importable and contains the expected names."""
    import keel.api as api

    expected = {
        # Manifest
        "ProjectManifest",
        "ProjectMeta",
        "RepoSpec",
        "load_project_manifest",
        "save_project_manifest",
        # Dryrun
        "Op",
        "OpLog",
        # Output
        "Output",
        # Prompts
        "confirm_destructive",
        "is_interactive",
        "require_or_fail",
        # Util
        "slugify",
        # Workspace
        "Scope",
        "deliverable_dir",
        "deliverable_exists",
        "detect_scope",
        "project_dir",
        "project_exists",
        "projects_dir",
        "read_phase",
    }
    actual = set(api.__all__)
    missing = expected - actual
    assert not missing, f"missing public exports: {missing}"


def test_keel_api_imports_resolve() -> None:
    """Every name in keel.api.__all__ resolves to an actual object."""
    import keel.api as api

    for name in api.__all__:
        assert hasattr(api, name), f"name in __all__ but not exported: {name}"
