"""Repeatable verification script for the SQLite Lab MCP server.

Connects to the FastMCP server in-process and walks through the checklist
from the lab rubric: tool discovery, resource discovery, valid calls, and
invalid calls with clear errors.

Usage:
    python verify_server.py
"""

import asyncio
import json

from fastmcp import Client

from init_db import DB_PATH, create_database
from mcp_server import mcp


def _print_header(title):
    print(f"\n=== {title} ===")


async def main():
    # Reset to the seed dataset first so this script is safe to re-run any
    # number of times (e.g. the insert step below would otherwise hit a
    # UNIQUE constraint on a leftover row from a previous run).
    create_database(DB_PATH, reset=True)

    async with Client(mcp) as client:
        _print_header("1. Tool discovery")
        tools = await client.list_tools()
        tool_names = sorted(t.name for t in tools)
        print("Discovered tools:", tool_names)
        assert tool_names == ["aggregate", "insert", "search"], "Unexpected tool set"

        _print_header("2. Resource discovery")
        resources = await client.list_resources()
        templates = await client.list_resource_templates()
        print("Static resources:", [r.uri for r in resources])
        print("Resource templates:", [t.uriTemplate for t in templates])

        _print_header("3. Read schema://database")
        db_schema = await client.read_resource("schema://database")
        print(db_schema[0].text[:400], "...")

        _print_header("4. Read schema://table/students")
        table_schema = await client.read_resource("schema://table/students")
        print(table_schema[0].text)

        _print_header("5. Valid call: search students in cohort A1")
        result = await client.call_tool("search", {"table": "students", "filters": {"cohort": "A1"}})
        print(json.dumps(result.data, indent=2))

        _print_header("6. Valid call: insert a new student")
        result = await client.call_tool("insert", {
            "table": "students",
            "values": {
                "name": "Verify Bot",
                "email": "verify.bot@example.com",
                "cohort": "A1",
                "enrolled_on": "2025-07-02",
            },
        })
        print(json.dumps(result.data, indent=2))

        _print_header("7. Valid call: aggregate average score by cohort")
        result = await client.call_tool("aggregate", {
            "table": "enrollments",
            "metric": "avg",
            "column": "score",
        })
        print(json.dumps(result.data, indent=2))

        _print_header("8. Invalid call: unknown table")
        result = await client.call_tool("search", {"table": "not_a_table"})
        print(json.dumps(result.data, indent=2))
        assert "error" in result.data, "Expected an error payload for unknown table"

        _print_header("9. Invalid call: unknown column filter")
        result = await client.call_tool("search", {
            "table": "students",
            "filters": {"not_a_column": "x"},
        })
        print(json.dumps(result.data, indent=2))
        assert "error" in result.data

        _print_header("10. Invalid call: unsupported operator")
        result = await client.call_tool("search", {
            "table": "students",
            "filters": {"cohort": {"op": "~=", "value": "A1"}},
        })
        print(json.dumps(result.data, indent=2))
        assert "error" in result.data

        _print_header("11. Invalid call: empty insert")
        result = await client.call_tool("insert", {"table": "students", "values": {}})
        print(json.dumps(result.data, indent=2))
        assert "error" in result.data

        _print_header("12. Invalid call: bad aggregate metric")
        result = await client.call_tool("aggregate", {
            "table": "enrollments",
            "metric": "median",
            "column": "score",
        })
        print(json.dumps(result.data, indent=2))
        assert "error" in result.data

    print("\nAll verification checks passed.")


if __name__ == "__main__":
    asyncio.run(main())
