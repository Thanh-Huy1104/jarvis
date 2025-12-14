#!/usr/bin/env python3
# /// script
# dependencies = [
#   "fastmcp",
#   "docker",
#   "psutil", 
#   "httpx",
#   "duckduckgo-search",
#   "beautifulsoup4",
#   "trafilatura",
# ]
# ///

"""
Jarvis Headless MCP Server (Ultimate Edition)
---------------------------------------------
A complete toolset for a headless AI Assistant.
Capabilities:
1. System & Docker Management (Ops)
2. Sandboxed Python Execution (Engineering)
3. File System Manipulation (Coding)
4. Web Research (Browsing)
5. Memory & Task Management (Productivity)
"""

import ast
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, List, Optional

import docker
import psutil
import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
from fastmcp import FastMCP

# =============================================================================
# 🔧 CONFIGURATION & CONSTANTS
# =============================================================================

SERVER_NAME = "Jarvis Headless"
DATA_DIR = Path.home() / "jarvis_data"
WORKSPACE_DIR = DATA_DIR / "workspace"
NOTES_FILE = DATA_DIR / "notes.md"
TODO_FILE = DATA_DIR / "todos.json"
STATE_FILE = DATA_DIR / "state.json"

# Ensure core directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

# Initialize MCP Server
mcp = FastMCP(SERVER_NAME)

# =============================================================================
# 🛠️ HELPER FUNCTIONS
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

def _is_safe_path(path: Path) -> bool:
    """Ensures file operations stay within the WORKSPACE_DIR."""
    try:
        # Resolve to absolute path and check prefix
        full_path = path.resolve()
        return str(full_path).startswith(str(WORKSPACE_DIR.resolve()))
    except Exception:
        return False

# =============================================================================
# 🌍 WEB & RESEARCH TOOLS ("THE EYES")
# =============================================================================

@mcp.tool()
def search_web(query: str, max_results: int = 5, region: str = "wt-wt") -> str:
    """
    Searches the internet for current information using DuckDuckGo.
    
    Args:
        query: Search query string
        max_results: Number of results to return (default: 5, max: 20)
        region: Region code (wt-wt=global, us-en=USA, uk-en=UK, etc.)
    
    Returns formatted results with title, URL, and snippet.
    """
    try:
        max_results = min(max_results, 20)  # Cap at 20
        
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results, region=region))
        
        if not results:
            return f"No results found for: {query}"
        
        # Format results for better readability
        formatted = []
        for i, result in enumerate(results, 1):
            formatted.append(
                f"[{i}] {result.get('title', 'No title')}\n"
                f"    URL: {result.get('href', 'N/A')}\n"
                f"    {result.get('body', 'No description')}\n"
            )
        
        return "\n".join(formatted)
    except Exception as e:
        return f"Error performing web search: {e}"

@mcp.tool()
def search_news(query: str, max_results: int = 5) -> str:
    """
    Searches for recent news articles using DuckDuckGo News.
    Returns timestamped news results.
    """
    try:
        with DDGS() as ddgs:
            results = list(ddgs.news(query, max_results=max_results))
        
        if not results:
            return f"No news found for: {query}"
        
        formatted = []
        for i, result in enumerate(results, 1):
            date = result.get('date', 'Unknown date')
            formatted.append(
                f"[{i}] {result.get('title', 'No title')} ({date})\n"
                f"    Source: {result.get('source', 'Unknown')}\n"
                f"    URL: {result.get('url', 'N/A')}\n"
                f"    {result.get('body', 'No description')}\n"
            )
        
        return "\n".join(formatted)
    except Exception as e:
        return f"Error searching news: {e}"

