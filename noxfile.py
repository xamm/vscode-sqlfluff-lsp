# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
"""All the action we need during build."""

import os
import pathlib
import shutil
import tempfile

import nox

BUNDLE_ROOT = pathlib.Path(__file__).parent / "bundled"
BUNDLED_PROTOCOL = BUNDLE_ROOT / "protocol"


def _install_bundle(session: nox.Session) -> None:
    """Vendor the pure-Python LSP runtime used with environment SQLFluff."""
    shutil.rmtree(BUNDLED_PROTOCOL, ignore_errors=True)
    BUNDLED_PROTOCOL.mkdir(parents=True)
    with tempfile.TemporaryDirectory() as temp_dir:
        export_file = pathlib.Path(temp_dir) / "bundle-export.txt"
        session.run(
            "uv",
            "export",
            "--locked",
            "--no-dev",
            "--prune",
            "mcp",
            "--prune",
            "sqlfluff",
            "--no-emit-project",
            "--output-file",
            os.fspath(export_file),
            external=True,
        )
        session.run(
            "uv",
            "pip",
            "install",
            "--target",
            os.fspath(BUNDLED_PROTOCOL),
            "--no-deps",
            "-r",
            os.fspath(export_file),
            external=True,
        )


def _sync_project(session: nox.Session, *groups: str) -> None:
    """Syncs the uv project lock into the isolated session environment."""
    command = [
        "uv",
        "sync",
        "--locked",
        "--no-dev",
        "--extra",
        "dbt",
        f"--python={session.virtualenv.location}",
    ]
    for group in groups:
        command.extend(["--group", group])
    session.run_install(
        *command,
        env={"UV_PROJECT_ENVIRONMENT": session.virtualenv.location},
    )


@nox.session(venv_backend="none")
def setup(session: nox.Session) -> None:
    """Sets up the template for development."""
    _install_bundle(session)


@nox.session(venv_backend="uv", python=["3.10", "3.14"])
def tests(session: nox.Session) -> None:
    """Runs all the tests for the extension."""
    _install_bundle(session)
    _sync_project(session, "test")
    session.run("pytest", "src/test/python_tests")


@nox.session(venv_backend="uv")
def lint(session: nox.Session) -> None:
    """Runs linter and formatter checks on python files."""
    _sync_project(session, "test", "lint")
    python_paths = [
        "./bundled/tool",
        "./sqlfluff_lsp",
        "./src/test/python_tests",
        "noxfile.py",
    ]
    session.run("ruff", "check", *python_paths)
    session.run(
        "ruff",
        "format",
        "--check",
        *python_paths,
    )
    session.run("pyright")

    # check typescript code
    session.run("npm", "run", "lint", external=True)
