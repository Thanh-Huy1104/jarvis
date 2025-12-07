#!/usr/bin/env python3
# /// script
# dependencies = [
#   "fastmcp",
#   "httpx",
#   "psutil", 
# ]
# ///

from fastmcp import FastMCP
import httpx
import psutil
import datetime
import subprocess
import json
import socket
from pathlib import Path

# --- Configuration ---
# We store data in your home directory so it persists across restarts
DATA_DIR = Path.home() / "jarvis_data"
DATA_DIR.mkdir(exist_ok=True)

NOTES_FILE = DATA_DIR / "notes.md"
TODO_FILE = DATA_DIR / "todos.json"

# Initialize the server
mcp = FastMCP("Jarvis Headless")

# ==========================================
# 🧠 MEMORY & ORGANIZATION TOOLS
# ==========================================

@mcp.tool()
def add_note(content: str, category: str = "general") -> str:
    """
    Saves a text note to a markdown journal.
    Useful for logging errors, ideas, or reminders.
    """
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"\n### [{timestamp}] ({category.upper()})\n{content}\n"
    
    try:
        with open(NOTES_FILE, "a", encoding="utf-8") as f:
            f.write(entry)
        return f"✅ Note saved to {NOTES_FILE}"
    except Exception as e:
        return f"❌ Failed to save note: {e}"

@mcp.tool()
def read_recent_notes(lines: int = 20) -> str:
    """
    Reads the last N lines of your notes file.
    Use this to recall what the user was last working on.
    """
    if not NOTES_FILE.exists():
        return "No notes found yet."
    
    try:
        # Simple tail implementation
        with open(NOTES_FILE, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
            return "".join(all_lines[-lines:])
    except Exception as e:
        return f"Error reading notes: {e}"

@mcp.tool()
def manage_todos(action: str, task_content: str = "", task_id: int = -1) -> str:
    """
    Manages a simple Todo list.
    Args:
        action: 'add', 'list', or 'complete'
        task_content: Description of the task (for 'add')
        task_id: ID of the task to complete (for 'complete')
    """
    # Load existing
    if TODO_FILE.exists():
        with open(TODO_FILE, "r") as f:
            try:
                todos = json.load(f)
            except json.JSONDecodeError:
                todos = []
    else:
        todos = []

    if action == "add":
        if not task_content:
            return "❌ Error: task_content required for 'add'"
        new_id = 1 if not todos else max(t["id"] for t in todos) + 1
        todos.append({"id": new_id, "task": task_content, "created": str(datetime.date.today())})
        msg = f"✅ Added task #{new_id}: {task_content}"

    elif action == "list":
        if not todos:
            return "📝 Todo list is empty."
        return "\n".join([f"[#{t['id']}] {t['task']} ({t['created']})" for t in todos])

    elif action == "complete":
        # Filter out the task with the given ID
        initial_len = len(todos)
        todos = [t for t in todos if t["id"] != task_id]
        if len(todos) == initial_len:
            return f"❌ Task #{task_id} not found."
        msg = f"✅ Completed task #{task_id}."

    else:
        return f"❌ Unknown action: {action}. Use 'add', 'list', or 'complete'."

    # Save back
    with open(TODO_FILE, "w") as f:
        json.dump(todos, f, indent=2)
    
    return msg

# ==========================================
# 🛠️ ENGINEERING / DEBUGGING TOOLS
# ==========================================

@mcp.tool()
def check_local_port(port: int) -> str:
    """
    Checks if a specific TCP port is open and listening on localhost.
    Useful for debugging if a Docker container or service is actually running.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)
    result = sock.connect_ex(('127.0.0.1', port))
    sock.close()
    
    if result == 0:
        return f"🟢 Port {port} is OPEN (Service is running)"
    else:
        return f"🔴 Port {port} is CLOSED (Nothing listening)"

# ==========================================
# 🖥️ EXISTING SYSTEM TOOLS
# ==========================================

@mcp.tool()
def get_system_health() -> str:
    """Returns a snapshot of the server's health."""
    cpu_percent = psutil.cpu_percent(interval=1)
    
    mem = psutil.virtual_memory()
    mem_used_gb = round(mem.used / (1024**3), 2)
    mem_total_gb = round(mem.total / (1024**3), 2)
    
    disk = psutil.disk_usage('/')
    disk_free_gb = round(disk.free / (1024**3), 2)
    
    boot_time = datetime.datetime.fromtimestamp(psutil.boot_time())
    uptime = datetime.datetime.now() - boot_time
    
    return (
        f"--- System Health ---\n"
        f"CPU Usage: {cpu_percent}%\n"
        f"Memory: {mem_used_gb}GB / {mem_total_gb}GB ({mem.percent}%)\n"
        f"Disk Free: {disk_free_gb} GB\n"
        f"Uptime: {str(uptime).split('.')[0]}"
    )

@mcp.tool()
def get_top_processes(count: int = 5) -> str:
    """Lists the top processes consuming CPU."""
    procs = []
    for proc in psutil.process_iter(['pid', 'name', 'cpu_percent']):
        try:
            procs.append(proc.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
            
    sorted_procs = sorted(procs, key=lambda p: p['cpu_percent'], reverse=True)[:count]
    
    result = "--- Top CPU Processes ---\n"
    for p in sorted_procs:
        result += f"PID: {p['pid']} | Name: {p['name']} | CPU: {p['cpu_percent']}%\n"
        
    return result

@mcp.tool()
async def get_weather(city: str) -> str:
    """
    Fetches current weather for a city.
    Use this for ANY weather question, including follow-ups like 'what about [city]?'.
    """
    try:
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1&language=en&format=json"
        async with httpx.AsyncClient() as client:
            geo_resp = await client.get(geo_url)
            geo_data = geo_resp.json()
            
            if not geo_data.get("results"):
                return f"Could not find city: {city}"
                
            lat = geo_data["results"][0]["latitude"]
            lon = geo_data["results"][0]["longitude"]
            
            weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,wind_speed_10m"
            weather_resp = await client.get(weather_url)
            w_data = weather_resp.json()["current"]
            
            temp = w_data["temperature_2m"]
            wind = w_data["wind_speed_10m"]
            return f"Weather in {city}: {temp}°C, Wind: {wind} km/h"
            
    except Exception as e:
        return f"Error fetching weather: {e}"

@mcp.tool()
def run_shell_command(command: str) -> str:
    """Executes a safe shell command."""
    allowed_prefixes = ["whoami", "date", "ls", "ip a", "uptime", "free", "df", "docker ps"]
    
    if not any(command.startswith(prefix) for prefix in allowed_prefixes):
        return f"Command '{command}' is not in the allowed list."
    
    try:
        result = subprocess.run(
            command, 
            shell=True, 
            capture_output=True, 
            text=True, 
            timeout=5
        )
        return f"Output:\n{result.stdout}\nErrors:\n{result.stderr}"
    except Exception as e:
        return f"Failed to execute: {e}"

if __name__ == "__main__":
    mcp.run()