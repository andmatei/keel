"""Test fixtures sourced from keel.testing (the same fixtures plugin authors get)."""

from typer.testing import CliRunner

import pytest

pytest_plugins = ["keel.testing"]


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()
