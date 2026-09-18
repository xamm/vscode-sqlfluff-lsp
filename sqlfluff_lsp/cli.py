"""Command-line entrypoints for the SQLFluff LSP and MCP servers."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from . import __version__


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the SQLFluff language server.")
    parser.add_argument("--dialect", help="Override the SQLFluff dialect.")
    parser.add_argument("--templater", help="Override the SQLFluff templater.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    """Run the SQLFluff language server over stdio."""
    args = _parse_args(argv)
    from .lsp_server import main as run_server

    overrides = {
        key: value
        for key, value in {
            "dialect": args.dialect,
            "templater": args.templater,
        }.items()
        if value is not None
    }
    run_server(overrides=overrides)


def mcp_main() -> None:
    """Run the SQLFluff MCP server over stdio."""
    from .mcp_server import run

    run()


__all__ = ["__version__", "main", "mcp_main"]
