# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
"""Implementation of tool support over LSP."""

from __future__ import annotations

import copy
import json
import os
import pathlib
import sys
import traceback
from typing import Any, Optional, Sequence


# **********************************************************
# Update sys.path before importing any bundled libraries.
# **********************************************************
def update_sys_path(path_to_add: str, strategy: str) -> None:
    """Add given path to `sys.path`."""
    if path_to_add not in sys.path and os.path.isdir(path_to_add):
        if strategy == "useBundled":
            sys.path.insert(0, path_to_add)
        elif strategy == "fromEnvironment":
            sys.path.append(path_to_add)


# Ensure that we can import LSP libraries, and other bundled libraries.
update_sys_path(
    os.fspath(pathlib.Path(__file__).parent.parent / "libs"),
    os.getenv("LS_IMPORT_STRATEGY", "useBundled"),
)

# **********************************************************
# Imports needed for the language server goes below this.
# **********************************************************
# pylint: disable=wrong-import-position,import-error
import lsp_jsonrpc as jsonrpc
import lsp_utils as utils
import lsprotocol.types as lsp
from pygls import server, uris, workspace

WORKSPACE_SETTINGS = {}
GLOBAL_SETTINGS = {}
RUNNER = pathlib.Path(__file__).parent / "lsp_runner.py"

MAX_WORKERS = 5
LSP_SERVER = server.LanguageServer(
    name="sqlfluff", version="0.1.0", max_workers=MAX_WORKERS
)


# **********************************************************
# Tool specific code goes below this.
# **********************************************************

TOOL_MODULE = "sqlfluff"
TOOL_DISPLAY = "SQLFluff"

# Default SQLFluff arguments (no global args; specify per-command)
TOOL_ARGS = []


def _parse_sqlfluff_output(content: str, severity: str) -> list[lsp.Diagnostic]:
    """Parse SQLFluff JSON output into LSP diagnostics."""
    diagnostics: list[lsp.Diagnostic] = []
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        log_error(f"Error parsing SQLFluff JSON: {str(e)}")
        return []
    file_results = data if isinstance(data, list) else [data]
    for file_result in file_results:
        violations = file_result.get("violations", [])
        for v in violations:
            try:
                # SQLFluff uses start_line_no/start_line_pos (1-based)
                raw_line = v.get("start_line_no", v.get("line_no", 1))
                raw_col = v.get("start_line_pos", v.get("line_pos", 1))
                line = max(raw_line - 1, 0)
                col = max(raw_col - 1, 0)
                # Calculate positions
                start = lsp.Position(line=line, character=col)
                end = lsp.Position(line=line, character=col + 1)
                rng = lsp.Range(start=start, end=end)
                # Build Diagnostic with named fields to ensure proper assignment
                diagnostic = lsp.Diagnostic(
                    range=rng,
                    message=v.get("description", ""),
                    severity=_get_severity(severity),
                    code=v.get("code", ""),
                    source=TOOL_DISPLAY,
                )
                diagnostics.append(diagnostic)
            except Exception:
                log_error(f"Error creating diagnostic: {traceback.format_exc()}")
    return diagnostics


def _get_severity(severity: str) -> lsp.DiagnosticSeverity:
    """Map SQLFluff rules to LSP severity levels, with optional override to treat all as errors."""
    # Override: treat all diagnostics as errors if configured
    log_to_output(f"Using diagnostic severity: {severity}")
    match severity:
        case "error":
            return lsp.DiagnosticSeverity.Error
        case "warning":
            return lsp.DiagnosticSeverity.Warning
        case "information":
            return lsp.DiagnosticSeverity.Information
        case "hint":
            return lsp.DiagnosticSeverity.Hint
    raise ValueError(f"Unknown diagnostic severity: {severity}")


def _linting_helper(document: workspace.Document) -> list[lsp.Diagnostic]:
    """Run SQLFluff linter on document."""
    try:
        settings = _get_settings_by_document(document)
        dialect = settings.get("dialect", None)
        templater = settings.get("templater", None)
        args = ["lint", "-f", "json", "--disable-progress-bar"]
        if dialect:
            args += ["--dialect", dialect]
        if templater:
            args += ["--templater", templater]
        settings = _get_settings_by_document(document)
        severity = settings.get("diagnosticSeverity", "warning")

        try:
            result = _run_tool_on_document(document, use_stdin=True, extra_args=args)
        except Exception:
            result = _run_tool_on_document(document, use_stdin=False, extra_args=args)
        return (
            _parse_sqlfluff_output(result.stdout, severity)
            if result and result.stdout
            else []
        )
    except Exception:
        log_error(traceback.format_exc(chain=True))
        return []


