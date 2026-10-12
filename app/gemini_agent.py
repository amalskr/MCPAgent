
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
        async with ClientSession(read, write) as session:
            await session.initialize()

            mcp_result = await session.list_tools()
            declarations = convert_mcp_tools(mcp_result.tools)

            print("Connected to MCP Server!")
            print("Available tools:")
            for tool in mcp_result.tools:
                print(f"- {tool.name}")

            gemini_tool = types.Tool(
                function_declarations=declarations
            )

            question = input("\nAsk your SME Agent: ").strip()

            if not question:
                print("Please enter a question.")
                return

            contents = [
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(text=question)
                    ],
                )
            ]

            for _ in range(5):
                response = await client.aio.models.generate_content(
                    model=MODEL,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        tools=[gemini_tool],
                        system_instruction=(
                            "You are an SME data analyst. "
                            "Use the available tools to answer questions "
                            "with real database results. Never invent results. "
                            "Only use read-only database operations."
                        ),
                    ),
                )

                if not response.candidates:
                    print("Gemini returned no candidates.")
                    return

                model_content = response.candidates[0].content
                contents.append(model_content)

                function_calls = response.function_calls or []

                if not function_calls:
                    print("\nGemini Response:")
                    print(response.text or "(No text response)")
                    return

                for function_call in function_calls:
                    tool_name = function_call.name
                    arguments = dict(function_call.args or {})

                    available_names = {
                        tool.name for tool in mcp_result.tools
                    }

                    if tool_name not in available_names:
                        tool_result = {
                            "error": f"Unknown tool: {tool_name}"
                        }
                    else:
                        print(f"\nCalling MCP tool: {tool_name}")
                        print(f"Arguments: {arguments}")

                        result = await session.call_tool(
                            tool_name,
                            arguments,
                        )

                        tool_result = {
                            "isError": result.is_error,
                            "content": [
                                {
                                    "type": item.type,
                                    "text": getattr(item, "text", ""),
                                }
                                for item in result.content
                            ],
                        }

                    contents.append(
                        types.Content(
                            role="user",
                            parts=[
                                types.Part.from_function_response(
                                    name=tool_name,
                                    response=tool_result,
                                )
                            ],
                        )
                    )

            print("Stopped after 5 tool-calling rounds.")


if __name__ == "__main__":
    asyncio.run(main())