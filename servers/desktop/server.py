#!/usr/bin/env python3
# /// script
# dependencies = [
#   "fastmcp",
#   "docker",
#   "psutil", 
# ]
# ///

"""
Jarvis Headless MCP Server
--------------------------
Provides system monitoring, sandboxed code execution, and productivity tools
for a headless Linux/Proxmox environment.
"""

import ast
import datetime
import json
import socket
import subprocess
import tempfile
import os
import sys  # Required for safe logging (stderr)
from pathlib import Path
from typing import List, Dict, Any, Optional
import shutil
import re 

import docker
import psutil
from fastmcp import FastMCP

# =============================================================================
# CONFIGURATION & CONSTANTS
# =============================================================================

SERVER_NAME = "Jarvis Headless"
DATA_DIR = Path.home() / "jarvis_data"
WORKSPACE_DIR = DATA_DIR / "workspace"
NOTES_FILE = DATA_DIR / "notes.md"
TODO_FILE = DATA_DIR / "todos.json"
STATE_FILE = DATA_DIR / "state.json" 

# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

mcp = FastMCP(SERVER_NAME)

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _load_json(filepath: Path, default: Any = None) -> Any:
    if not filepath.exists():
        return default if default is not None else []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return default if default is not None else []

def _save_json(filepath: Path, data: Any) -> None:
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def _get_active_project() -> Optional[Path]:
    data = _load_json(STATE_FILE, default={})
    path_str = data.get("active_project")
    if path_str:
        path = Path(path_str)
        if path.exists() and path.is_dir():
            return path
    return None

def _run_subprocess(cmd: List[str], timeout: int = 5) -> str:
    try:
        use_shell = isinstance(cmd, str)
        result = subprocess.run(
            cmd, 
            shell=use_shell,
            capture_output=True, 
            text=True, 
            timeout=timeout
        )
        if result.returncode != 0:
            return f"Command Failed (Code {result.returncode}):\n{result.stderr.strip()}"
        return f"{result.stdout.strip()}"
    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {timeout}s."
    except Exception as e:
        return f"Execution Error: {str(e)}"

# =============================================================================
# 🧪 SANDBOXED COMPUTE & ENGINEERING
# =============================================================================

@mcp.tool()
def set_active_project(path: str) -> str:
    """Sets the active coding project directory."""
    p = Path(path).expanduser().resolve()
    if not p.exists() or not p.is_dir():
        return f"Error: Path not found or not a directory: {path}"
    
    state = _load_json(STATE_FILE, default={})
    state["active_project"] = str(p)
    _save_json(STATE_FILE, state)
    
    return f"Active project set to: {p}"