def _match_line_endings(document: workspace.Document, text: str) -> str:
    """Ensures that the edited text line endings matches the document line endings."""
    expected = _get_line_endings(document.source.splitlines(keepends=True))
    actual = _get_line_endings(text.splitlines(keepends=True))
    if actual == expected or actual is None or expected is None:
        return text
    return text.replace(actual, expected)


def _formatting_helper(document: workspace.Document) -> list[lsp.TextEdit] | None:
    """Run SQLFluff formatter on document."""
    try:
        log_to_output(f"Starting formatting for document: {document.uri}")
        settings = _get_settings_by_document(document)
        dialect = settings.get("dialect", None)
        templater = settings.get("templater", None)
        # Always output fixed content to stdout
        fix_args = ["fix", "--disable-progress-bar", "--quiet", "--FIX-EVEN-UNPARSABLE"]
        if dialect:
            fix_args += ["--dialect", dialect]
        if templater:
            fix_args += ["--templater", templater]
        log_to_output("Starting SQLFluff fix with basic arguments")
        result = _run_tool_on_document(document, use_stdin=True, extra_args=fix_args)
        if result and result.stdout:
            new_source = _match_line_endings(document, result.stdout)
            return [
                lsp.TextEdit(
                    range=lsp.Range(
                        start=lsp.Position(line=0, character=0),
                        end=lsp.Position(line=len(document.lines), character=0),
                    ),
                    new_text=new_source,
                )
            ]
    except Exception:
        log_error(traceback.format_exc(chain=True))

    return None


def _get_line_endings(lines: list[str]) -> str:
    """Returns line endings used in the text."""
    try:
        if lines[0][-2:] == "\r\n":
            return "\r\n"
        return "\n"
    except Exception:  # pylint: disable=broad-except
        return None


# **********************************************************
# Formatting features ends here
# **********************************************************


# **********************************************************
# Linting handlers
# **********************************************************
@LSP_SERVER.feature(lsp.TEXT_DOCUMENT_DID_OPEN)
def did_open(params: lsp.DidOpenTextDocumentParams) -> None:
    """Handle file open: lint and publish diagnostics."""
    document = LSP_SERVER.workspace.get_text_document(params.text_document.uri)
    diagnostics = _linting_helper(document)
    LSP_SERVER.publish_diagnostics(document.uri, diagnostics)


@LSP_SERVER.feature(lsp.TEXT_DOCUMENT_DID_SAVE)
def did_save(params: lsp.DidSaveTextDocumentParams) -> None:
    """Handle file save: lint and publish diagnostics."""
    document = LSP_SERVER.workspace.get_text_document(params.text_document.uri)
    diagnostics = _linting_helper(document)
    LSP_SERVER.publish_diagnostics(document.uri, diagnostics)


@LSP_SERVER.feature(lsp.TEXT_DOCUMENT_DID_CLOSE)
def did_close(params: lsp.DidCloseTextDocumentParams) -> None:
    """Handle file close: clear diagnostics."""
    LSP_SERVER.publish_diagnostics(params.text_document.uri, [])


# **********************************************************
# Formatting handler
# **********************************************************
@LSP_SERVER.feature(lsp.TEXT_DOCUMENT_FORMATTING)
def formatting(params: lsp.DocumentFormattingParams) -> list[lsp.TextEdit] | None:
    """Handle formatting request: apply SQLFluff fix."""
    document = LSP_SERVER.workspace.get_text_document(params.text_document.uri)
    return _formatting_helper(document)


# **********************************************************
# Required Language Server Initialization and Exit handlers.
# **********************************************************
@LSP_SERVER.feature(lsp.INITIALIZE)
def initialize(params: lsp.InitializeParams) -> None:
    """LSP handler for initialize request."""
    log_to_output(f"CWD Server: {os.getcwd()}")

    paths = "\r\n   ".join(sys.path)
    log_to_output(f"sys.path used to run Server:\r\n   {paths}")

    GLOBAL_SETTINGS.update(**params.initialization_options.get("globalSettings", {}))

    settings = params.initialization_options["settings"]
    _update_workspace_settings(settings)
    log_to_output(
        f"Settings used to run Server:\r\n{json.dumps(settings, indent=4, ensure_ascii=False)}\r\n"
    )
    log_to_output(
        f"Global settings:\r\n{json.dumps(GLOBAL_SETTINGS, indent=4, ensure_ascii=False)}\r\n"
    )


