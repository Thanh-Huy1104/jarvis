#!/usr/bin/env python3
# /// script
# dependencies = [
#   "fastmcp",
#   "httpx",
#   "psutil", 
#   "docker"
# ]
# ///

"""
Jarvis Headless MCP Server
--------------------------
Provides system monitoring, sandboxed code execution, and productivity tools
for a headless Linux/Proxmox environment.
"""

import datetime
import json
import socket
import subprocess
import tempfile
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
import shutil
import re # Import re

import httpx
import psutil
from fastmcp import FastMCP
import docker
from docker.errors import ContainerError, ImageNotFound, APIError
# =============================================================================
# CONFIGURATION & CONSTANTS
# =============================================================================

SERVER_NAME = "Jarvis Headless"
DATA_DIR = Path.home() / "jarvis_data"
WORKSPACE_DIR = DATA_DIR / "workspace"
NOTES_FILE = DATA_DIR / "notes.md"
TODO_FILE = DATA_DIR / "todos.json"
STATE_FILE = DATA_DIR / "state.json"  # Tracks active context (e.g. current project)

# Shell commands allowed for direct execution on the host
ALLOWED_SHELL_COMMANDS = [
    "whoami", "date", "ls", "ip a", "uptime", "free", "df", "docker ps"
]

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
WORKSPACE_DIR.mkdir(exist_ok=True)

mcp = FastMCP(SERVER_NAME)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _load_json(filepath: Path, default: Any = None) -> Any:
    """Safely loads JSON from a file, returning default if not found/invalid."""
    if not filepath.exists():
        return default if default is not None else []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return default if default is not None else []

def _save_json(filepath: Path, data: Any) -> None:
    """Safely saves data to a JSON file."""
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def _get_active_project() -> Optional[Path]:
    """Retrieves the currently active project path from state."""
    data = _load_json(STATE_FILE, default={})
    path_str = data.get("active_project")
    if path_str:
        path = Path(path_str)
        if path.exists() and path.is_dir():
            return path
    return None

def _run_subprocess(cmd: List[str], timeout: int = 5) -> str:
    """Executes a subprocess and returns formatted output."""
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
    """
    Sets the active coding project directory. 
    Future tools (execute_python, read_file) will target this directory.
    Example: set_active_project("/home/th/projects/my-app")
    """
    p = Path(path).expanduser().resolve()
    if not p.exists() or not p.is_dir():
        return f"Error: Path not found or not a directory: {path}"
    
    # Save to state file so it persists across server restarts
    state = _load_json(STATE_FILE, default={})
    state["active_project"] = str(p)
    _save_json(STATE_FILE, state)
    
    return f"Active project set to: {p}\nJarvis can now read files and run diagnostics in this folder."

@mcp.tool()
def get_project_structure(max_depth: int = 2) -> str:
    """
    Returns a tree view of files in the ACTIVE project. 
    Use this to understand the codebase structure before reading specific files.
    """
    project_path = _get_active_project()
    if not project_path:
        return "Warning: No active project set. Use `set_active_project` first."

    # Use 'tree' command if available, otherwise fallback to simple list
    if shutil.which("tree"):
        return _run_subprocess(["tree", "-L", str(max_depth), "--noreport", str(project_path)])
    
    # Fallback python implementation
    output = []
    output.append(f"{project_path.name}/")
    for root, dirs, files in os.walk(project_path):
        level = root.replace(str(project_path), '').count(os.sep)
        if level >= max_depth: continue
        indent = ' ' * 4 * (level)
        subindent = ' ' * 4 * (level + 1)
        for f in files:
            if not f.startswith('.'): # Skip hidden
                output.append(f"{subindent}{f}")
    return "\n".join(output)

