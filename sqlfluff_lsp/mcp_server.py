"""Agent-oriented MCP tools backed by the persistent SQLFluff engine."""

from __future__ import annotations

import difflib
import importlib
import json
from pathlib import Path
from typing import Any

try:  # MCP 1.x exposes FastMCP in this module.
    FastMCP = importlib.import_module("mcp.server.fastmcp").FastMCP
except ModuleNotFoundError:  # MCP 2.x renamed FastMCP to MCPServer.
    FastMCP = importlib.import_module("mcp.server").MCPServer

from .engine import Engine, EngineError

mcp = FastMCP("sqlfluff")

ENGINE: Engine | None = None


def _get_engine() -> Engine:
    global ENGINE
    if ENGINE is None:
        ENGINE = Engine(Path.cwd())
    return ENGINE


def _tool_error(error: EngineError) -> str:
    return json.dumps({"error": str(error)})


def _summary(files: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "files_linted": len(files),
        "files_with_violations": sum(bool(item["violations"]) for item in files),
        "total_violations": sum(len(item["violations"]) for item in files),
    }


@mcp.tool()
def lint(paths: list[str]) -> str:
    """Lint SQL files or directories using project config in the current directory.

    The dbt templater is supported. The first call in a dbt project compiles its
    manifest and can take seconds; later calls reuse the persistent manifest and
    are fast. Violation lines and columns are 1-based source positions.
    """
    try:
        engine = _get_engine()
        files = []
        for path in engine.expand(paths):
            violations = engine.lint_file(path)
            files.append(
                {
                    "filepath": str(path),
                    "violations": [violation.to_dict() for violation in violations],
                }
            )
        return json.dumps({"files": files, "summary": _summary(files)})
    except EngineError as error:
        return _tool_error(error)


@mcp.tool()
def fix(paths: list[str], apply: bool = False) -> str:
    """Preview or apply SQLFluff fixes for files or directories.

    Project config comes from the current directory and dbt templating is
    supported. The default dry-run returns unified diffs without changing files;
    pass ``apply=true`` to persist only files with actual source changes. The
    first dbt call can compile a manifest and later calls reuse it. Violation
    lines and columns are 1-based source positions.
    """
    try:
        engine = _get_engine()
        files = []
        for path in engine.expand(paths):
            original = path.read_text(encoding="utf-8")
            fixed, changed, violations = engine.fix_file(path, apply=apply)
            diff = "".join(
                difflib.unified_diff(
                    original.splitlines(keepends=True),
                    fixed.splitlines(keepends=True),
                    fromfile=str(path),
                    tofile=str(path),
                )
            )
            files.append(
                {
                    "filepath": str(path),
                    "changed": changed,
                    "diff": diff,
                    "violations": [violation.to_dict() for violation in violations],
                }
            )
        result = {
            "files": files,
            "summary": {
                **_summary(files),
                "files_changed": sum(item["changed"] for item in files),
            },
        }
        return json.dumps(result)
    except EngineError as error:
        return _tool_error(error)


@mcp.tool()
def reload() -> str:
    """Drop cached SQLFluff config and dbt manifest before the next call."""
    try:
        _get_engine().reload()
    except EngineError as error:
        return _tool_error(error)
    return "reloaded; dbt manifest and config rebuild on next use"


def run() -> None:
    """Run the MCP server over stdio."""
    mcp.run()


__all__ = ["ENGINE", "fix", "lint", "mcp", "reload", "run"]
