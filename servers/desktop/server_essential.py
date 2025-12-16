#!/usr/bin/env python3
# /// script
# dependencies = [
#   "fastmcp",
#   "docker",
# ]
# ///

"""
Jarvis Essential MCP Server
---------------------------
Minimal MCP server with only tools that require system-level access
and cannot be done through Python skills in the sandbox.

Essential tools:
- File system operations (read/write files on host)
- Shell command execution (on host system)
- Docker container management
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import List

import docker
from fastmcp import FastMCP

# =============================================================================
# 🔧 CONFIGURATION
# =============================================================================

SERVER_NAME = "Jarvis Essential"
DATA_DIR = Path.home() / "jarvis_data"
DATA_DIR.mkdir(exist_ok=True)

mcp = FastMCP(SERVER_NAME)

# =============================================================================
# 📁 FILE SYSTEM OPERATIONS (Host System Access)
# =============================================================================

def _is_safe_path(path: Path) -> bool:
    """Prevent path traversal attacks."""
    try:
        path = path.resolve()
        home = Path.home()
        # Allow home directory and subdirectories only
        return str(path).startswith(str(home))
    except:
        return False

@mcp.tool()
def list_directory(path: str = ".") -> str:
    """
    List files and folders in a directory on the HOST system.
    Use this to explore the file system outside the sandbox.
    """
    try:
        target = Path(path).expanduser().resolve()
        if not _is_safe_path(target):
            return f"❌ Access denied: {path} (outside home directory)"
        
        items = sorted(target.iterdir(), key=lambda x: (not x.is_dir(), x.name))
        output = [f"📂 {target}\n"]
        for item in items:
            icon = "📁" if item.is_dir() else "📄"
            output.append(f"{icon} {item.name}")
        return "\n".join(output)
    except Exception as e:
        return f"❌ Error: {str(e)}"

@mcp.tool()
def read_file(filepath: str) -> str:
    """
    Read a file from the HOST file system.
    Use this to access files outside the sandbox.
    """
    try:
        target = Path(filepath).expanduser().resolve()
        if not _is_safe_path(target):
            return f"❌ Access denied: {filepath}"
        
        return target.read_text()
    except Exception as e:
        return f"❌ Error reading file: {str(e)}"

@mcp.tool()
def write_file(filepath: str, content: str) -> str:
    """
    Write content to a file on the HOST file system.
    Creates parent directories if needed.
    """
    try:
        target = Path(filepath).expanduser().resolve()
        if not _is_safe_path(target):
            return f"❌ Access denied: {filepath}"
        
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return f"✅ Written {len(content)} chars to {target}"
    except Exception as e:
        return f"❌ Error writing file: {str(e)}"

# =============================================================================
# 🖥️ SYSTEM OPERATIONS (Shell & Docker)
# =============================================================================

@mcp.tool()
def run_shell_command(command: str) -> str:
    """
    Execute a shell command on the HOST system.
    
    ⚠️ CAUTION: This runs commands directly on the host.
    Use sandbox Python execution for most tasks.
    
    Use cases:
    - Git operations
    - System package installation (apt, brew, etc.)
    - Process management
    - System configuration
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(Path.home())
        )
        
        output = []
        if result.stdout:
            output.append("STDOUT:")
            output.append(result.stdout)
        if result.stderr:
            output.append("STDERR:")
            output.append(result.stderr)
        
        output.append(f"\nExit code: {result.returncode}")
        return "\n".join(output)
    
    except subprocess.TimeoutExpired:
        return "❌ Command timed out (30s limit)"
    except Exception as e:
        return f"❌ Error: {str(e)}"

@mcp.tool()
def manage_docker(action: str, container_name: str) -> str:
    """
    Manage Docker containers on the HOST system.
    
    Actions:
    - list: Show all containers
    - start: Start a container
    - stop: Stop a container
    - restart: Restart a container
    - logs: Get container logs
    - inspect: Get container details
    """
    try:
        client = docker.from_env()
        
        if action == "list":
            containers = client.containers.list(all=True)
            output = ["Container Status:"]
            for c in containers:
                status = "🟢" if c.status == "running" else "🔴"
                output.append(f"{status} {c.name} ({c.status})")
            return "\n".join(output)
        
        # Find container
        try:
            container = client.containers.get(container_name)
        except docker.errors.NotFound:
            return f"❌ Container '{container_name}' not found"
        
        if action == "start":
            container.start()
            return f"✅ Started '{container_name}'"
        
        elif action == "stop":
            container.stop()
            return f"✅ Stopped '{container_name}'"
        
        elif action == "restart":
            container.restart()
            return f"✅ Restarted '{container_name}'"
        
        elif action == "logs":
            logs = container.logs(tail=50).decode('utf-8')
            return f"Last 50 lines of '{container_name}':\n{logs}"
        
        elif action == "inspect":
            info = container.attrs
            return json.dumps({
                "name": info['Name'],
                "status": info['State']['Status'],
                "image": info['Config']['Image'],
                "ports": info['NetworkSettings']['Ports']
            }, indent=2)
        
        else:
            return f"❌ Unknown action: {action}"
    
    except Exception as e:
        return f"❌ Docker error: {str(e)}"

# =============================================================================
# 🚀 SERVER ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    mcp.run()
