
import os

import mysql.connector
from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer

load_dotenv()

mcp = MCPServer("SME MySQL Agent")


def get_db_connection():
    """Create a connection to the SME MySQL database."""
    return mysql.connector.connect(
        host=os.environ["MYSQL_HOST"],
        port=int(os.getenv("MYSQL_PORT", "3306")),
        database=os.environ["MYSQL_DATABASE"],
        user=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        connection_timeout=10,
    )


@mcp.tool()
def say_hello(name: str) -> str:
    """Return a welcome message for the SME agent user."""
    return f"Hello, {name}! Your MCP server is working."


@mcp.tool()
def list_tables() -> str:
    """List the tables available in the SME database."""
    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("SHOW TABLES")

        tables = [row[0] for row in cursor.fetchall()]

        if not tables:
            return "No tables found."

        return "Available database tables:\n" + "\n".join(
            f"- {table}" for table in tables
        )

    except (mysql.connector.Error, KeyError, ValueError) as error:
        return f"Database error: {error}"

    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()


@mcp.tool()
def describe_table(table_name: str) -> str:
    """Show column names and data types for a database table."""
    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        # Validate the name before using it in an SQL identifier.
        cursor.execute("SHOW TABLES")
        allowed_tables = {row[0] for row in cursor.fetchall()}

        if table_name not in allowed_tables:
            return (
                f"Table '{table_name}' was not found. "
                "Use list_tables to see available tables."
            )

        cursor.execute(f"DESCRIBE `{table_name}`")
        columns = cursor.fetchall()

        lines = [f"Schema for table '{table_name}':"]

        for column in columns:
            name, data_type, nullable, key, default, extra = column
            lines.append(
                f"- {name}: {data_type}, "
                f"nullable={nullable}, key={key or 'none'}"
            )

        return "\n".join(lines)

    except (mysql.connector.Error, KeyError, ValueError) as error:
        return f"Database error: {error}"

    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()


import re


@mcp.tool()
def query_database(sql: str) -> str:
    """Execute a single read-only SELECT query on the SME database.

    Only SELECT queries are allowed. Results are limited to 100 rows.
    """
    connection = None
    cursor = None

    try:
        query = sql.strip()

        # Allow one optional trailing semicolon only.
        if query.endswith(";"):
            query = query[:-1].strip()

        # Only allow SELECT statements.
        if not re.match(r"^SELECT\b", query, re.IGNORECASE):
            return "Rejected: only SELECT queries are allowed."

        # Block multiple statements and SQL comments.
        if ";" in query or "--" in query or "/*" in query or "#" in query:
            return "Rejected: multiple statements and SQL comments are not allowed."

        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(query)

        # Fetch at most 101 rows to detect oversized results.
        rows = cursor.fetchmany(101)

        if len(rows) > 100:
            return (
                "Query returned more than 100 rows. "
                "Please add a LIMIT clause of 100 or fewer."
            )

        if not rows:
            return "Query executed successfully. No rows found."

        import json
        return json.dumps(rows, default=str, ensure_ascii=False, indent=2)

    except mysql.connector.Error as error:
        return f"Database query error: {error}"

    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()


if __name__ == "__main__":
    import sys

    print("Starting SME MySQL MCP Server...", file=sys.stderr)
    mcp.run()
