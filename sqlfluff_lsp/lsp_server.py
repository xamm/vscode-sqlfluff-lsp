"""SQLFluff language server backed by a persistent in-process engine."""

from __future__ import annotations

import logging
import os
import pathlib
import threading
import traceback
from typing import Any

from lsprotocol import types as lsp
from pygls import uris, workspace
from pygls.lsp.server import LanguageServer

from . import __version__
from .engine import Engine, EngineError

LOGGER = logging.getLogger(__name__)

MAX_WORKERS = 5
LSP_SERVER = LanguageServer(
    name="sqlfluff",
    version=__version__,
    max_workers=MAX_WORKERS,
    text_document_sync_kind=lsp.TextDocumentSyncKind.Full,
)
ENGINE: Engine | None = None
DIAGNOSTIC_SEVERITY = "warning"
DEBOUNCE_TIMERS: dict[str, threading.Timer] = {}
DEBOUNCE_LOCK = threading.RLock()


def log_to_output(
    message: str, msg_type: lsp.MessageType = lsp.MessageType.Log
) -> None:
    """Send a message to the connected LSP client."""
    LSP_SERVER.window_log_message(lsp.LogMessageParams(type=msg_type, message=message))


def log_error(message: str) -> None:
    """Log an error and optionally show it as a client notification."""
    log_to_output(message, lsp.MessageType.Error)
    if os.getenv("LS_SHOW_NOTIFICATION", "off") in {"onError", "onWarning", "always"}:
        LSP_SERVER.window_show_message(
            lsp.ShowMessageParams(type=lsp.MessageType.Error, message=message)
        )


def log_warning(message: str) -> None:
    """Log a warning and optionally show it as a client notification."""
    log_to_output(message, lsp.MessageType.Warning)
    if os.getenv("LS_SHOW_NOTIFICATION", "off") in {"onWarning", "always"}:
        LSP_SERVER.window_show_message(
            lsp.ShowMessageParams(type=lsp.MessageType.Warning, message=message)
        )


def log_always(message: str) -> None:
    """Log an informational message and optionally notify the client."""
    log_to_output(message, lsp.MessageType.Info)
    if os.getenv("LS_SHOW_NOTIFICATION", "off") == "always":
        LSP_SERVER.window_show_message(
            lsp.ShowMessageParams(type=lsp.MessageType.Info, message=message)
        )


def _get_severity(severity: str) -> lsp.DiagnosticSeverity:
    """Map the configured diagnostic severity to an LSP enum."""
    severities = {
        "error": lsp.DiagnosticSeverity.Error,
        "warning": lsp.DiagnosticSeverity.Warning,
        "information": lsp.DiagnosticSeverity.Information,
        "hint": lsp.DiagnosticSeverity.Hint,
    }
    try:
        return severities[severity]
    except KeyError as error:
        raise ValueError(f"Unknown diagnostic severity: {severity}") from error


def _get_line_endings(lines: list[str]) -> str | None:
    """Return the first line-ending style found in the source."""
    try:
        if lines[0][-2:] == "\r\n":
            return "\r\n"
        return "\n"
    except (IndexError, TypeError):
        return None


def _match_line_endings(document: workspace.TextDocument, text: str) -> str:
    """Ensure formatted output keeps the document's line-ending style."""
    expected = _get_line_endings(document.source.splitlines(keepends=True))
    actual = _get_line_endings(text.splitlines(keepends=True))
    if actual == expected or actual is None or expected is None:
        return text
    return text.replace(actual, expected)


def _settings_from_initialization(options: Any) -> tuple[dict[str, Any], str | None]:
    """Read both the VS Code extension and standalone initialization shapes."""
    if not isinstance(options, dict):
        return {}, None

    extension_settings = options.get("settings")
    global_settings = options.get("globalSettings")
    if isinstance(extension_settings, list) and extension_settings:
        settings = extension_settings[0]
        if not isinstance(settings, dict):
            settings = {}
        merged = dict(global_settings) if isinstance(global_settings, dict) else {}
        merged.update(settings)
        return merged, settings.get("cwd")

    direct = {
        key: value
        for key, value in options.items()
        if key in {"cwd", "dialect", "templater", "diagnosticSeverity"}
    }
    return direct, direct.get("cwd")


def _path_for_document(document: workspace.TextDocument) -> pathlib.Path:
    """Convert a managed document URI to a filesystem path."""
    path = uris.to_fs_path(document.uri)
    if path is None:
        raise EngineError(f"Unsupported document URI: {document.uri}")
    return pathlib.Path(path)


def _lint_document(document: workspace.TextDocument) -> list[lsp.Diagnostic]:
    """Lint one managed document and convert source positions to LSP positions."""
    if ENGINE is None:
        return []
    try:
        violations = ENGINE.lint(document.source, _path_for_document(document))
        severity = _get_severity(DIAGNOSTIC_SEVERITY)
        return [
            lsp.Diagnostic(
                range=lsp.Range(
                    start=lsp.Position(
                        line=max(violation.line - 1, 0),
                        character=max(violation.column - 1, 0),
                    ),
                    end=lsp.Position(
                        line=max(violation.line - 1, 0),
                        character=max(violation.column - 1, 0),
                    ),
                ),
                message=f"{violation.code}: {violation.description}",
                severity=severity,
                code=violation.code,
                source="sqlfluff",
            )
            for violation in violations
        ]
    except EngineError as error:
        log_error(str(error))
    except Exception:  # noqa: BLE001 - keep LSP alive after user-file errors
        log_error(traceback.format_exc(chain=True))
    return []


