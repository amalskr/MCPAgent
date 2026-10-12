
import asyncio
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

SYSTEM_INSTRUCTION = """
You are an SME data analyst connected to a MySQL database
through MCP tools.

For every question that requires database information,
you MUST call an appropriate MCP tool.

Never invent database results.
Use list_tables to list tables, describe_table to inspect
a table, and query_database for read-only SELECT queries.
Only report results returned by the tools.
"""


def convert_mcp_tools(mcp_tools):
    return [
        types.FunctionDeclaration(
            name=tool.name,
            description=tool.description or tool.name,
            parameters_json_schema=tool.input_schema,
        )
        for tool in mcp_tools
    ]


async def ask_agent_async(question, history):
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing from .env")

    client = genai.Client(api_key=api_key)

    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "app.server"],
        cwd=PROJECT_ROOT,
    )

    tool_outputs = []

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await asyncio.wait_for(
                session.initialize(),
                timeout=15,
            )

            mcp_result = await session.list_tools()

            if not mcp_result.tools:
                raise RuntimeError("No MCP tools received.")

            available_tools = {
                tool.name for tool in mcp_result.tools
            }

            gemini_tool = types.Tool(
                function_declarations=convert_mcp_tools(
                    mcp_result.tools
                )
            )

            history.append(
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=question)],
                )
            )

            for _ in range(5):
                response = await client.aio.models.generate_content(
                    model=MODEL,
                    contents=history,
                    config=types.GenerateContentConfig(
                        tools=[gemini_tool],
                        system_instruction=SYSTEM_INSTRUCTION,
                    ),
                )

                if not response.candidates:
                    raise RuntimeError("Gemini returned no response.")

                model_content = response.candidates[0].content
                history.append(model_content)

                function_calls = response.function_calls or []

                if not function_calls:
                    return (
                        response.text or "(No text response)",
                        history,
                        tool_outputs,
                    )

                function_responses = []

                for call in function_calls:
                    name = call.name
                    arguments = dict(call.args or {})

                    if name not in available_tools:
                        result_data = {
                            "error": f"Unknown MCP tool: {name}"
                        }
                    else:
                        try:
                            result = await session.call_tool(
                                name,
                                arguments,
                            )

                            content = [
                                item.text
                                if hasattr(item, "text")
                                else str(item)
                                for item in result.content
                            ]

                            result_data = {
                                "isError": result.is_error,
                                "content": content,
                            }

                            tool_outputs.append({
                                "tool": name,
                                "arguments": arguments,
                                "result": content,
                                "structured": result.structured_content,
                                "is_error": result.is_error,
                            })

                        except Exception as error:
                            result_data = {"error": str(error)}

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

            return (
                "Maximum tool-call rounds reached. Please try again.",
                history,
                tool_outputs,
            )


def ask_agent(question, history):
    return asyncio.run(ask_agent_async(question, history))