@mcp.tool()
def read_project_file(relative_path: str) -> str:
    """
    Reads the content of a specific file in the active project.
    Args:
        relative_path: Path relative to project root (e.g., "src/main.py")
    """
    project_path = _get_active_project()
    if not project_path:
        return "Warning: No active project set."
        
    target_file = (project_path / relative_path).resolve()
    
    # Security check: Ensure file is actually INSIDE the project folder (prevent ../../etc/passwd)
    if not str(target_file).startswith(str(project_path)):
        return "Security Error: Cannot read files outside the active project."
        
    if not target_file.exists():
        return f"Error: File not found: {relative_path}"
        
    try:
        with open(target_file, "r", encoding="utf-8") as f:
            content = f.read()
            return f"Content of {relative_path}:\n```\n{content}\n```"
    except Exception as e:
        return f"Error reading file: {e}"

@mcp.tool()
def execute_python(code: str, dependencies: List[str] = []) -> str:
    """
    Executes Python code in a SECURE Docker sandbox using the Docker SDK.
    
    **CRITICAL: You MUST use `print()` to see results. STDOUT is captured separately.**
    """
    active_project = _get_active_project()
    client = docker.from_env()

    # 1. DEPENDENCY SANITIZER (Prevents "numpy.linalg" errors)
    clean_deps = set()
    for dep in dependencies:
        # Keep only the root package name (e.g. 'numpy.linalg' -> 'numpy')
        root = dep.split('.')[0]
        # Skip standard libs or suspicious inputs
        if root.lower() not in ['os', 'sys', 're', 'math', 'json', 'random', 'time']:
            clean_deps.add(root)
            
    header = "# /// script\n# dependencies = [\n"
    for dep in clean_deps:
        header += f'#   "{dep}",\n'
    header += "# ]\n# ///\n\n"

    # 2. Setup Code & F-String Fixer
    setup_code = ""
    if active_project:
        setup_code = "import sys\nsys.path.append('/mnt/project')\n\n"
        
    fstring_pattern = re.compile(r"f(['\"])(.*?\n.*?)\1", re.DOTALL)
    code = fstring_pattern.sub(r"f'''\2'''", code)
    
    full_script = header + setup_code + code

    # 3. Create Temp File
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tmp:
        tmp.write(full_script)
        tmp_path_host = tmp.name

    container = None
    try:
        # 4. Define Volumes (SDK Format)
        # Format: {HostPath: {'bind': ContainerPath, 'mode': 'ro/rw'}}
        volumes = {
            tmp_path_host: {'bind': '/app/script.py', 'mode': 'ro'},
            str(WORKSPACE_DIR): {'bind': '/app/workspace', 'mode': 'rw'}
        }
        if active_project:
            volumes[str(active_project)] = {'bind': '/mnt/project', 'mode': 'ro'}

        # 5. Run Container (Detached for timeout control)
        container = client.containers.run(
            image="jarvis-sandbox",
            command=["uv", "run", "/app/script.py"],
            volumes=volumes,
            network_mode="host",
            mem_limit="512m",
            nano_cpus=1000000000, # 1.0 CPU
            detach=True,         # Run in background so we can wait()
            remove=False         # Do not auto-remove yet (we need logs)
        )

        # 6. Wait with Timeout
        try:
            result = container.wait(timeout=60)
            exit_code = result.get('StatusCode', 1)
        except Exception: # Timed out
            container.kill()
            return "Error: Execution timed out (60s limit)."

        # 7. Capture Output (STDOUT vs STDERR separation!)
        # This is the magic fix for your "Silent Execution" issues.
        stdout = container.logs(stdout=True, stderr=False).decode('utf-8', errors='replace').strip()
        stderr = container.logs(stdout=False, stderr=True).decode('utf-8', errors='replace').strip()

        if exit_code != 0:
            error_msg = (
                f"⚠️ CRITICAL EXECUTION FAILURE (Exit Code {exit_code}) ⚠️\n"
                f"--------------------------------------------------\n"
                f"{stderr}\n"
                f"{stdout}\n"
                f"--------------------------------------------------\n"
                f"FIX: Analyze the Traceback above. Do not claim success."
            )
            return error_msg

        # If we have stdout, return it (ignore stderr noise like 'Project mounted')
        if stdout:
            return f"Output:\n{stdout}"
            
        # If stdout is empty but we have stderr, warn the user
        if stderr:
             return f"Executed successfully, but STDOUT is empty.\n(System Logs: {stderr})\nDid you forget to print()?"
        
        return "Executed successfully. Output was empty."

    except ImageNotFound:
        return "System Error: Docker image 'jarvis-sandbox' not found."
    except APIError as e:
        return f"Docker API Error: {str(e)}"
    except Exception as e:
        return f"Unexpected Error: {str(e)}"
    finally:
        # Cleanup
        if container:
            try:
                container.remove(force=True)
            except:
                pass
        Path(tmp_path_host).unlink(missing_ok=True)
        