@LSP_SERVER.feature(lsp.EXIT)
def on_exit(_params: Optional[Any] = None) -> None:
    """Handle clean up on exit."""
    jsonrpc.shutdown_json_rpc()


@LSP_SERVER.feature(lsp.SHUTDOWN)
def on_shutdown(_params: Optional[Any] = None) -> None:
    """Handle clean up on shutdown."""
    jsonrpc.shutdown_json_rpc()


def _get_global_defaults():
    return {
        "path": GLOBAL_SETTINGS.get("path", []),
        "interpreter": GLOBAL_SETTINGS.get("interpreter", [sys.executable]),
        "args": GLOBAL_SETTINGS.get("args", []),
        "importStrategy": GLOBAL_SETTINGS.get("importStrategy", "useBundled"),
        "showNotifications": GLOBAL_SETTINGS.get("showNotifications", "off"),
        "formatOnSave": GLOBAL_SETTINGS.get("formatOnSave", False),
        "executablePath": GLOBAL_SETTINGS.get("executablePath", ""),
        "diagnosticSeverity": GLOBAL_SETTINGS.get("diagnosticSeverity", "warning"),
        "dialect": GLOBAL_SETTINGS.get("dialect"),
        "templater": GLOBAL_SETTINGS.get("templater"),
    }


def _update_workspace_settings(settings):
    if not settings:
        key = os.getcwd()
        WORKSPACE_SETTINGS[key] = {
            "cwd": key,
            "workspaceFS": key,
            "workspace": uris.from_fs_path(key),
            **_get_global_defaults(),
        }
        return

    for setting in settings:
        key = uris.to_fs_path(setting["workspace"])
        WORKSPACE_SETTINGS[key] = {
            "cwd": key,
            **setting,
            "workspaceFS": key,
        }


def _get_document_key(document: workspace.Document):
    if WORKSPACE_SETTINGS:
        document_workspace = pathlib.Path(document.path)
        workspaces = {s["workspaceFS"] for s in WORKSPACE_SETTINGS.values()}

        # Find workspace settings for the given file.
        while document_workspace != document_workspace.parent:
            if str(document_workspace) in workspaces:
                return str(document_workspace)
            document_workspace = document_workspace.parent

    return None


def _get_settings_by_document(document: workspace.Document | None):
    if document is None or document.path is None:
        return list(WORKSPACE_SETTINGS.values())[0]

    key = _get_document_key(document)
    if key is None:
        # This is either a non-workspace file or there is no workspace.
        key = os.fspath(pathlib.Path(document.path).parent)
        return {
            "cwd": key,
            "workspaceFS": key,
            "workspace": uris.from_fs_path(key),
            **_get_global_defaults(),
        }

    return WORKSPACE_SETTINGS[str(key)]


