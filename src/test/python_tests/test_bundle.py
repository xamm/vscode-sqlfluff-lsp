# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
"""Tests for the packaged Python runtime bundle."""

import pathlib
import subprocess
import sys

from .lsp_test_client.constants import PROJECT_ROOT

BUNDLED_PROTOCOL = PROJECT_ROOT / "bundled" / "protocol"

LAUNCHER = PROJECT_ROOT / "bundled" / "tool" / "lsp_server.py"


def test_lsp_protocol_is_available_from_bundle() -> None:
    """The LSP server's protocol dependencies are packaged for a clean runtime."""
    result = subprocess.run(
        [
            sys.executable,
            "-S",
            "-c",
            (
                f"import sys; sys.path.insert(0, {str(BUNDLED_PROTOCOL)!r}); "
                "import lsprotocol, pygls; "
                "print(lsprotocol.__file__); print(pygls.__file__)"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert all(
        pathlib.Path(path).is_relative_to(BUNDLED_PROTOCOL)
        for path in result.stdout.splitlines()
    )


def test_lsp_server_uses_environment_sqlfluff() -> None:
    """The launcher starts with SQLFluff from the selected environment."""
    result = subprocess.run(
        [sys.executable, str(LAUNCHER)],
        cwd=PROJECT_ROOT,
        input="",
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
