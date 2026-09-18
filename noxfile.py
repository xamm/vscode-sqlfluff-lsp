# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
"""All the action we need during build"""

import json
import os
import pathlib
import tempfile
import urllib.request as url_lib
from typing import List

import nox  # pylint: disable=import-error


def _install_bundle(session: nox.Session) -> None:
    """Vendors the locked runtime dependencies for the extension bundle."""
    with tempfile.TemporaryDirectory() as temp_dir:
        export_file = pathlib.Path(temp_dir) / "bundle-export.txt"
        session.run(
            "uv",
            "export",
            "--locked",
            "--no-dev",
            "--extra",
            "dbt",
            "--no-emit-project",
            "--output-file",
            os.fspath(export_file),
            external=True,
        )
        session.run(
            "uv",
            "pip",
            "install",
            "--python",
            "3.10",
            "--target",
            "./bundled/libs",
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


def _check_files(names: List[str]) -> None:
    root_dir = pathlib.Path(__file__).parent
    for name in names:
        file_path = root_dir / name
        lines: List[str] = file_path.read_text().splitlines()
        if any(line for line in lines if line.startswith("# TODO:")):
            raise Exception(  # pylint: disable=broad-exception-raised
                f"Please update {os.fspath(file_path)}."
            )


def _get_package_data(package):
    json_uri = f"https://registry.npmjs.org/{package}"
    with url_lib.urlopen(json_uri) as response:
        return json.loads(response.read())


def _update_npm_packages(session: nox.Session) -> None:
    pinned = {
        "vscode-languageclient",
        "@types/vscode",
        "@types/node",
    }
    package_json_path = pathlib.Path(__file__).parent / "package.json"
    package_json = json.loads(package_json_path.read_text(encoding="utf-8"))

    for package in package_json["dependencies"]:
        if package not in pinned:
            data = _get_package_data(package)
            latest = "^" + data["dist-tags"]["latest"]
            package_json["dependencies"][package] = latest

    for package in package_json["devDependencies"]:
        if package not in pinned:
            data = _get_package_data(package)
            latest = "^" + data["dist-tags"]["latest"]
            package_json["devDependencies"][package] = latest

    # Ensure engine matches the package
    if (
        package_json["engines"]["vscode"]
        != package_json["devDependencies"]["@types/vscode"]
    ):
        print(
            "Please check VS Code engine version and @types/vscode version in package.json."
        )

    new_package_json = json.dumps(package_json, indent=4)
    # JSON dumps uses \n for line ending on all platforms by default
    if not new_package_json.endswith("\n"):
        new_package_json += "\n"
    package_json_path.write_text(new_package_json, encoding="utf-8")
    session.run("npm", "install", external=True)


@nox.session(venv_backend="none")
def setup(session: nox.Session) -> None:
    """Sets up the template for development."""
    _install_bundle(session)


@nox.session(venv_backend="uv", python=["3.10", "3.14"])
def tests(session: nox.Session) -> None:
    """Runs all the tests for the extension."""
    _sync_project(session, "test")
    session.run("pytest", "src/test/python_tests")


@nox.session(venv_backend="uv")
def lint(session: nox.Session) -> None:
    """Runs linter and formatter checks on python files."""
    _sync_project(session, "test", "lint")
    session.run("pylint", "-d", "W0511", "./bundled/tool")
    session.run(
        "pylint",
        "-d",
        "W0511",
        "--ignore=./src/test/python_tests/test_data",
        "./src/test/python_tests",
    )
    session.run("pylint", "-d", "W0511", "noxfile.py")

    # check formatting using black
    session.run("black", "--check", "./bundled/tool")
    session.run("black", "--check", "./sqlfluff_lsp")
    session.run("black", "--check", "./src/test/python_tests")
    session.run("black", "--check", "noxfile.py")

    # check import sorting using isort
    session.run("isort", "--profile", "black", "--check", "./bundled/tool")
    session.run("isort", "--profile", "black", "--check", "./sqlfluff_lsp")
    session.run("isort", "--profile", "black", "--check", "./src/test/python_tests")
    session.run("isort", "--profile", "black", "--check", "noxfile.py")

    # check typescript code
    session.run("npm", "run", "lint", external=True)


@nox.session(venv_backend="none")
def build_package(session: nox.Session) -> None:
    """Builds VSIX package for publishing."""
    _check_files(["README.md", "LICENSE", "SECURITY.md", "SUPPORT.md"])
    _install_bundle(session)
    session.run("npm", "install", external=True)
    session.run("npm", "run", "vsce-package", external=True)


@nox.session(venv_backend="none")
def update_packages(session: nox.Session) -> None:
    """Update locked Python and npm packages."""
    session.run("uv", "lock", "--upgrade", external=True)
    _update_npm_packages(session)