@mcp.tool()
def scrape_website(url: str, extract_links: bool = False) -> str:
    """
    Scrapes the text content of a specific webpage for reading documentation.
    
    Args:
        url: The webpage URL to scrape
        extract_links: If True, also extracts and returns all links found
    
    Returns clean text content with optional links.
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }
        res = requests.get(url, headers=headers, timeout=15)
        res.raise_for_status()
        
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # Extract links if requested
        links = []
        if extract_links:
            for link in soup.find_all('a', href=True):
                href = link['href']
                # Convert relative URLs to absolute
                if href.startswith('/'):
                    from urllib.parse import urljoin
                    href = urljoin(url, href)
                if href.startswith('http'):
                    links.append(f"{link.get_text(strip=True)} -> {href}")
        
        # Remove unwanted elements
        for element in soup(["script", "style", "nav", "footer", "header", "aside", "iframe"]):
            element.decompose()
        
        # Extract main content - prioritize article/main tags
        main_content = soup.find('main') or soup.find('article') or soup.find('body')
        if main_content:
            text = main_content.get_text()
        else:
            text = soup.get_text()
        
        # Clean up whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = '\n'.join(chunk for chunk in chunks if chunk)
        
        # Build output
        output = text[:15000] + "\n...(truncated)" if len(text) > 15000 else text
        
        if extract_links and links:
            output += f"\n\n--- FOUND {len(links)} LINKS ---\n"
            output += "\n".join(links[:50])  # Limit to 50 links
        
        return output
    except requests.exceptions.Timeout:
        return f"Error: Request timed out for {url}"
    except requests.exceptions.RequestException as e:
        return f"Error fetching website: {e}"
    except Exception as e:
        return f"Error scraping website: {e}"

# =============================================================================
# 📂 FILE SYSTEM TOOLS ("THE HANDS")
# =============================================================================

@mcp.tool()
def list_directory(path: str = ".") -> str:
    """Lists files and directories in the workspace."""
    target = (WORKSPACE_DIR / path).resolve()
    if not _is_safe_path(target):
        return "Error: Access Denied. You can only access the workspace."
    
    if not target.exists():
        return "Error: Path does not exist."

    try:
        output = []
        # Simple ls -la style output
        for item in target.iterdir():
            type_char = "d" if item.is_dir() else "-"
            output.append(f"{type_char} {item.name}")
        return "\n".join(sorted(output))
    except Exception as e:
        return f"Error listing directory: {e}"

@mcp.tool()
def read_file(filepath: str) -> str:
    """Reads the content of a file from the workspace."""
    target = (WORKSPACE_DIR / filepath).resolve()
    if not _is_safe_path(target):
        return "Error: Access Denied."
    if not target.exists():
        return "Error: File not found."
    if not target.is_file():
        return "Error: Path is not a file."
        
    try:
        return target.read_text(encoding='utf-8')
    except Exception as e:
        return f"Error reading file: {e}"

@mcp.tool()
def write_file(filepath: str, content: str) -> str:
    """Writes (or overwrites) a file in the workspace."""
    target = (WORKSPACE_DIR / filepath).resolve()
    if not _is_safe_path(target):
        return "Error: Access Denied."
    
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8')
        return f"Successfully wrote {len(content)} bytes to {filepath}"
    except Exception as e:
        return f"Error writing file: {e}"

# =============================================================================
# 🧠 MEMORY & PRODUCTIVITY ("THE BRAIN")
# =============================================================================

@mcp.tool()
def add_note(note: str) -> str:
    """Adds a timestamped note to the personal journal."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        with open(NOTES_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n## {now}\n{note}\n")
        return "Note added successfully."
    except Exception as e:
        return f"Error adding note: {e}"

@mcp.tool()
def search_notes(keyword: str) -> str:
    """Searches personal notes for a specific keyword."""
    if not NOTES_FILE.exists():
        return "No notes file found."
    
    try:
        matches = []
        content = NOTES_FILE.read_text(encoding='utf-8')
        # Split by header entries (## YYYY-MM-DD)
        entries = content.split("##")
        
        for entry in entries:
            if not entry.strip(): continue
            if keyword.lower() in entry.lower():
                matches.append(f"##{entry.strip()}")
        
        if not matches:
            return f"No notes found containing '{keyword}'."
        return "\n\n".join(matches)
    except Exception as e:
        return f"Error searching notes: {e}"

@mcp.tool()
def manage_todo(action: str, task: str = "", task_id: int = -1) -> str:
    """
    Manages a simple TODO list.
    Actions: 'list', 'add', 'complete', 'remove'.
    """
    todos = _load_json(TODO_FILE, [])
    
    if action == "list":
        active = [t for t in todos if not t.get('completed')]
        if not active: return "No active tasks."
        return json.dumps(active, indent=2)
    
    elif action == "add":
        if not task: return "Error: Task description required for 'add'."
        new_id = max([t.get('id', 0) for t in todos], default=0) + 1
        todos.append({
            "id": new_id, 
            "task": task, 
            "completed": False, 
            "created": str(datetime.datetime.now())
        })
        _save_json(TODO_FILE, todos)
        return f"Task added: [ID {new_id}] {task}"
        
    elif action == "complete":
        for t in todos:
            if t.get('id') == task_id:
                t['completed'] = True
                _save_json(TODO_FILE, todos)
                return f"Task {task_id} marked as complete."
        return f"Error: Task ID {task_id} not found."
    
    return "Invalid action. Use: list, add, complete."

# =============================================================================
# 🧪 SANDBOXED ENGINEERING ("THE LAB")
# =============================================================================

@mcp.tool()
def set_active_project(path: str) -> str:
    """Sets the active project directory for code execution context."""
    p = Path(path).expanduser().resolve()
    if not p.exists() or not p.is_dir():
        return f"Error: Path not found: {path}"
    
    state = _load_json(STATE_FILE, default={})
    state["active_project"] = str(p)
    _save_json(STATE_FILE, state)
    return f"Active project set to: {p}"

