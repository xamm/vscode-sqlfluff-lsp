# SQLFluff Extension and Agent Servers

A VS Code extension for SQLFluff, plus a persistent Python language server and
MCP server for editors and coding agents. SQLFluff remains the linter and
formatter; this project provides the protocol frontends and keeps one engine
alive so dbt projects do not reload their manifest for every request.

## Features

- **SQL linting** with dialect-aware diagnostics
- **SQL formatting** through source-preserving SQLFluff fixes
- **dbt templating** for saved files and unsaved editor buffers
- **Persistent engine** shared by the LSP and MCP frontends
- **MCP tools** for agent-oriented lint, dry-run fix, applied fix, and reload
- **Configurable rules** from `.sqlfluff` or `pyproject.toml`

## Requirements

- Python 3.10 or above with SQLFluff installed
- VS Code 1.138.0 or above for the extension
- Python extension for VS Code

## VS Code Quick Start

Install SQLFluff in the Python environment used by your project. For example:

```bash
# Standard virtual environment
python -m pip install sqlfluff

# uv-managed project
uv add --dev sqlfluff
```

Then run **Python: Select Interpreter** in VS Code and select that environment.
The extension follows the interpreter selected by the Python extension and
restarts automatically when it changes. Alternatively, set
`sqlfluff.interpreter` to the interpreter path for the workspace.

For dbt projects, install the templater and your adapter in the same
environment, for example:

```bash
python -m pip install sqlfluff sqlfluff-templater-dbt dbt-snowflake
```

Project installation alone is sufficient when that project environment is the
selected VS Code interpreter. If startup fails, the extension offers actions
to select another interpreter or open the SQLFluff output channel.

## Extension Settings

The extension contributes these settings:

* `sqlfluff.showNotifications`: Controls when server notifications are shown
* `sqlfluff.diagnosticSeverity`: Severity for SQLFluff diagnostics (`error`,
  `warning`, `information`, or `hint`)
* `sqlfluff.dialect`: Optional dialect override
* `sqlfluff.templater`: Optional templater override

The old `sqlfluff.args` and `sqlfluff.path` settings are removed. The engine
uses SQLFluff's Python API directly, so per-request CLI arguments and binary
paths cannot be applied.

Project configuration remains the default. VS Code settings for dialect and
templater override the project configuration when explicitly set.

## Configuration

SQLFluff loads `.sqlfluff` or `pyproject.toml` from the project root. Example:

```ini
[sqlfluff]
dialect = snowflake
templater = jinja
encoding = utf-8
exclude_rules = L016

[sqlfluff:rules:capitalisation.keywords]
capitalisation_policy = upper
```