@mcp.tool()
def execute_python(code: str, dependencies: List[str] = []) -> str:
    """
    Executes Python code in a SECURE Docker sandbox.
    FEATURES: Auto-prints the last expression, Secure Sandbox, Auto-installs dependencies.
    """
    # CRITICAL: Print to stderr to avoid breaking JSON-RPC
    print(f"\n--- [DEBUG] Incoming Code ---\n{code}\n-----------------------------", file=sys.stderr)

    active_project = _get_active_project()
    client = docker.from_env()

    # 1. AST AUTO-PRINT MAGIC
    code = code.strip()
    try:
        tree = ast.parse(code)
        last_node = tree.body[-1] if tree.body else None
        
        # Check if it's an expression
        if last_node and isinstance(last_node, ast.Expr):
            # CHECK: Is it already a print() call?
            is_print = (
                isinstance(last_node.value, ast.Call) and
                isinstance(last_node.value.func, ast.Name) and
                last_node.value.func.id == 'print'
            )
            
            # Only wrap if it's NOT already a print call
            if not is_print:
                print("[DEBUG] Wrapping last expression in print().", file=sys.stderr)
                print_node = ast.Call(
                    func=ast.Name(id='print', ctx=ast.Load()),
                    args=[last_node.value],
                    keywords=[]
                )
                tree.body[-1] = ast.Expr(value=print_node)
                code = ast.unparse(tree)
            else:
                print("[DEBUG] Last line is already print(). No change.", file=sys.stderr)
    except Exception as e:
        print(f"[DEBUG] AST Transformation Failed: {e}", file=sys.stderr)
        
    # 2. Dependency Sanitizer
    clean_deps = set()
    for dep in dependencies:
        root = dep.split('.')[0]
        if root.lower() not in ['os', 'sys', 're', 'math', 'json', 'random', 'time']:
            clean_deps.add(root)
            
    header = "# /// script\n# dependencies = [\n"
    for dep in clean_deps:
        header += f'#   "{dep}",\n'
    header += "# ]\n# ///\n\n"

    # 3. Setup Code & F-String Fixer
    setup_code = ""
    if active_project:
        setup_code = "import sys\nsys.path.append('/mnt/project')\n\n"
        
    fstring_pattern = re.compile(r"f(['\"])(.*?\n.*?)\1", re.DOTALL)
    code = fstring_pattern.sub(r"f'''\2'''", code)
    
    full_script = header + setup_code + code

    # 4. Create Temp File
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tmp:
        tmp.write(full_script)
        tmp_path_host = tmp.name

    container = None
    try:
        # 5. Volume Mounts - DUAL MOUNT FIX for path confusion
        volumes = {
            tmp_path_host: {'bind': '/app/script.py', 'mode': 'ro'},
            str(WORKSPACE_DIR): {'bind': '/app/workspace', 'mode': 'rw'},
            str(WORKSPACE_DIR): {'bind': '/workspace', 'mode': 'rw'} # Fallback for bad LLM paths
        }
        if active_project:
            volumes[str(active_project)] = {'bind': '/mnt/project', 'mode': 'ro'}

        container = client.containers.run(
            image="jarvis-sandbox",
            command=["uv", "run", "/app/script.py"],
            volumes=volumes,
            network_mode="host",
            mem_limit="512m",
            nano_cpus=1000000000,
            detach=True,
            remove=False
        )

        try:
            result = container.wait(timeout=60)
            exit_code = result.get('StatusCode', 1)
        except Exception:
            container.kill()
            return "Error: Execution timed out (60s limit)."

        stdout = container.logs(stdout=True, stderr=False).decode('utf-8', errors='replace').strip()
        stderr = container.logs(stdout=False, stderr=True).decode('utf-8', errors='replace').strip()

        if exit_code != 0:
            return (
                f"⚠️ CRITICAL EXECUTION FAILURE (Exit Code {exit_code}) ⚠️\n"
                f"{stderr}\n{stdout}\n"
            )

        if stdout:
            return f"Output:\n{stdout}"
        
        if not stdout:
             msg = "Executed successfully, but STDOUT is empty."
             if stderr:
                 msg += f"\n(System Logs: {stderr})"
             msg += "\n\nCRITICAL: The code returned no result. Did you forget to `print()` the final variable?"
             return msg

    except Exception as e:
        return f"System Error: {str(e)}"
    finally:
        if container:
            try:
                container.remove(force=True)
            except: pass
        Path(tmp_path_host).unlink(missing_ok=True)

# =============================================================================
# SYSTEM OPERATIONS
# =============================================================================

@mcp.tool()
def get_system_health() -> str:
    """Returns detailed CPU, RAM, and Disk stats in GB."""
    def _bytes_to_gb(bytes_val: int) -> float:
        return round(bytes_val / (1024 ** 3), 2)
    
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    
    return (
        f"CPU Load: {psutil.cpu_percent()}%\n"
        f"RAM: {mem.percent}% Used | Total: {_bytes_to_gb(mem.total)}GB | Available: {_bytes_to_gb(mem.available)}GB\n"
        f"Disk: {disk.percent}% Used | Free: {_bytes_to_gb(disk.free)}GB"
    )

@mcp.tool()
def run_shell_command(command: str) -> str:
    """Executes safe shell commands inside the WORKSPACE directory."""
    ALLOWED = ["whoami", "date", "ls", "ip a", "uptime", "free", "df", "docker ps", "mkdir", "rm", "cat", "echo"]
    
    # 1. Security Check
    if not any(command.startswith(prefix) for prefix in ALLOWED):
        return f"Denied: Command '{command}' not in allowlist."
    
    # 2. Execution in Workspace Dir
    try:
        # We explicitly set cwd=WORKSPACE_DIR so 'ls' sees the right files
        result = subprocess.run(
            command, 
            shell=True,
            cwd=WORKSPACE_DIR,
            capture_output=True, 
            text=True, 
            timeout=5
        )
        if result.returncode != 0:
            return f"Command Failed (Code {result.returncode}):\n{result.stderr.strip()}"
        
        output = result.stdout.strip()
        if not output:
            return "Command executed successfully (no output)."
        return output
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 5s."
    except Exception as e:
        return f"Execution Error: {str(e)}"

if __name__ == "__main__":
    mcp.run()