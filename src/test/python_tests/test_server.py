# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
"""Integration tests for the SQLFluff language server."""

from threading import Event

from hamcrest import assert_that, has_entry, has_item, has_length, is_, starts_with

from .lsp_test_client import constants, session, utils

DBT_ROOT = constants.TEST_DATA / "dbt_project"
TEST_FILE_PATH = DBT_ROOT / "models" / "stg_customers.sql"
TEST_FILE_URI = utils.as_uri(str(TEST_FILE_PATH))
TIMEOUT = 15


def _initialize_params() -> dict:
    return {
        "processId": None,
        "rootPath": str(DBT_ROOT),
        "rootUri": utils.as_uri(str(DBT_ROOT)),
        "capabilities": {},
        "initializationOptions": {"dialect": "duckdb", "templater": "dbt"},
    }


def test_linting_dbt_model() -> None:
    """didOpen publishes source-position diagnostics from the dbt model."""
    contents = TEST_FILE_PATH.read_text(encoding="utf-8")
    actual: list[dict] = []
    done = Event()

    with session.LspSession(cwd=DBT_ROOT) as ls_session:
        ls_session.initialize(_initialize_params())

        def _handler(params):
            actual.append(params)
            done.set()

        ls_session.set_notification_callback(session.PUBLISH_DIAGNOSTICS, _handler)
        ls_session.notify_did_open(
            {
                "textDocument": {
                    "uri": TEST_FILE_URI,
                    "languageId": "sql",
                    "version": 1,
                    "text": contents,
                }
            }
        )
        assert done.wait(TIMEOUT)

    assert_that(actual, has_length(1))
    diagnostics = actual[0]["diagnostics"]
    assert_that(diagnostics, has_item(has_entry("source", "sqlfluff")))
    assert {diagnostic["code"] for diagnostic in diagnostics} & {"LT09", "AL01"}
    assert all(
        diagnostic["range"]["start"]["line"] >= 0
        and diagnostic["range"]["start"]["character"] >= 0
        for diagnostic in diagnostics
    )


def test_formatting_dbt_model() -> None:
    """Formatting returns one whole-document source-preserving edit."""
    contents = TEST_FILE_PATH.read_text(encoding="utf-8")
    with session.LspSession(cwd=DBT_ROOT) as ls_session:
        ls_session.initialize(_initialize_params())
        ls_session.notify_did_open(
            {
                "textDocument": {
                    "uri": TEST_FILE_URI,
                    "languageId": "sql",
                    "version": 1,
                    "text": contents,
                }
            }
        )
        edits = ls_session.text_document_formatting(
            {
                "textDocument": {"uri": TEST_FILE_URI},
                "options": {"tabSize": 4, "insertSpaces": True},
            }
        )

    assert_that(edits, has_length(1))
    assert_that(edits[0]["range"]["start"], is_({"line": 0, "character": 0}))
    assert_that(edits[0]["newText"], starts_with("select\n"))
    assert "{{ ref('raw_customers') }}" in edits[0]["newText"]