def _publish_for_uri(uri: str) -> None:
    """Lint the current document and publish diagnostics."""
    try:
        document = LSP_SERVER.workspace.get_text_document(uri)
        LSP_SERVER.text_document_publish_diagnostics(
            lsp.PublishDiagnosticsParams(uri=uri, diagnostics=_lint_document(document))
        )
    except Exception:  # noqa: BLE001 - keep LSP alive after notification errors
        log_error(traceback.format_exc(chain=True))


def _schedule_lint(uri: str) -> None:
    """Debounce linting after a document change."""
    delay = max(float(os.getenv("SQLFLUFF_DEBOUNCE_MS", "300")) / 1000, 0)
    with DEBOUNCE_LOCK:
        previous = DEBOUNCE_TIMERS.pop(uri, None)
        if previous is not None:
            previous.cancel()
        timer = threading.Timer(delay, _publish_for_uri, args=(uri,))
        timer.daemon = True
        DEBOUNCE_TIMERS[uri] = timer
        timer.start()


def _clear_timer(uri: str) -> None:
    with DEBOUNCE_LOCK:
        timer = DEBOUNCE_TIMERS.pop(uri, None)
        if timer is not None:
            timer.cancel()


@LSP_SERVER.feature(lsp.TEXT_DOCUMENT_DID_OPEN)
def did_open(params: lsp.DidOpenTextDocumentParams) -> None:
    """Lint an opened document immediately."""
    _publish_for_uri(params.text_document.uri)


@LSP_SERVER.feature(lsp.TEXT_DOCUMENT_DID_SAVE)
def did_save(params: lsp.DidSaveTextDocumentParams) -> None:
    """Lint a saved document immediately."""
    _publish_for_uri(params.text_document.uri)


@LSP_SERVER.feature(lsp.TEXT_DOCUMENT_DID_CHANGE)
def did_change(params: lsp.DidChangeTextDocumentParams) -> None:
    """Debounce linting after a full-document change."""
    _schedule_lint(params.text_document.uri)


@LSP_SERVER.feature(lsp.TEXT_DOCUMENT_DID_CLOSE)
def did_close(params: lsp.DidCloseTextDocumentParams) -> None:
    """Clear diagnostics and cancel pending work on close."""
    _clear_timer(params.text_document.uri)
    LSP_SERVER.text_document_publish_diagnostics(
        lsp.PublishDiagnosticsParams(uri=params.text_document.uri, diagnostics=[])
    )


@LSP_SERVER.feature(lsp.TEXT_DOCUMENT_FORMATTING)
def formatting(params: lsp.DocumentFormattingParams) -> list[lsp.TextEdit] | None:
    """Return one whole-document edit containing SQLFluff's source-preserving fix."""
    if ENGINE is None:
        return None
    document = LSP_SERVER.workspace.get_text_document(params.text_document.uri)
    try:
        fixed, changed, _ = ENGINE.fix(document.source, _path_for_document(document))
        if not changed:
            return None
        fixed = _match_line_endings(document, fixed)
        return [
            lsp.TextEdit(
                range=lsp.Range(
                    start=lsp.Position(line=0, character=0),
                    end=lsp.Position(line=len(document.lines), character=0),
                ),
                new_text=fixed,
            )
        ]
    except EngineError as error:
        log_error(str(error))
    except Exception:  # noqa: BLE001 - keep LSP alive after formatting errors
        log_error(traceback.format_exc(chain=True))
    return None


@LSP_SERVER.feature(lsp.INITIALIZE)
def initialize(params: lsp.InitializeParams) -> None:
    """Initialize the shared engine from project and client settings."""
    global ENGINE, DIAGNOSTIC_SEVERITY
    options, configured_root = _settings_from_initialization(
        params.initialization_options
    )
    options = {**options, **_CLI_OVERRIDES}
    root_value = configured_root or params.root_path or os.getcwd()
    root = pathlib.Path(root_value).expanduser()
    overrides = {
        key: str(options[key]) for key in ("dialect", "templater") if options.get(key)
    }
    try:
        ENGINE = Engine(root, overrides=overrides)
        DIAGNOSTIC_SEVERITY = str(options.get("diagnosticSeverity", "warning"))
        log_to_output(f"SQLFluff engine initialized at {ENGINE.root}")
    except EngineError as error:
        ENGINE = None
        LSP_SERVER.window_show_message(
            lsp.ShowMessageParams(type=lsp.MessageType.Error, message=str(error))
        )
    except Exception:  # noqa: BLE001 - report initialization failures
        ENGINE = None
        log_error(traceback.format_exc(chain=True))


def main(overrides: dict[str, str] | None = None) -> None:
    """Start the language server over stdio."""
    if overrides:
        _CLI_OVERRIDES.clear()
        _CLI_OVERRIDES.update(overrides)
    LSP_SERVER.start_io()


_CLI_OVERRIDES: dict[str, str] = {}

__all__ = ["ENGINE", "LSP_SERVER", "main"]


def _cleanup() -> None:
    """Cancel pending debounce timers and release the cached engine."""
    global ENGINE
    with DEBOUNCE_LOCK:
        timers = list(DEBOUNCE_TIMERS.values())
        DEBOUNCE_TIMERS.clear()
    for timer in timers:
        timer.cancel()
    ENGINE = None


@LSP_SERVER.feature(lsp.EXIT)
def on_exit(_params: Any = None) -> None:
    """Cancel pending debounce timers before the protocol exits."""
    _cleanup()


@LSP_SERVER.feature(lsp.SHUTDOWN)
def on_shutdown(_params: Any = None) -> None:
    """Release the cached engine before the protocol shuts down."""
    _cleanup()


if __name__ == "__main__":
    main()
