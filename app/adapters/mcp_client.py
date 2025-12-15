import os
import json
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
    def __init__(self, config_path: str | None = None):
        self.exit_stack = AsyncExitStack()
        self.sessions: Dict[str, ClientSession] = {}
        
        # Load configuration from JSON file
        self.base_dir = Path(__file__).resolve().parent.parent.parent
        
        if config_path is None:
            config_path = str(self.base_dir / "mcp_servers.json")
        
        self.config_path = Path(config_path)
        self.server_configs = self._load_config()

    def _load_config(self) -> Dict[str, Dict[str, Any]]:
        """Load MCP server configurations from JSON file."""
        if not self.config_path.exists():
            logger.warning(f"MCP config not found at {self.config_path}, using defaults")
            return self._get_default_config()
        
        try:
            with open(self.config_path, 'r') as f:
                config_raw = json.load(f)
            
            # Resolve environment variables in config
            config = self._resolve_env_vars(config_raw)
            
            logger.info(f"Loaded MCP config from {self.config_path}")
            return config.get("servers", {})
        except Exception as e:
            logger.error(f"Failed to load MCP config: {e}, using defaults")
            return self._get_default_config()
    
    def _resolve_env_vars(self, obj: Any) -> Any:
        """Recursively resolve ${VAR_NAME} placeholders with environment variables."""
        if isinstance(obj, dict):
            return {k: self._resolve_env_vars(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._resolve_env_vars(item) for item in obj]
        elif isinstance(obj, str):
            # Replace ${VAR_NAME} with environment variable
            import re
            def replacer(match):
                var_name = match.group(1)
                value = os.getenv(var_name, "")
                # If env var not found, log warning and return empty string
                if not value:
                    logger.warning(f"Environment variable '{var_name}' not set")
                    return ""
                return value
            
            pattern = r'\$\{([^}]+)\}'
            result = re.sub(pattern, replacer, obj)
            
            # Handle boolean strings
            if isinstance(result, str):
                if result.lower() == 'true':
                    return True
                elif result.lower() == 'false':
                    return False
            
            return result
        else:
            return obj
    
    def _get_default_config(self) -> Dict[str, Dict[str, Any]]:
        """Default configuration if JSON file doesn't exist."""
        return {
            "desktop": {
                "script": str(self.base_dir / "servers" / "desktop" / "server.py"),
                "command": "uv",
                "args_template": ["run", "{script}"],
                "enabled": True
            },
            "google_calendar": {
                "command": "npx",
                "args_template": ["-y", "@cocal/google-calendar-mcp"],
                "enabled": False,  # Disabled by default - requires OAuth setup
                "env": {
                    "GOOGLE_OAUTH_CREDENTIALS": "/path/to/your/gcp-oauth.keys.json"
                }
            }
        }

    async def _connect_server(self, server_name: str, config: Dict[str, Any]) -> ClientSession:
        """Connect to a single MCP server."""
        # Check if server is enabled
        if not config.get("enabled", True):
            logger.info(f"Server '{server_name}' is disabled in config")
            raise ValueError(f"Server '{server_name}' is disabled")
        
        script_path = config.get("script")
        command = config["command"]
        
        # Build arguments
        if script_path:
            script_path = Path(script_path)
            if not script_path.exists():
                raise FileNotFoundError(f"❌ Server script not found at: {script_path}")
            args = [arg.format(script=str(script_path)) for arg in config["args_template"]]
        else:
            args = config["args_template"]
        
        # Check command exists
        cmd_path = shutil.which(command)
        if not cmd_path:
            raise RuntimeError(f"❌ '{command}' not found in PATH")

        logger.info(f"Connecting to MCP server '{server_name}': {command} {' '.join(args)}")

        # Get custom env vars if specified
        env = {
            **os.environ,
            "PYTHONUNBUFFERED": "1",
            **config.get("env", {})
        }

        server_params = StdioServerParameters(
            command=cmd_path,
            args=args,
            env=env
        )
        
        read, write = await self.exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        
        session = await self.exit_stack.enter_async_context(
            ClientSession(read, write)
        )
        
        await session.initialize()
        
        # Health check
        tools = await session.list_tools()
        tool_names = [t.name for t in tools.tools]
        logger.info(f"✅ MCP '{server_name}' Connected! Tools: {tool_names}")
        
        return session

    async def connect(self):
        """Connect to all configured MCP servers."""
        for server_name, config in self.server_configs.items():
            try:
                session = await self._connect_server(server_name, config)
                self.sessions[server_name] = session
            except Exception as e:
                logger.error(f"❌ Failed to connect to '{server_name}': {e}")
                # Continue connecting to other servers
                continue
        
        if not self.sessions:
            raise RuntimeError("❌ No MCP servers connected successfully")

    async def list_tools(self) -> List[Dict[str, Any]]:
        """
        Returns tools from all connected MCP servers.
        Maps MCP 'inputSchema' to 'args_schema'.
        """
        if not self.sessions:
            await self.connect()
        
        tool_list = []
        for server_name, session in self.sessions.items():
            result = await session.list_tools()
            
            for tool in result.tools:
                tool_list.append({
                    "name": tool.name,
                    "description": tool.description,
                    "args_schema": tool.inputSchema,
                    "_server": server_name  # Track which server owns this tool
                })
        
        return tool_list
    
    async def call_tool(self, name: str, args: dict) -> str:
        """Call a tool on the appropriate MCP server."""
        if not self.sessions:
            raise RuntimeError("No MCP servers connected")
        
        # Find which server has this tool
        target_session = None
        for session in self.sessions.values():
            tools = await session.list_tools()
            if any(t.name == name for t in tools.tools):
                target_session = session
                break
        
        if not target_session:
            raise ValueError(f"Tool '{name}' not found in any connected MCP server")
        
        result: CallToolResult = await target_session.call_tool(name, arguments=args)
        
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