"""Automated tests for the SQLite Lab MCP server.

Covers the db.py adapter directly (fast, no MCP protocol overhead) and the
FastMCP tool/resource surface end-to-end through an in-process Client.
Each test gets its own throwaway SQLite file so tests never interfere with
each other or with implementation/lab.db.
"""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db import SQLiteAdapter, ValidationError
from init_db import create_database


@pytest.fixture()
def adapter(tmp_path):
    db_path = tmp_path / "test.db"
    create_database(db_path, reset=True)
    return SQLiteAdapter(db_path)


# ---------------------------------------------------------------------------
# db.py / SQLiteAdapter unit tests
# ---------------------------------------------------------------------------

def test_list_tables(adapter):
    assert set(adapter.list_tables()) == {"students", "courses", "enrollments"}


def test_get_table_schema_unknown_table(adapter):
    with pytest.raises(ValidationError):
        adapter.get_table_schema("not_a_table")


def test_search_filters_and_pagination(adapter):
    result = adapter.search("students", filters={"cohort": "A1"})
    assert result["returned"] == 2
    assert all(row["cohort"] == "A1" for row in result["rows"])

    paged = adapter.search("students", limit=1, offset=1, order_by="id")
    assert paged["returned"] == 1
    assert paged["total_matching"] == 5


def test_search_unknown_table_raises(adapter):
    with pytest.raises(ValidationError):
        adapter.search("nope")


def test_search_unknown_column_filter_raises(adapter):
    with pytest.raises(ValidationError):
        adapter.search("students", filters={"nope": "x"})


def test_search_unsupported_operator_raises(adapter):
    with pytest.raises(ValidationError):
        adapter.search("students", filters={"cohort": {"op": "~=", "value": "A1"}})


def test_insert_returns_payload(adapter):
    result = adapter.insert("students", {
        "name": "New Student",
        "email": "new@example.com",
        "cohort": "B1",
        "enrolled_on": "2025-07-02",
    })
    assert result["inserted"]["name"] == "New Student"
    assert result["row_id"] > 0


def test_insert_empty_raises(adapter):
    with pytest.raises(ValidationError):
        adapter.insert("students", {})


def test_insert_unknown_column_raises(adapter):
    with pytest.raises(ValidationError):
        adapter.insert("students", {"not_a_column": "x"})


def test_aggregate_count(adapter):
    result = adapter.aggregate("students", "count")
    assert result["rows"][0]["value"] == 5


def test_aggregate_avg_with_group_by(adapter):
    result = adapter.aggregate("enrollments", "avg", column="score", group_by="course_id")
    assert len(result["rows"]) == 3
    assert all("group_value" in row for row in result["rows"])


def test_aggregate_unsupported_metric_raises(adapter):
    with pytest.raises(ValidationError):
        adapter.aggregate("enrollments", "median", column="score")


def test_aggregate_missing_column_raises(adapter):
    with pytest.raises(ValidationError):
        adapter.aggregate("enrollments", "avg")


# ---------------------------------------------------------------------------
# End-to-end MCP tool/resource tests through fastmcp.Client
# ---------------------------------------------------------------------------

@pytest.fixture()
def mcp_client_env(tmp_path, monkeypatch):
    """Point the shared mcp_server module at a fresh temp database."""
    db_path = tmp_path / "mcp_test.db"
    create_database(db_path, reset=True)

    import mcp_server
    monkeypatch.setattr(mcp_server, "adapter", SQLiteAdapter(db_path))
    return mcp_server.mcp


def _run(coro):
    return asyncio.run(coro)


def test_mcp_tool_discovery(mcp_client_env):
    from fastmcp import Client

    async def _check():
        async with Client(mcp_client_env) as client:
            tools = await client.list_tools()
            return sorted(t.name for t in tools)

    assert _run(_check()) == ["aggregate", "insert", "search"]


def test_mcp_resource_discovery(mcp_client_env):
    from fastmcp import Client

    async def _check():
        async with Client(mcp_client_env) as client:
            resources = await client.list_resources()
            templates = await client.list_resource_templates()
            return [str(r.uri) for r in resources], [t.uriTemplate for t in templates]

    resource_uris, template_uris = _run(_check())
    assert "schema://database" in resource_uris
    assert "schema://table/{table_name}" in template_uris


def test_mcp_valid_search_call(mcp_client_env):
    from fastmcp import Client

    async def _check():
        async with Client(mcp_client_env) as client:
            result = await client.call_tool("search", {"table": "students", "filters": {"cohort": "A1"}})
            return result.data

    data = _run(_check())
    assert data["returned"] == 2


def test_mcp_invalid_search_call_returns_error(mcp_client_env):
    from fastmcp import Client

    async def _check():
        async with Client(mcp_client_env) as client:
            result = await client.call_tool("search", {"table": "not_a_table"})
            return result.data

    data = _run(_check())
    assert "error" in data


def test_mcp_table_schema_resource(mcp_client_env):
    from fastmcp import Client

    async def _check():
        async with Client(mcp_client_env) as client:
            contents = await client.read_resource("schema://table/students")
            return contents[0].text

    text = _run(_check())
    assert '"name": "cohort"' in text