@mcp.tool()
def list_workspace_files() -> str:
    """Lists files available in the engineering workspace (persistent storage)."""
    try:
        files = [f.name for f in WORKSPACE_DIR.iterdir() if f.is_file()]
        if not files:
            return "Workspace is empty."
        return "Workspace Files:\n" + "\n".join([f"- {name}" for name in files])
    except Exception as e:
        return f"Error: {e}"


# =============================================================================
# 🧠 MEMORY & PRODUCTIVITY
# =============================================================================

@mcp.tool()
def add_note(content: str, category: str = "general") -> str:
    """Saves a note to the journal."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"\n### [{timestamp}] ({category.upper()})\n{content}\n"
    try:
        with open(NOTES_FILE, "a", encoding="utf-8") as f:
            f.write(entry)
        return f"Note saved."
    except Exception as e:
        return f"Error: {e}"

@mcp.tool()
def read_recent_notes(lines: int = 20) -> str:
    """Reads recent notes."""
    if not NOTES_FILE.exists(): return "No notes found."
    try:
        with open(NOTES_FILE, "r", encoding="utf-8") as f:
            return "".join(f.readlines()[-lines:])
    except Exception as e:
        return f"Error: {e}"

@mcp.tool()
def manage_todos(action: str, task_content: str = "", task_id: int = -1) -> str:
    """Manages Todo list (add, list, complete)."""
    todos = _load_json(TODO_FILE, default=[])
    if action == "add":
        if not task_content: return "Error: Task content required."
        new_id = 1 if not todos else max(t["id"] for t in todos) + 1
        todos.append({"id": new_id, "task": task_content, "created": str(datetime.date.today())})
        _save_json(TODO_FILE, todos)
        return f"Added task #{new_id}"
    elif action == "list":
        if not todos: return "Todo list is empty."
        return "\n".join([f"[#{t['id']}] {t['task']}" for t in todos])
    elif action == "complete":
        todos = [t for t in todos if t["id"] != task_id]
        _save_json(TODO_FILE, todos)
        return f"Completed task #{task_id}."
    return "Error: Unknown action."


# =============================================================================
# SYSTEM OPERATIONS
# =============================================================================

def _bytes_to_gb(bytes_val: int) -> float:
    return round(bytes_val / (1024 ** 3), 2)

@mcp.tool()
def get_system_health() -> str:
    """Returns detailed CPU, RAM, and Disk stats in GB."""
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    
    return (
        f"CPU Load: {psutil.cpu_percent()}%\n"
        f"RAM: {mem.percent}% Used | Total: {_bytes_to_gb(mem.total)}GB | Available: {_bytes_to_gb(mem.available)}GB\n"
        f"Disk: {disk.percent}% Used | Free: {_bytes_to_gb(disk.free)}GB"
    )
    
@mcp.tool()
def run_shell_command(command: str) -> str:
    """Executes safe shell commands."""
    if not any(command.startswith(prefix) for prefix in ALLOWED_SHELL_COMMANDS):
        return f"Denied: Command '{command}' not in allowlist."
    return _run_subprocess(command)

if __name__ == "__main__":
    mcp.run()