@mcp.tool()
def execute_python(code: str, dependencies: List[str] = []) -> str:
    """
    Executes Python code in a secure Docker sandbox.
    Automatically installs dependencies and prints the last expression.
    """
    print(f"\n--- [DEBUG] Incoming Code ---\n{code}\n-----------------------------", file=sys.stderr)

    active_project = _get_active_project()
    client = docker.from_env()

    # 1. AST Transformation (Auto-print last expression)
    code = code.strip()
    try:
        tree = ast.parse(code)
        if tree.body and isinstance(tree.body[-1], ast.Expr):
            last_node = tree.body[-1]
            # check if not already a print call
            is_print = (
                isinstance(last_node.value, ast.Call) and
                isinstance(last_node.value.func, ast.Name) and
                last_node.value.func.id == 'print'
            )
            if not is_print:
                print("[DEBUG] Wrapping last expression in print()", file=sys.stderr)
                print_node = ast.Call(
                    func=ast.Name(id='print', ctx=ast.Load()),
                    args=[last_node.value],
                    keywords=[]
                )
                tree.body[-1] = ast.Expr(value=print_node)
                code = ast.unparse(tree)
    except Exception as e:
        print(f"[DEBUG] AST Transformation Failed: {e}", file=sys.stderr)
        
    # 2. Prepare Script
    clean_deps = {d.split('.')[0] for d in dependencies if d.lower() not in 
                 ['os', 'sys', 're', 'math', 'json', 'random', 'time', 'datetime']}
            
    header = "# /// script\n# dependencies = [\n"
    for dep in clean_deps:
        header += f'#   "{dep}",\n'
    header += "# ]\n# ///\n\n"

    setup_code = "import sys\nsys.path.append('/mnt/project')\n\n" if active_project else ""
    
    # Fix f-string format edge cases
    fstring_pattern = re.compile(r"f(['\"])(.*?\n.*?)\1", re.DOTALL)
    code = fstring_pattern.sub(r"f'''\2'''", code)
    
    full_script = header + setup_code + code

    # 3. Create Temp File
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tmp:
        tmp.write(full_script)
        tmp_path_host = tmp.name

    container = None
    try:
        # 4. Volume Config
        volumes = {
            tmp_path_host: {'bind': '/app/script.py', 'mode': 'ro'},
            str(WORKSPACE_DIR): {'bind': '/app/workspace', 'mode': 'rw'},
            str(WORKSPACE_DIR): {'bind': '/workspace', 'mode': 'rw'}
        }
        if active_project:
            volumes[str(active_project)] = {'bind': '/mnt/project', 'mode': 'ro'}

        # 5. Run Container
        container = client.containers.run(
            image="jarvis-sandbox",
            command=["uv", "run", "/app/script.py"],
            volumes=volumes,
            network_mode="host",
            mem_limit="512m",
            nano_cpus=1000000000, # 1 CPU
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
            return f"⚠️ EXECUTION FAILURE (Exit Code {exit_code}):\n{stderr}\n{stdout}"

        if not stdout:
            return f"Executed successfully (No Output).\nLogs: {stderr}" if stderr else "Executed successfully."

        return f"{stdout}"

    except Exception as e:
        return f"System Error: {str(e)}"
    finally:
        if container:
            try:
                container.remove(force=True)
            except: pass
        Path(tmp_path_host).unlink(missing_ok=True)

# =============================================================================
# 🖥️ SYSTEM OPS ("THE INFRASTRUCTURE")
# =============================================================================

@mcp.tool()
def get_system_health() -> str:
    """Returns CPU, RAM, and Disk usage stats."""
    def _bytes_to_gb(b): return round(b / (1024**3), 2)
    
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    
    return (
        f"CPU: {psutil.cpu_percent()}%\n"
        f"RAM: {mem.percent}% ({_bytes_to_gb(mem.used)}GB / {_bytes_to_gb(mem.total)}GB)\n"
        f"Disk: {disk.percent}% ({_bytes_to_gb(disk.used)}GB / {_bytes_to_gb(disk.total)}GB)"
    )

@mcp.tool()
def run_shell_command(command: str) -> str:
    """
    Executes safe shell commands in the workspace.
    Allowed: ls, cat, echo, grep, find, date, whoami, uptime, df, free, docker
    """
    ALLOWED_PREFIXES = [
        "ls", "cat", "echo", "grep", "find", "date", "whoami", 
        "uptime", "df", "free", "docker ps", "mkdir", "rm", "touch", "pwd"
    ]
    
    if not any(command.strip().startswith(p) for p in ALLOWED_PREFIXES):
        return f"Denied: Command '{command}' not in whitelist."

    try:
        res = subprocess.run(
            command, 
            shell=True, 
            cwd=WORKSPACE_DIR,
            capture_output=True, 
            text=True, 
            timeout=10
        )
        if res.returncode != 0:
            return f"Error ({res.returncode}): {res.stderr.strip()}"
        return res.stdout.strip() or "Success (No output)"
    except Exception as e:
        return f"Execution Error: {e}"

@mcp.tool()
def manage_docker(action: str, container_name: str) -> str:
    """
    Manages Docker containers. 
    Action: 'start', 'stop', 'restart', 'logs'.
    """
    client = docker.from_env()
    try:
        container = client.containers.get(container_name)
        if action == "start":
            container.start()
        elif action == "stop":
            container.stop()
        elif action == "restart":
            container.restart()
        elif action == "logs":
            return container.logs(tail=50).decode('utf-8')
        else:
            return "Invalid action. Use start, stop, restart, or logs."
        
        return f"Successfully performed '{action}' on {container_name}"
    except Exception as e:
        return f"Docker Error: {e}"

if __name__ == "__main__":
    mcp.run()