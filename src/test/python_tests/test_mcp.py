# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
"""Integration tests for the SQLFluff MCP server."""

import json
import os
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters, stdio_client

DBT_ROOT = Path(__file__).parent / "test_data" / "dbt_project"
MODEL = DBT_ROOT / "models" / "stg_customers.sql"


@pytest.mark.asyncio
async def test_mcp_lint_fix_and_reload() -> None:
    """Exercise lint, dry-run fix, applied fix, and reload over stdio."""
    original = MODEL.read_text(encoding="utf-8")
    server = StdioServerParameters(
        command=sys.executable,
        args=["-c", "from sqlfluff_lsp.cli import mcp_main; mcp_main()"],
        cwd=str(DBT_ROOT),
        env={
            **os.environ,
            "PYTHONPATH": str(Path(__file__).parents[3]),
        },
    )
    try:
        async with (
            stdio_client(server) as (read_stream, write_stream),
            ClientSession(read_stream, write_stream) as client,
        ):
            await client.initialize()
            lint_result = await client.call_tool(
                "lint", {"paths": ["models/stg_customers.sql"]}
            )
            assert not getattr(lint_result, "isError", False)
            lint_payload = json.loads(lint_result.content[0].text)
            assert lint_payload["summary"]["total_violations"] > 0

            dry_result = await client.call_tool(
                "fix", {"paths": ["models/stg_customers.sql"], "apply": False}
            )
            assert not getattr(dry_result, "isError", False)
            dry_payload = json.loads(dry_result.content[0].text)
            assert dry_payload["files"][0]["changed"] is True
            assert dry_payload["files"][0]["diff"]
            assert MODEL.read_text(encoding="utf-8") == original

            apply_result = await client.call_tool(
                "fix", {"paths": ["models/stg_customers.sql"], "apply": True}
            )
            assert not getattr(apply_result, "isError", False)
            apply_payload = json.loads(apply_result.content[0].text)
            assert apply_payload["files"][0]["changed"] is True
            assert MODEL.read_text(encoding="utf-8") != original

            reload_result = await client.call_tool("reload", {})
            assert "reloaded" in reload_result.content[0].text
    finally:
        MODEL.write_text(original, encoding="utf-8")
