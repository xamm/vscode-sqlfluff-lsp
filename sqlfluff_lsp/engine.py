"""Persistent in-process SQLFluff engine shared by the LSP and MCP frontends."""

from __future__ import annotations

import importlib.util
import logging
import os
import threading
import traceback
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from sqlfluff.core import Linter
from sqlfluff.core.config import FluffConfig
from sqlfluff.core.errors import SQLFluffUserError
from sqlfluff.core.linter.discovery import paths_from_path

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class Violation:
    """A SQLFluff violation in source-file coordinates."""

    code: str
    description: str
    name: str
    line: int
    column: int
    warning: bool
    fixable: bool

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON-compatible representation used by frontends."""
        return asdict(self)


class EngineError(Exception):
    """A user-facing SQLFluff setup or configuration error."""


class Engine:
    """Own one SQLFluff linter and serialize all work through it.

    SQLFluff's dbt templater temporarily changes global Jinja state and uses
    dbt context variables. Keeping this lock around the complete operation
    prevents concurrent LSP requests from corrupting that shared state.
    """

    def __init__(self, root: Path, overrides: dict[str, str] | None = None):
        self.root = Path(root).expanduser().resolve()
        self.overrides = dict(overrides or {})
        self._lock = threading.RLock()
        self._linter: Linter | None = None
        self._root_config = self._build_config()

    def _build_config(self) -> FluffConfig:
        """Load project configuration and enable the optional Rust parser."""
        try:
            os.chdir(self.root)
            config = FluffConfig.from_root(
                overrides=self.overrides or None,
                require_dialect=False,
            )
            if (
                config.get("use_rust_parser", default=None) is None
                and importlib.util.find_spec("sqlfluffrs") is not None
            ):
                rust_overrides = {**self.overrides, "use_rust_parser": "auto"}
                config = FluffConfig.from_root(
                    overrides=rust_overrides,
                    require_dialect=False,
                )
            return config
        except SQLFluffUserError as error:
            raise EngineError(str(error)) from error
        except OSError as error:
            raise EngineError(
                f"Unable to use project root {self.root}: {error}"
            ) from error

    def _get_linter(self) -> Linter:
        if self._linter is None:
            self._linter = Linter(config=self._root_config)
        return self._linter

    @staticmethod
    def _violation(error: Any) -> Violation:
        data = error.to_dict()
        return Violation(
            code=str(data.get("code", "")),
            description=str(data.get("description", "")),
            name=str(data.get("name", "")),
            line=max(int(data.get("start_line_no", 1)), 1),
            column=max(int(data.get("start_line_pos", 1)), 1),
            warning=bool(data.get("warning", False)),
            fixable=bool(error.fixable),
        )

    def _lint_string_locked(
        self, sql: str, path: Path, fix: bool = False
    ) -> tuple[Any, list[Violation]]:
        file_path = Path(path).expanduser()
        try:
            file_config = self._root_config.make_child_from_path(str(file_path))
            linted = self._get_linter().lint_string(
                in_str=sql,
                fname=str(file_path),
                fix=fix,
                config=file_config,
            )
            violations = [
                self._violation(error)
                for error in linted.get_violations(
                    filter_ignore=True,
                    filter_warning=False,
                )
            ]
            return linted, violations
        except SQLFluffUserError as error:
            raise EngineError(str(error)) from error
        except Exception:  # noqa: BLE001 - preserve frontend resilience
            LOGGER.error("SQLFluff operation failed for %s", file_path)
            LOGGER.error(traceback.format_exc())
            return None, []

    def lint(self, sql: str, path: Path) -> list[Violation]:
        """Lint an in-memory source buffer using its real filesystem path."""
        with self._lock:
            _, violations = self._lint_string_locked(sql, path)
            return violations

    def fix(self, sql: str, path: Path) -> tuple[str, bool, list[Violation]]:
        """Return fixed source, whether it changed, and initial violations."""
        with self._lock:
            linted, violations = self._lint_string_locked(sql, path, fix=True)
            if linted is None:
                return sql, False, violations
            try:
                fixed_source, changed = linted.fix_string()
            except AssertionError:
                LOGGER.error("SQLFluff could not map fixes back to %s", path)
                return sql, False, violations
            return fixed_source, changed, violations

    def lint_file(self, path: Path) -> list[Violation]:
        """Read and lint a UTF-8 file."""
        file_path = Path(path).expanduser()
        try:
            source = file_path.read_text(encoding="utf-8")
        except OSError as error:
            raise EngineError(f"Unable to read {file_path}: {error}") from error
        return self.lint(source, file_path)

    def fix_file(self, path: Path, apply: bool) -> tuple[str, bool, list[Violation]]:
        """Fix a UTF-8 file, optionally persisting the changed source."""
        file_path = Path(path).expanduser()
        try:
            source = file_path.read_text(encoding="utf-8")
        except OSError as error:
            raise EngineError(f"Unable to read {file_path}: {error}") from error
        fixed_source, changed, violations = self.fix(source, file_path)
        if apply and changed:
            try:
                file_path.write_text(fixed_source, encoding="utf-8")
            except OSError as error:
                raise EngineError(f"Unable to write {file_path}: {error}") from error
        return fixed_source, changed, violations

    def expand(self, paths: list[str]) -> list[Path]:
        """Expand files and directories while respecting SQLFluff ignore files."""
        with self._lock:
            extensions = self._root_config.get("sql_file_exts", default=".sql")
            target_extensions = tuple(
                extension.strip().lower()
                for extension in str(extensions).split(",")
                if extension.strip()
            )
            requested_paths = paths or [str(self.root)]
            expanded: list[Path] = []
            for path in requested_paths:
                expanded.extend(
                    Path(expanded_path)
                    for expanded_path in paths_from_path(
                        path,
                        target_file_exts=target_extensions,
                        working_path=str(self.root),
                    )
                )
            return expanded

    def reload(self) -> None:
        """Drop cached SQLFluff objects and reload project configuration."""
        with self._lock:
            self._linter = None
            self._root_config = self._build_config()


__all__ = ["Engine", "EngineError", "Violation"]
