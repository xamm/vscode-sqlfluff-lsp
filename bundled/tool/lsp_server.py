# ruff: noqa: E402
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
"""Compatibility launcher for the packaged SQLFluff language server."""

from __future__ import annotations

import os
import pathlib
import sys


def update_sys_path(path_to_add: str, strategy: str) -> None:
    """Add a bundled dependency directory according to the extension setting."""
    if path_to_add not in sys.path and os.path.isdir(path_to_add):
        if strategy == "useBundled":
            sys.path.insert(0, path_to_add)
        elif strategy == "fromEnvironment":
            sys.path.append(path_to_add)


update_sys_path(
    os.fspath(pathlib.Path(__file__).parent.parent / "libs"),
    os.getenv("LS_IMPORT_STRATEGY", "useBundled"),
)

repo_root = pathlib.Path(__file__).resolve().parents[2]
if os.fspath(repo_root) not in sys.path:
    sys.path.insert(0, os.fspath(repo_root))

# pylint: disable=wrong-import-position,import-error
from sqlfluff_lsp.lsp_server import main  # noqa: E402

if __name__ == "__main__":
    main()
