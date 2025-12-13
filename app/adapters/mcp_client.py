import os
import shutil
import logging
from pathlib import Path
from contextlib import AsyncExitStack
from typing import Any, List, Dict, cast

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult
from app.domain.ports import ToolsPort

logger = logging.getLogger(__name__)

class JarvisMCPClient(ToolsPort):
    def __init__(self):
        self.exit_stack = AsyncExitStack()
        self.session: ClientSession | None = None
        
        # Path to your server script. Adjust if your structure is different.
        # Assuming servers/desktop/server.py based on typical structure
        self.base_dir = Path(__file__).resolve().parent.parent.parent
        self.script_path = self.base_dir / "servers" / "desktop" / "server.py"

    async def connect(self):
        if not self.script_path.exists():
            # Fallback for different project structures
            logger.warning(f"Server script not found at {self.script_path}, checking local...")
            self.script_path = Path("server.py").resolve()
            
        if not self.script_path.exists():
             raise FileNotFoundError(f"❌ Server script NOT found at: {self.script_path}")

        uv_path = shutil.which("uv")
        if not uv_path:
            raise RuntimeError("❌ 'uv' not found in PATH. Run 'pip install uv'")

        logger.info(f"Connecting to MCP server at: {self.script_path}")

        server_params = StdioServerParameters(
            command=uv_path, 
            args=["run", str(self.script_path)], 
            env={
                **os.environ,
                "PYTHONUNBUFFERED": "1"
            }
        )
        
        try:
            read, write = await self.exit_stack.enter_async_context(
                stdio_client(server_params)
            )
            
            self.session = await self.exit_stack.enter_async_context(
                ClientSession(read, write)
            )
            
            await self.session.initialize()
            
            # Quick health check
            tools = await self.session.list_tools()
            tool_names = [t.name for t in tools.tools]
            logger.info(f"✅ MCP Connected! Available Tools: {tool_names}")
            
        except Exception as e:
            logger.error(f"❌ MCP Connection Failed: {e}")
            raise e

    async def list_tools(self) -> List[Dict[str, Any]]:
        """
        Returns tools in the format the LLM Adapter expects.
        Maps MCP 'inputSchema' to 'args_schema'.
        """
        if not self.session:
            await self.connect()
        
        assert self.session is not None, "Session should be connected"
            
        result = await self.session.list_tools()
        
        tool_list = []
        for tool in result.tools:
            tool_list.append({
                "name": tool.name,
                "description": tool.description,
                "args_schema": tool.inputSchema # Critical mapping for OpenAI/VLLM
            })
            
        return tool_list
    
    async def call_tool(self, name: str, args: dict) -> str:
        if not self.session:
            raise RuntimeError("Client not connected")
        
        assert self.session is not None
            
        result: CallToolResult = await self.session.call_tool(name, arguments=args)
        
        output_text = []
        for content in result.content:
            if content.type == "text":
                output_text.append(content.text)
            elif content.type == "image":
                output_text.append("[Image returned]")
            elif content.type == "resource":
                # Cast to access uri attribute
                content_any = cast(Any, content)
                uri = getattr(content_any, 'uri', 'unknown')
                output_text.append(f"[Resource: {uri}]")
                
        return "\n".join(output_text)
    
    async def cleanup(self):
        await self.exit_stack.aclose()