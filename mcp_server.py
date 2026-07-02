"""FastMCP server exposing search/insert/aggregate tools over a SQLite lab DB."""

import json
import sys
from pathlib import Path

from fastmcp import FastMCP

from db import SQLiteAdapter, ValidationError
from init_db import DB_PATH, create_database

if not Path(DB_PATH).exists():
    create_database()

mcp = FastMCP("SQLite Lab MCP Server")
adapter = SQLiteAdapter(DB_PATH)


def _error(exc: ValidationError):
    return {"error": str(exc)}


@mcp.tool(name="search")
def search(table: str, filters: dict = None, columns: list = None, limit: int = 20,
           offset: int = 0, order_by: str = None, descending: bool = False):
    """Search rows in a table with optional filters, column selection,
    ordering, and pagination.

    filters: object mapping column -> value (equality) or
             column -> {"op": "=|!=|>|>=|<|<=|like|in", "value": ...}
    """
    try:
        return adapter.search(table, columns=columns, filters=filters, limit=limit,
                               offset=offset, order_by=order_by, descending=descending)
    except ValidationError as exc:
        return _error(exc)


@mcp.tool(name="insert")
def insert(table: str, values: dict):
    """Insert one row into a table. values is an object of column -> value.
    Returns the inserted row, including the generated primary key."""
    try:
        return adapter.insert(table, values)
    except ValidationError as exc:
        return _error(exc)


@mcp.tool(name="aggregate")
def aggregate(table: str, metric: str, column: str = None, filters: dict = None,
              group_by: str = None):
    """Compute an aggregate (count, avg, sum, min, max) over a table,
    with optional filters and group_by column."""
    try:
        return adapter.aggregate(table, metric, column=column, filters=filters,
                                  group_by=group_by)
    except ValidationError as exc:
        return _error(exc)


@mcp.resource("schema://database")
def database_schema():
    """Full schema snapshot of every table in the database."""
    return json.dumps(adapter.get_database_schema(), indent=2)


@mcp.resource("schema://table/{table_name}")
def table_schema(table_name: str):
    """Schema of a single table."""
    try:
        return json.dumps(adapter.get_table_schema(table_name), indent=2)
    except ValidationError as exc:
        return json.dumps(_error(exc))


if __name__ == "__main__":
    transport = sys.argv[1] if len(sys.argv) > 1 else "stdio"
    mcp.run(transport=transport)
