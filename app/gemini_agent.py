
import asyncio
import json
import os
import sys

from dotenv import load_dotenv
from google import genai
from google.genai import types
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

MODEL = "gemini-2.5-flash"


def convert_mcp_tools(mcp_tools):
    """Convert MCP tool schemas into Gemini function declarations."""
    declarations = []

    for tool in mcp_tools:
        declarations.append(
            types.FunctionDeclaration(
                name=tool.name,
                description=tool.description or tool.name,
                parameters_json_schema=tool.input_schema,
            )
        )

    return declarations





async def main():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing from .env")

    client = genai.Client(api_key=api_key)

    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "app.server"],
        cwd=PROJECT_ROOT,
    )

    async with stdio_client(server_params) as (read, write):
        print("DEBUG 1: MCP process started", flush=True)

        async with ClientSession(read, write) as session:
            print("DEBUG 2: Initializing MCP...", flush=True)

            await asyncio.wait_for(
                session.initialize(),
                timeout=15,
            )

            print("DEBUG 3: MCP initialized successfully", flush=True)

            mcp_result = await session.list_tools()

            print(
                f"DEBUG: Received {len(mcp_result.tools)} MCP tools",
                flush=True,
            )

            for tool in mcp_result.tools:
                print(f"DEBUG TOOL: {tool.name}", flush=True)

            available_tools = {
                tool.name for tool in mcp_result.tools
            }

            if not mcp_result.tools:
                raise RuntimeError(
                    "No MCP tools received. Check app/server.py tool definitions."
                )

            gemini_tool = types.Tool(
                function_declarations=convert_mcp_tools(
                    mcp_result.tools
                )
            )

            print("DEBUG 4: MCP tools loaded", flush=True)
            print("\n=== SME MySQL AI Agent ===")
            print("Available tools:")
            for tool in mcp_result.tools:
                print(f"- {tool.name}")

            print("\nAsk a question about your business data.")
            print("Type 'exit' to quit.\n", flush=True)

            history = []

            while True:
                try:
                    question = input("You: ").strip()
                except (EOFError, KeyboardInterrupt):
                    print("\nGoodbye!")
                    break

                if not question:
                    continue

                if question.lower() in {"exit", "quit"}:
                    print("Goodbye!")
                    break

                history.append(
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_text(text=question)
                        ],
                    )
                )

                for round_number in range(5):
                    try:
                        response = await client.aio.models.generate_content(
                            model=MODEL,
                            contents=history,
                            config=types.GenerateContentConfig(
                                tools=[gemini_tool],
                                system_instruction=(
                                    "You are an SME data analyst connected to a MySQL database "
                                    "through MCP tools. "
                                    "For every question that requires database information, "
                                    "you MUST call an appropriate MCP tool. "
                                    "Never merely print or suggest SQL as the final answer. "
                                    "Use list_tables to list tables, describe_table to inspect "
                                    "a table, and query_database for read-only SELECT queries. "
                                    "Only report results returned by the tools. "
                                    "Never invent database results."
                                ),
                            ),
                        )
                    except Exception as error:
                        print(f"\nGemini API error: {error}\n")
                        break

                    if not response.candidates:
                        print("\nGemini returned no response.\n")
                        break

                    model_content = response.candidates[0].content
                    history.append(model_content)

                    function_calls = response.function_calls or []

                    if not function_calls:
                        print(
                            "\nAgent: ",
                            response.text or "(No text response)",
                            "\n",
                        )
                        break

                    function_responses = []

                    for function_call in function_calls:
                        name = function_call.name
                        arguments = dict(function_call.args or {})

                        print(f"[Calling MCP tool: {name}]")

                        if name not in available_tools:
                            result_data = {
                                "error": f"Unknown tool: {name}"
                            }
                        else:
                            try:
                                tool_result = await session.call_tool(
                                    name,
                                    arguments,
                                )

                                result_data = {
                                    "isError": tool_result.is_error,
                                    "content": [
                                        item.text
                                        if hasattr(item, "text")
                                        else str(item)
                                        for item in tool_result.content
                                    ],
                                }
                            except Exception as error:
                                result_data = {
                                    "error": str(error)
                                }

                        function_responses.append(
                            types.Part.from_function_response(
                                name=name,
                                response=result_data,
                            )
                        )

                    history.append(
                        types.Content(
                            role="user",
                            parts=function_responses,
                        )
                    )
                else:
                    print(
                        "Agent: Maximum tool-call rounds reached.\n"
                    )


if __name__ == "__main__":
    asyncio.run(main())