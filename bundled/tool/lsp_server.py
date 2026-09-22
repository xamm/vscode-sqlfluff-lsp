# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
"""Compatibility launcher for the packaged SQLFluff language server."""

from __future__ import annotations

import importlib
import os
import pathlib
import sys

repo_root = pathlib.Path(__file__).resolve().parents[2]
bundled_root = pathlib.Path(__file__).parent.parent
protocol_path = bundled_root / "protocol"
if protocol_path.is_dir():
    sys.path.insert(0, os.fspath(protocol_path))

if os.fspath(repo_root) not in sys.path:
    sys.path.insert(0, os.fspath(repo_root))


def main() -> None:
    """Load the server only after its protocol paths are configured."""
    server = importlib.import_module("sqlfluff_lsp.lsp_server")
    server.main()


if __name__ == "__main__":
    main()
