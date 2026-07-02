"""SQLite data access layer for the MCP lab server.

All SQL is built with a fixed set of validated identifiers and bound
parameters. Table names, column names, operators, and aggregate metrics are
always checked against an allow-list derived from the live schema before
they are ever placed into a SQL string.
"""

import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).parent / "lab.db"

SUPPORTED_OPERATORS = {
    "=": "=",
    "!=": "!=",
    ">": ">",
    ">=": ">=",
    "<": "<",
    "<=": "<=",
    "like": "LIKE",
    "in": "IN",
}

SUPPORTED_METRICS = {"count", "avg", "sum", "min", "max"}

MAX_LIMIT = 200


class ValidationError(Exception):
    """Raised when a request cannot be safely executed."""


class SQLiteAdapter:
    """Database access layer backing the search/insert/aggregate MCP tools."""

    def __init__(self, db_path=DEFAULT_DB_PATH):
        self.db_path = str(db_path)

    def connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def list_tables(self):
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        return [row["name"] for row in rows]

    def get_table_schema(self, table):
        self._validate_table(table)
        with self.connect() as conn:
            rows = conn.execute(f"PRAGMA table_info('{table}')").fetchall()
        return [
            {
                "name": row["name"],
                "type": row["type"],
                "not_null": bool(row["notnull"]),
                "default": row["dflt_value"],
                "primary_key": bool(row["pk"]),
            }
            for row in rows
        ]

    def get_database_schema(self):
        return {table: self.get_table_schema(table) for table in self.list_tables()}

    # -- validation helpers -------------------------------------------------

    def _validate_table(self, table):
        if not isinstance(table, str) or table not in self.list_tables():
            raise ValidationError(f"Unknown table: {table!r}")

    def _column_names(self, table):
        return [col["name"] for col in self.get_table_schema(table)]

    def _validate_columns(self, table, columns):
        valid = self._column_names(table)
        for column in columns:
            if column not in valid:
                raise ValidationError(f"Unknown column {column!r} on table {table!r}")
        return valid

    def _build_where(self, table, filters):
        """Translate a {column: value | {"op": ..., "value": ...}} mapping
        into a parameterized SQL WHERE clause."""
        if not filters:
            return "", []

        if not isinstance(filters, dict):
            raise ValidationError("filters must be an object mapping column -> value")

        valid_columns = self._column_names(table)
        clauses = []
        params = []

        for column, spec in filters.items():
            if column not in valid_columns:
                raise ValidationError(f"Unknown filter column {column!r} on table {table!r}")

            if isinstance(spec, dict):
                op = spec.get("op", "=")
                value = spec.get("value")
            else:
                op, value = "=", spec

            if op not in SUPPORTED_OPERATORS:
                raise ValidationError(
                    f"Unsupported filter operator {op!r}. "
                    f"Supported: {sorted(SUPPORTED_OPERATORS)}"
                )

            sql_op = SUPPORTED_OPERATORS[op]
            if op == "in":
                if not isinstance(value, (list, tuple)) or not value:
                    raise ValidationError("'in' filter requires a non-empty list value")
                placeholders = ", ".join("?" for _ in value)
                clauses.append(f'"{column}" {sql_op} ({placeholders})')
                params.extend(value)
            else:
                clauses.append(f'"{column}" {sql_op} ?')
                params.append(value)

        return " WHERE " + " AND ".join(clauses), params

    # -- tool-facing operations ----------------------------------------------

    def search(self, table, columns=None, filters=None, limit=20, offset=0,
               order_by=None, descending=False):
        self._validate_table(table)
        valid_columns = self._column_names(table)

        if columns:
            self._validate_columns(table, columns)
            select_cols = ", ".join(f'"{c}"' for c in columns)
        else:
            select_cols = "*"

        if not isinstance(limit, int) or limit <= 0:
            raise ValidationError("limit must be a positive integer")
        if not isinstance(offset, int) or offset < 0:
            raise ValidationError("offset must be a non-negative integer")
        limit = min(limit, MAX_LIMIT)

        where_sql, params = self._build_where(table, filters)

        order_sql = ""
        if order_by is not None:
            if order_by not in valid_columns:
                raise ValidationError(f"Unknown order_by column {order_by!r} on table {table!r}")
            direction = "DESC" if descending else "ASC"
            order_sql = f' ORDER BY "{order_by}" {direction}'

        query = f'SELECT {select_cols} FROM "{table}"{where_sql}{order_sql} LIMIT ? OFFSET ?'
        params = params + [limit, offset]

        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
            total_query = f'SELECT COUNT(*) AS total FROM "{table}"{where_sql}'
            total = conn.execute(total_query, params[:-2]).fetchone()["total"]

        return {
            "rows": [dict(row) for row in rows],
            "returned": len(rows),
            "total_matching": total,
            "limit": limit,
            "offset": offset,
        }

    def insert(self, table, values):
        self._validate_table(table)
        if not values or not isinstance(values, dict):
            raise ValidationError("insert requires a non-empty object of column -> value")

        self._validate_columns(table, values.keys())

        columns = list(values.keys())
        placeholders = ", ".join("?" for _ in columns)
        column_sql = ", ".join(f'"{c}"' for c in columns)
        query = f'INSERT INTO "{table}" ({column_sql}) VALUES ({placeholders})'

        with self.connect() as conn:
            cursor = conn.execute(query, [values[c] for c in columns])
            conn.commit()
            new_id = cursor.lastrowid
            row = conn.execute(f'SELECT * FROM "{table}" WHERE rowid = ?', (new_id,)).fetchone()

        return {"inserted": dict(row) if row else values, "row_id": new_id}

    def aggregate(self, table, metric, column=None, filters=None, group_by=None):
        self._validate_table(table)
        valid_columns = self._column_names(table)

        if not isinstance(metric, str) or metric.lower() not in SUPPORTED_METRICS:
            raise ValidationError(
                f"Unsupported metric {metric!r}. Supported: {sorted(SUPPORTED_METRICS)}"
            )
        metric = metric.lower()

        if metric == "count":
            target = "*" if column is None else f'"{column}"'
            if column is not None and column not in valid_columns:
                raise ValidationError(f"Unknown column {column!r} on table {table!r}")
        else:
            if column is None or column not in valid_columns:
                raise ValidationError(f"Metric {metric!r} requires a valid column")
            target = f'"{column}"'

        group_sql = ""
        select_prefix = ""
        if group_by is not None:
            if group_by not in valid_columns:
                raise ValidationError(f"Unknown group_by column {group_by!r} on table {table!r}")
            select_prefix = f'"{group_by}" AS group_value, '
            group_sql = f' GROUP BY "{group_by}"'

        where_sql, params = self._build_where(table, filters)
        query = (
            f'SELECT {select_prefix}{metric.upper()}({target}) AS value '
            f'FROM "{table}"{where_sql}{group_sql}'
        )

        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()

        return {"metric": metric, "column": column, "group_by": group_by,
                "rows": [dict(row) for row in rows]}
