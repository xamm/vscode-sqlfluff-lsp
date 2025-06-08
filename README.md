# SQLFluff Extension for VS Code

A VS Code extension for SQLFluff, a SQL linter and formatter. SQLFluff is a popular, dialect-aware SQL linter and formatter that helps you write clean, consistent SQL code.

## Features

- **SQL Linting**: Checks your SQL code for syntax errors, style issues, and best practices
- **SQL Formatting**: Automatically formats your SQL code using `sqlfluff fix` which respects your project configuration
- **Multiple SQL Dialects**: Supports various SQL dialects like PostgreSQL, MySQL, BigQuery, Snowflake and more
- **Format on Save**: Optional ability to format your SQL code whenever you save
- **Configurable Rules**: Enable or disable specific linting rules to match your team's coding standards via `.sqlfluff` or `pyproject.toml` files

## Requirements

- Python 3.8 or above
- VS Code 1.64.0 or above
- Python extension for VS Code

## Extension Settings

This extension contributes the following settings:

* `sqlfluff.args`: Additional arguments passed to SQLFluff
* `sqlfluff.path`: Path to SQLFluff binary if not using the bundled version
* `sqlfluff.importStrategy`: Controls where SQLFluff is imported from ("useBundled" or "fromEnvironment")
* `sqlfluff.interpreter`: Python interpreter to use for SQLFluff
* `sqlfluff.showNotifications`: Controls when notifications are shown
* `sqlfluff.diagnosticSeverity`: Controls the severity level of SQLFluff diagnostics (error, warning, information, hint)
* `sqlfluff.dialect`: Specifies which SQL dialect to use for linting and formatting
* `sqlfluff.templater`: Defines which templater to use for processing SQL files

> **Note:** While SQLFluff configurations are typically defined in `.sqlfluff` or `pyproject.toml` files, the VS Code settings above will override those configurations if set. This allows you to customize SQLFluff behavior specifically within VS Code without changing your project-level configurations.

## SQLFluff Commands

The extension provides the following commands (accessible via Command Palette):

* **SQLFluff: Restart Server** (`sqlfluff.restart`): Restarts the language server

## Configuration

SQLFluff can be configured using a `.sqlfluff` configuration file or `pyproject.toml` file in your project root. The extension will respect these project-level configurations when linting and formatting SQL files.

Example `.sqlfluff` configuration:

```ini
[sqlfluff]
dialect = snowflake
templater = jinja
exclude_rules = L016

[sqlfluff:indentation]
indented_joins = True
indented_using_on = True

[sqlfluff:layout:type:comma]
line_position = trailing

[sqlfluff:rules]
allow_scalar = True
unquoted_identifiers_policy = all

[sqlfluff:rules:capitalisation.keywords]  # CP01, formerly L010
capitalisation_policy = upper

[sqlfluff:rules:capitalisation.functions]  # CP03, formerly L030
capitalisation_policy = upper
```

Example `pyproject.toml` configuration:

```toml
[tool.sqlfluff]
dialect = "snowflake"
templater = "jinja"
exclude_rules = ["L016"]

[tool.sqlfluff.indentation]
indented_joins = true
indented_using_on = true

[tool.sqlfluff.layout.type.comma]
line_position = "trailing"

[tool.sqlfluff.rules]
allow_scalar = true
unquoted_identifiers_policy = "all"

[tool.sqlfluff.rules.capitalisation.keywords]  # CP01, formerly L010
capitalisation_policy = "upper"

[tool.sqlfluff.rules.capitalisation.functions]  # CP03, formerly L030
capitalisation_policy = "upper"
```

For detailed configuration options, see [SQLFluff documentation](https://docs.sqlfluff.com/en/stable/configuration.html).

## Supported SQL Dialects

- ANSI (default)
- BigQuery
- ClickHouse
- Databricks
- DB2
- DuckDB
- Hive
- MySQL
- Oracle
- PostgreSQL
- Redshift
- Snowflake
- SparkSQL
- SQLite
- Teradata
- TSQL (SQL Server)

## Quick Start

1. Install the extension
2. Open a SQL file (`.sql` extension)
3. Errors and warnings will be highlighted automatically
4. Format document with `Format Document` command (Shift+Alt+F) or on save if enabled

## Troubleshooting

- **SQLFluff Not Found**: Make sure Python is installed and available in your path
- **No Linting Results**: Check if you have the correct dialect selected for your SQL
- **Formatting Issues**: Try using the dedicated "SQLFluff: Format SQL" command which uses `sqlfluff fix` internally
- **Configuration Not Applied**: Ensure your `.sqlfluff` or `pyproject.toml` file is correctly formatted and in the project root
- **Performance Issues**: For large files, consider excluding some rules in your configuration

## Release Notes

### 1.0.0

Initial release of SQLFluff extension for VS Code

---

## Development

### Building the Extension

```bash
npm install
npm run package
```

### Running Tests

```bash
npm test
```

## License

This extension is licensed under the MIT License.