For detailed options, see the [SQLFluff documentation](https://docs.sqlfluff.com/en/stable/configuration.html).

## Standalone LSP

Install the persistent server from a checkout or a package source:

```bash
uv tool install '.[dbt]'
# Add the adapter used by the project, for example:
uv tool install '.[dbt]' --with dbt-snowflake
```

The command is `sqlfluff-lsp`. It speaks LSP over stdio and accepts optional
`--dialect` and `--templater` overrides. A standalone client can launch it with
the project directory as its working directory.

OMP configuration (`~/.omp/agent/lsp.json`):

```json
{
  "servers": {
    "sqlfluff-lsp": {
      "command": "sqlfluff-lsp",
      "fileTypes": [".sql"],
      "rootMarkers": [".sqlfluff", "dbt_project.yml", ".git"],
      "isLinter": true
    }
  }
}
```

Helix and Neovim can use the same command in their language-server
configuration. The server supports full-document synchronization, diagnostics,
formatting, and a debounced `didChange` path. Code actions are not included in
v1.

## MCP for Agents

Install the MCP entrypoint with the same project extras:

```bash
uv tool install '.[dbt]' --with dbt-duckdb
```

The repository includes a root `.mcp.json` configuration for Claude Code and
OMP-compatible MCP discovery:

```json
{
  "mcpServers": {
    "sqlfluff": {
      "command": "sqlfluff-mcp",
      "args": []
    }
  }
}
```

The `sqlfluff` server exposes:

- `lint(paths)`: returns JSON violations and a summary
- `fix(paths, apply=false)`: returns unified diffs without changing files
- `fix(paths, apply=true)`: writes source-preserving fixes
- `reload()`: drops cached configuration and the dbt manifest

The first operation in a dbt project compiles the project and can take seconds.
Later operations reuse the in-process manifest and are substantially faster.
Violation lines and columns are 1-based source positions.

## dbt Setup

Install `sqlfluff-templater-dbt` through the `dbt` extra and install the adapter
used by the project. Configure the same project and profiles directories that
dbt uses:

```ini
[sqlfluff]
dialect = snowflake
templater = dbt
encoding = utf-8

[sqlfluff:templater:dbt]
project_dir = .
profiles_dir = .
```

Set `profiles_dir` to the real profile location when it is outside the project.
Keep generated targets and packages in `.sqlfluffignore`, for example:

```text
target/
dbt_packages/
macros/
```

The engine passes each in-memory buffer to SQLFluff with its real file path,
which is required for dbt's `ref`, `var`, manifest, and source-position
semantics.

## Speed and Cache Behavior

The engine creates one `sqlfluff.core.Linter` per project process. SQLFluff's
dbt templater therefore caches its manifest, compiler, and adapter state across
requests. All lint and fix work is serialized because dbt templating mutates
shared Jinja state. Install the optional Rust parser when a compatible wheel is
available:

```bash
uv tool install '.[dbt,fast]' --with dbt-snowflake
```

When the Rust parser package is present, the engine selects
`use_rust_parser = auto` and silently falls back to the Python parser when it is
unavailable.

## Manifest Staleness and Troubleshooting

The dbt manifest is cached for the lifetime of a server. After changing macros,
models, or project configuration, reload the process or use:

- VS Code: `SQLFluff: Restart Server`
- OMP LSP: `lsp reload *`
- MCP: call `reload`

If the server reports no dialect, configure `dialect` in project config or use
the standalone `--dialect` option. If an installed command is not on `PATH`,
replace it in the client configuration with its absolute uv-tool path.

## Supported SQL Dialects

ANSI, BigQuery, ClickHouse, Databricks, DB2, DuckDB, Hive, MySQL, Oracle,
PostgreSQL, Redshift, Snowflake, SparkSQL, SQLite, Teradata, and TSQL.

## Quick Start

1. Install the extension or the standalone server.
2. Open a SQL file or configure an agent client.
3. Configure the dialect and templater in project configuration.
4. Review diagnostics or call the MCP `lint` tool.
5. Format with `Format Document` or call MCP `fix` in dry-run mode first.

Install the declared toolchain (Python 3.10 is the supported floor and Python
3.14 is the current development runtime) and Node dependencies:

```bash
mise install
npm install
```

Build the extension:

```bash
npm run compile
```

Run the Python fixture suite with dbt and the DuckDB adapter:

```bash
uv run --extra dbt --group test pytest src/test/python_tests -v
```

Run the cross-version checks and lint with Nox:

```bash
uvx nox -s tests     # runs on Python 3.10 and 3.14
uvx nox -P 3.14 -s lint
```

Build the protocol bundle and VSIX through mise. Publishing requires VSCE
marketplace credentials in the environment:

```bash
mise run package
mise run publish
```

Upgrade dependencies within their declared version ranges:

```bash
mise run bump
```

Major upgrades require deliberate constraint and compatibility changes in
`pyproject.toml` or `package.json`.

Python linting, formatting, and type checking run through Ruff and Pyright in
`uvx nox -P 3.14 -s lint`. TypeScript linting runs on Oxlint
(`.oxlintrc.json`) with `curly`, `eqeqeq`, and the native `no-throw-literal`
rule. The former
`@typescript-eslint/naming-convention` rule is not yet implemented in Oxlint
or tsgolint (tracked in oxc-project/oxc#481); the codebase conforms to it
today — re-add the rule when Oxlint ships it. Formatting runs on Oxfmt
(`.oxfmtrc.json`); `npm run format-check` verifies it. TypeScript remains at
6.0.3 because `ts-loader@9.6.2` cannot compile with the TypeScript 7 native
compiler; upgrade it together with TypeScript when loader support is available.

## License

This extension and its server integrations are licensed under the MIT License.
