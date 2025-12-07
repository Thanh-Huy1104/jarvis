#!/usr/bin/env python3
# /// script
# dependencies = [
#   "fastmcp",
#   "httpx",
#   "psutil", 
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

import httpx
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
    if shutil := subprocess.which("tree"):
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
    Executes Python code in a SECURE Docker sandbox.
    When printing multi-line output, always use triple quotes for f-strings to prevent SyntaxError.

    Capabilities:
    1. If an active project is set, it is mounted at `/mnt/project` (Read-Only).
    2. You can import modules from the project by adding `/mnt/project` to sys.path.
    3. Use this to run diagnostics, static analysis, or unit tests on the user's code.
    """
    active_project = _get_active_project()
    
    # 1. Prepare script content
    header = "# /// script\n# dependencies = [\n"
    for dep in dependencies:
        header += f'#   "{dep}",\n'
    header += "# ]\n# ///\n\n"
    
    # Inject helper setup if project is active
    setup_code = ""
    if active_project:
        setup_code = (
            "import sys\n"
            "sys.path.append('/mnt/project')\n"
            "print(f'Info: Project mounted at /mnt/project')\n\n"
        )

    full_script = header + setup_code + code

    # 2. Create temp script on HOST
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tmp:
        tmp.write(full_script)
        tmp_path_host = tmp.name

    try:
        # 3. Construct Docker Command
        cmd = [
            "docker", "run", 
            "--rm",
            "--network", "host",
            "--cpus", "1.0",
            "--memory", "512m",
            "-v", f"{tmp_path_host}:/app/script.py:ro",
            "-v", f"{WORKSPACE_DIR}:/app/workspace",
            "jarvis-sandbox",
            "uv", "run", "/app/script.py"
        ]
        
        # 4. Mount Active Project (Read-Only) if it exists
        if active_project:
            cmd.insert(-3, "-v")
            cmd.insert(-3, f"{active_project}:/mnt/project:ro")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        output = result.stdout
        error = result.stderr
        
        if result.returncode != 0:
            return f"Execution Failed:\n{error}\n{output}"
            
        return f"Output:\n{output}"

    except subprocess.TimeoutExpired:
        return "Error: Timed out (60s limit)."
    except Exception as e:
        return f"System Error: {e}"
    finally:
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

@mcp.tool()
def get_system_health() -> str:
    """Returns CPU/RAM/Disk stats."""
    return f"CPU: {psutil.cpu_percent()}% | RAM: {psutil.virtual_memory().percent}%"

@mcp.tool()
def run_shell_command(command: str) -> str:
    """Executes safe shell commands."""
    if not any(command.startswith(prefix) for prefix in ALLOWED_SHELL_COMMANDS):
        return f"Denied: Command '{command}' not in allowlist."
    return _run_subprocess(command)

if __name__ == "__main__":
    mcp.run()