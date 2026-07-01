"""Jinja2 template loader/renderer for design artifacts."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING

from jinja2 import (
    BaseLoader,
    ChoiceLoader,
    Environment,
    FileSystemLoader,
    TemplateNotFound,
    select_autoescape,
)

if TYPE_CHECKING:
    from keel.workspace import Scope


class _PackageLoader(BaseLoader):
    """Loads templates from the `_templates/` resource dir of this package."""

    def get_source(self, environment, template):
        try:
            data = (files("keel") / "_templates" / template).read_text()
        except FileNotFoundError as e:
            raise TemplateNotFound(template) from e
        return data, template, lambda: True


def _make_env(search_dirs: list[Path] | None = None) -> Environment:
    """Build a Jinja2 Environment with an optional filesystem override layer.

    If *search_dirs* is provided, existing directories are searched first via
    ``FileSystemLoader``; the package-bundled ``_PackageLoader`` is always the
    final fallback.
    """
    existing_dirs = [d for d in (search_dirs or []) if d.is_dir()]

    if existing_dirs:
        loader: BaseLoader = ChoiceLoader(
            [FileSystemLoader([str(d) for d in existing_dirs]), _PackageLoader()]
        )
    else:
        loader = _PackageLoader()

    return Environment(
        loader=loader,
        autoescape=select_autoescape(default=False),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render(template: str, *, search_dirs: list[Path] | None = None, **context) -> str:
    """Render *template* with *context*.

    If *search_dirs* is given, existing directories in that list are searched
    before the package-bundled defaults.
    """
    return _make_env(search_dirs).get_template(template).render(**context)


def render_for_scope(template: str, scope: Scope, **context) -> str:
    """Render *template* with per-scope override resolution.

    Search order:
    1. ``<unit_dir>/.keel/templates/`` (project- or deliverable-level override)
    2. ``<projects_dir>/.keel/templates/`` (workspace-level override)
    3. Package-bundled default

    Only directories that actually exist on disk are consulted.
    """
    from keel.workspace import projects_dir

    search_dirs = [
        scope.unit_dir / ".keel" / "templates",
        projects_dir() / ".keel" / "templates",
    ]
    return render(template, search_dirs=search_dirs, **context)
