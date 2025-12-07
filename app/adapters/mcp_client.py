import os
import shutil
import logging
from pathlib import Path
from contextlib import AsyncExitStack
from typing import Any, List, Dict

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult

# Configure logging
logger = logging.getLogger("mcp_client")
logger.setLevel(logging.INFO)

class JarvisMCPClient:
    def __init__(self):
        self.exit_stack = AsyncExitStack()
        self.session: ClientSession | None = None
        
        # Resolve path relative to THIS file:
        # app/adapters/mcp_client.py -> app/adapters -> app -> ROOT
        self.base_dir = Path(__file__).resolve().parent.parent.parent
        self.script_path = self.base_dir / "servers" / "desktop" / "server.py"

    async def connect(self):
        # 1. Validation
        if not self.script_path.exists():
            raise FileNotFoundError(f"❌ Server script NOT found at: {self.script_path}")

        uv_path = shutil.which("uv")
        if not uv_path:
            raise RuntimeError("❌ 'uv' not found in PATH. Run 'pip install uv'")

        print(f"[MCP] Connecting to server at: {self.script_path}")

        # 2. Configure Transport
        # We run 'uv run /path/to/server.py'
        # uv handles the dependencies defined in the script header.
        server_params = StdioServerParameters(
            command=uv_path, 
            args=["run", str(self.script_path)], 
            env={
                **os.environ,
                "PYTHONUNBUFFERED": "1" # Important for streaming JSON
            }
        )
        
        try:
            # 3. Start Transport
            read, write = await self.exit_stack.enter_async_context(
                stdio_client(server_params)
            )
            
            # 4. Start Session
            self.session = await self.exit_stack.enter_async_context(
                ClientSession(read, write)
            )
            
            await self.session.initialize()
            
            # 5. List Tools (Confirmation)
            tools = await self.session.list_tools()
            tool_names = [t.name for t in tools.tools]
            print(f"[MCP] ✅ Connected! Available Tools: {tool_names}")
            
        except Exception as e:
            print(f"[MCP] ❌ Connection Failed: {e}")
            raise e

    async def list_tools(self) -> List[Dict[str, Any]]:
        """Returns tools in a format the LLM Router expects."""
        if not self.session:
            await self.connect()
            
        result = await self.session.list_tools()
        
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "args_schema": tool.inputSchema
            }
            for tool in result.tools
        ]
    
    async def call_tool(self, name: str, args: dict) -> str:
        if not self.session:
            raise RuntimeError("Client not connected")
            
        result: CallToolResult = await self.session.call_tool(name, arguments=args)
        
        output_text = []
        for content in result.content:
            if content.type == "text":
                output_text.append(content.text)
            elif content.type == "image":
                output_text.append("[Image returned]")
                
        return "\n".join(output_text)
    
    async def cleanup(self):
        await self.exit_stack.aclose()