# *****************************************************
# Internal execution APIs.
# *****************************************************
def _run_tool_on_document(
    document: workspace.Document,
    use_stdin: bool = False,
    extra_args: Optional[Sequence[str]] = None,
) -> utils.RunResult | None:
    """Runs tool on the given document.

    if use_stdin is true then contents of the document is passed to the
    tool via stdin.
    """
    if extra_args is None:
        extra_args = []
    # Save original extra_args for fallback to file input
    original_extra = list(extra_args)
    if str(document.uri).startswith("vscode-notebook-cell"):
        # TODO: Decide on if you want to skip notebook cells.
        # Skip notebook cells
        return None

    if utils.is_stdlib_file(document.path):
        # TODO: Decide on if you want to skip standard library files.
        # Skip standard library python files.
        return None

    # deep copy here to prevent accidentally updating global settings.
    settings = copy.deepcopy(_get_settings_by_document(document))

    code_workspace = settings["workspaceFS"]
    cwd = settings["cwd"]

    use_path = False
    use_rpc = False
    if settings["path"]:
        # 'path' setting takes priority over everything.
        use_path = True
        argv = settings["path"]
    elif settings["interpreter"] and not utils.is_current_interpreter(
        settings["interpreter"][0]
    ):
        # If there is a different interpreter set use JSON-RPC to the subprocess
        # running under that interpreter.
        argv = [TOOL_MODULE]
        use_rpc = True
    else:
        # if the interpreter is same as the interpreter running this
        # process then run as module.
        argv = [TOOL_MODULE]

    argv += TOOL_ARGS + settings["args"] + extra_args

    if use_stdin:
        # For SQLFluff with stdin, we need to specify --stdin-filename for config detection
        # SQLFluff also accepts input from stdin with a dash "-" as the file argument
        argv += ["--stdin-filename", document.path, "-"]
    else:
        argv += [document.path]

    if use_path:
        # This mode is used when running executables.
        log_to_output(" ".join(argv))
        log_to_output(f"CWD Server: {cwd}")
        result = utils.run_path(
            argv=argv,
            use_stdin=use_stdin,
            cwd=cwd,
            source=document.source.replace("\r\n", "\n"),
        )
        if result.stderr:
            log_to_output(result.stderr)
    elif use_rpc:
        # This mode is used if the interpreter running this server is different from
        # the interpreter used for running this server.
        log_to_output(" ".join(settings["interpreter"] + ["-m"] + argv))
        log_to_output(f"CWD Linter: {cwd}")

        result = jsonrpc.run_over_json_rpc(
            workspace=code_workspace,
            interpreter=settings["interpreter"],
            module=TOOL_MODULE,
            argv=argv,
            use_stdin=use_stdin,
            cwd=cwd,
            source=document.source,
        )
        if result.exception:
            log_error(result.exception)
            result = utils.RunResult(result.stdout, result.stderr)
        elif result.stderr:
            log_to_output(result.stderr)
    else:
        # In this mode the tool is run as a module in the same process as the language server.
        log_to_output(" ".join([sys.executable, "-m"] + argv))
        log_to_output(f"CWD Linter: {cwd}")
        # This is needed to preserve sys.path, in cases where the tool modifies
        # sys.path and that might not work for this scenario next time around.
        with utils.substitute_attr(sys, "path", sys.path[:]):
            try:
                # TODO: `utils.run_module` is equivalent to running `python -m sqlfluff`.
                # If your tool supports a programmatic API then replace the function below
                # with code for your tool. You can also use `utils.run_api` helper, which
                # handles changing working directories, managing io streams, etc.
                # Also update `_run_tool` function and `utils.run_module` in `lsp_runner.py`.
                result = utils.run_module(
                    module=TOOL_MODULE,
                    argv=argv,
                    use_stdin=use_stdin,
                    cwd=cwd,
                    source=document.source,
                )
            except Exception:
                log_error(traceback.format_exc(chain=True))
                raise
        if result.stderr:
            log_to_output(result.stderr)

    # Fallback: if stdin mode failed, retry with file input
    if use_stdin and result and (result.stderr or not result.stdout):
        log_warning("Stdin invocation failed, falling back to file input.")
        return _run_tool_on_document(
            document, use_stdin=False, extra_args=original_extra
        )
    log_to_output(f"{document.uri} :\r\n{result.stdout}")
    return result


# *****************************************************
# Logging and notification.
# *****************************************************
def log_to_output(
    message: str, msg_type: lsp.MessageType = lsp.MessageType.Log
) -> None:
    LSP_SERVER.show_message_log(message, msg_type)


def log_error(message: str) -> None:
    LSP_SERVER.show_message_log(message, lsp.MessageType.Error)
    if os.getenv("LS_SHOW_NOTIFICATION", "off") in ["onError", "onWarning", "always"]:
        LSP_SERVER.show_message(message, lsp.MessageType.Error)


def log_warning(message: str) -> None:
    LSP_SERVER.show_message_log(message, lsp.MessageType.Warning)
    if os.getenv("LS_SHOW_NOTIFICATION", "off") in ["onWarning", "always"]:
        LSP_SERVER.show_message(message, lsp.MessageType.Warning)


def log_always(message: str) -> None:
    LSP_SERVER.show_message_log(message, lsp.MessageType.Info)
    if os.getenv("LS_SHOW_NOTIFICATION", "off") in ["always"]:
        LSP_SERVER.show_message(message, lsp.MessageType.Info)


# *****************************************************
# Start the server.
# *****************************************************
if __name__ == "__main__":
    LSP_SERVER.start_io()
