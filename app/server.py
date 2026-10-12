
import os
import re
import sys

import mysql.connector
from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer

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
    """Execute a single read-only SELECT query."""
    query = sql.strip()

    if not re.match(r"(?is)^SELECT\b", query):
        raise ValueError("Only SELECT queries are allowed.")

    if ";" in query or "--" in query or "/*" in query or "#" in query:
        raise ValueError("Multiple statements and SQL comments are not allowed.")

    connection = get_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(query)
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
