# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
"""Tests for the persistent SQLFluff engine."""

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import Mock

import pytest

from sqlfluff_lsp.engine import Engine, EngineError

DBT_ROOT = Path(__file__).parent / "test_data" / "dbt_project"


@pytest.fixture(autouse=True)
def reset_dbt_fixture() -> Iterator[None]:
    """Restore the source fixture even when a test aborts during fixing."""
    path = DBT_ROOT / "models" / "stg_customers.sql"
    source = "select a,b from {{ ref('raw_customers') }}\n"
    path.write_text(source, encoding="utf-8")
    yield
    path.write_text(source, encoding="utf-8")


def test_non_dbt_lint_and_fix(tmp_path: Path) -> None:
    """Lint and fix an in-memory SQL buffer from a configured project."""
    (tmp_path / ".sqlfluff").write_text("[sqlfluff]\ndialect = ansi\n")
    path = tmp_path / "query.sql"
    source = "select a,b from t"
    engine = Engine(tmp_path)

    violations = engine.lint(source, path)
    fixed, changed, initial = engine.fix(source, path)

    assert violations
    assert any(violation.code == "LT09" for violation in violations)
    assert changed
    assert fixed != source
    assert [violation.code for violation in initial] == [
        violation.code for violation in violations
    ]


def test_no_dialect_raises_engine_error(tmp_path: Path) -> None:
    """A missing dialect is reported as a frontend-safe engine error."""
    engine = Engine(tmp_path)
    with pytest.raises(EngineError):
        engine.lint("select 1", tmp_path / "query.sql")


def test_warning_violations_are_retained(tmp_path: Path) -> None:
    """Rules configured as warnings remain available to all frontends."""
    (tmp_path / ".sqlfluff").write_text("[sqlfluff]\ndialect = ansi\nwarnings = LT09\n")
    engine = Engine(tmp_path)
    violations = engine.lint("select a,b from t", tmp_path / "query.sql")
    assert any(
        violation.code == "LT09" and violation.warning for violation in violations
    )


def test_duplicate_violations_are_removed() -> None:
    """Visually identical SQLFluff results produce one frontend violation."""
    error = Mock(fixable=True)
    error.to_dict.return_value = {
        "code": "CP01",
        "description": "Keywords must be upper case.",
        "name": "capitalisation.keywords",
        "start_line_no": 1,
        "start_line_pos": 1,
    }

    violations = Engine._unique_violations([error, error])

    assert len(violations) == 1
    assert violations[0].code == "CP01"


def test_dbt_lint_fix_and_cached_reload() -> None:
    """Lint, dry-run fix, apply fix, warm reuse, and reload a dbt model."""
    path = DBT_ROOT / "models" / "stg_customers.sql"
    original = path.read_text(encoding="utf-8")
    engine = Engine(DBT_ROOT)

    violations = engine.lint_file(path)
    assert violations
    assert all(v.line >= 1 and v.column >= 1 for v in violations)

    fixed, changed, _ = engine.fix_file(path, apply=False)
    assert changed
    assert "{{ ref('raw_customers') }}" in fixed
    assert path.read_text(encoding="utf-8") == original

    warm = engine.lint_file(path)
    assert [v.code for v in warm] == [v.code for v in violations]

    engine.reload()
    reloaded = engine.lint_file(path)
    assert [v.code for v in reloaded] == [v.code for v in warm]

    fixed_applied, applied_changed, _ = engine.fix_file(path, apply=True)
    assert applied_changed
    assert path.read_text(encoding="utf-8") == fixed_applied
    assert "{{ ref('raw_customers') }}" in fixed_applied

    path.write_text(original, encoding="utf-8")


def test_expand_respects_sqlfluffignore() -> None:
    """Directory expansion returns SQL files but skips ignored targets."""
    engine = Engine(DBT_ROOT)
    paths = engine.expand([str(DBT_ROOT)])
    assert DBT_ROOT / "models" / "stg_customers.sql" in paths
    assert all("target" not in path.parts for path in paths)
