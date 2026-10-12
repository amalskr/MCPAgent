
import os
import re
import sys

import mysql.connector
from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer
import sqlglot
from sqlglot import exp

load_dotenv()

mcp = MCPServer("SME MySQL Agent")


def get_connection():
    return mysql.connector.connect(
        host=os.environ["MYSQL_HOST"],
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        database=os.environ["MYSQL_DATABASE"],
        connection_timeout=10,
    )


@mcp.tool()
def say_hello(name: str = "there") -> str:
    """Check whether the SME MySQL MCP server is working."""
    return f"Hello {name}! MCP server is working."


@mcp.tool()
def list_tables() -> list[str]:
    """List tables in the configured MySQL database."""
    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("SHOW TABLES")
        return [row[0] for row in cursor.fetchall()]
    finally:
        connection.close()


@mcp.tool()
def describe_table(table_name: str) -> list[dict]:
    """Return column information for a table in the database."""
    if not re.fullmatch(r"[A-Za-z0-9_]+", table_name):
        raise ValueError("Invalid table name.")

    connection = get_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(f"DESCRIBE `{table_name}`")
        return cursor.fetchall()
    finally:
        connection.close()


@mcp.tool()
def query_database(sql: str) -> list[dict]:
    """Execute one read-only SELECT query with a maximum of 1000 rows."""

    query = sql.strip()

    if not query:
        raise ValueError("SQL query cannot be empty.")

    # Allow one optional trailing semicolon.
    query = query.rstrip()

    if query.endswith(";"):
        query = query[:-1].rstrip()

    # Reject internal semicolons and SQL comments.
    if ";" in query or "--" in query or "/*" in query or "#" in query:
        raise ValueError(
            "Multiple statements and SQL comments are not allowed."
        )

    # Parse SQL using the MySQL dialect.
    try:
        statements = sqlglot.parse(query, read="mysql")
    except Exception as error:
        raise ValueError("Invalid SQL syntax.") from error

    if len(statements) != 1 or statements[0] is None:
        raise ValueError("Exactly one SQL statement is required.")

    parsed = statements[0]

    # Allow only SELECT statements.
    if not isinstance(parsed, exp.Select):
        raise ValueError("Only SELECT queries are allowed.")

    # Reject SELECT INTO operations.
    if parsed.find(exp.Into) is not None:
        raise ValueError("SELECT INTO operations are not allowed.")

    # Apply a default row limit if one was not supplied.
    MAX_ROWS = 1000

    limit_node = parsed.args.get("limit")

    if limit_node is None:
        parsed = parsed.limit(MAX_ROWS)
    else:
        limit_value = limit_node.expression

        if not isinstance(limit_value, exp.Literal):
            raise ValueError("LIMIT must be a fixed integer.")

        if limit_value.is_string:
            raise ValueError("LIMIT must be an integer.")

        try:
            requested_limit = int(limit_value.this)
        except (TypeError, ValueError):
            raise ValueError("LIMIT must be an integer.")

        if requested_limit < 1:
            raise ValueError("LIMIT must be at least 1.")

        if requested_limit > MAX_ROWS:
            parsed = parsed.limit(MAX_ROWS)

    safe_query = parsed.sql(dialect="mysql")

    connection = get_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(safe_query)
        return cursor.fetchall()
    finally:
        connection.close()



if __name__ == "__main__":
    print(
        "Starting SME MySQL MCP Server...",
        file=sys.stderr,
        flush=True,
    )
    mcp.run()
