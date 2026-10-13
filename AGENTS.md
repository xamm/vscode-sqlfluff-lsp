# AGENTS.md

- Python tooling runs through `uv` and `mise`; `.mise.toml` has no `check` task and exposes `bundle`, `package` and `publish`.
- Verify dependencies with `uv lock --check` and commit the single `uv.lock` with Python dependency changes (see `.github/workflows/ci.yml`, `noxfile.py`).
- Python lint/typecheck (ruff, pyright) and TypeScript lint (oxlint): `uvx nox -s lint` (see `noxfile.py`, `.github/workflows/ci.yml`).
- Tests: `uvx nox -s tests` for Python; `npm test` for the VS Code extension (see `noxfile.py`, `package.json`).
- Editor features run through the LSP server (`src/extension.ts`, `sqlfluff_lsp/lsp_server.py`); the MCP frontend (`.mcp.json` → `sqlfluff-mcp`) is agent-facing — both share `sqlfluff_lsp/engine.py`.
- `bundled/protocol/` is generated vendor output and gitignored; rebuild it with `mise run bundle`, do not hand-edit (see `noxfile.py`, `.gitignore`).
