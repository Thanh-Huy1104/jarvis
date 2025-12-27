"""
Local Code Executor
-------------------
Executes Python code locally via subprocess.
"""

import logging
import subprocess
import sys
import os
import tempfile
import shutil
import re
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

def _sanitize_code(code: str) -> str:
    """Removes hallucinated imports."""
    lines = code.split('\n')
    sanitized_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("import tools") or \
           stripped.startswith("from skills import") or \
           stripped.startswith("import skills"):
            continue
        sanitized_lines.append(line)
    return '\n'.join(sanitized_lines)

def _indent_code(code: str, spaces: int = 4) -> str:
    """Helper to indent code for wrapping."""
    indent = " " * spaces
    return "\n".join(indent + line for line in code.split("\n"))

def execute_code_locally(code: str, timeout: int = 30) -> str:
    """Runs Python code in a subprocess and returns output."""
    code = _sanitize_code(code)
    
    # Locate skills directory
    skills_dir = os.path.abspath(".jarvis/skills/library")
    
    wrapped_code = f"""import sys
import traceback
import os
import glob
import importlib.util

# Bootstrap: Load all skills into global namespace
skills_dir = "{skills_dir}"
if os.path.exists(skills_dir):
    sys.path.append(skills_dir)
    for file in glob.glob(os.path.join(skills_dir, "*.py")):
        name = os.path.splitext(os.path.basename(file))[0]
        if name == "__init__": continue
        try:
            spec = importlib.util.spec_from_file_location(name, file)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            for attr in dir(module):
                if not attr.startswith("_"):
                    globals()[attr] = getattr(module, attr)
        except Exception:
            pass

try:
{_indent_code(code, spaces=4)}
except Exception as e:
    print(f"RUNTIME ERROR: {{type(e).__name__}}: {{e}}", file=sys.stderr)
    traceback.print_exc()
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as tmp_file:
        script_path = tmp_file.name
        tmp_file.write(wrapped_code)
            
    try:
        process = subprocess.Popen(
            [sys.executable, script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=os.getcwd()
        )
        
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            return f"⚠️ Execution timed out after {timeout} seconds.\nPartial Output:\n{stdout}\n{stderr}"
        
        exit_code = process.returncode
        output = stdout
        if stderr:
            output += f"\n[STDERR]\n{stderr}"
        
        if exit_code != 0:
            return f"⚠️ Execution failed (exit code {exit_code}):\n{output.strip()}"
        
        return output.strip() if output.strip() else "✓ Executed successfully (no output)"
            
    except Exception as e:
        logger.error(f"Execution error: {e}")
        return f"System Error: {str(e)}"
    finally:
        if os.path.exists(script_path):
            try: os.remove(script_path)
            except: pass

def execute_with_packages(code: str, timeout: int = 30) -> str:
    """Detects and installs missing packages, then executes code."""
    import_pattern = r'^(?:from|import)\s+(\w+)'
    imports = re.findall(import_pattern, code, re.MULTILINE)
    
    package_map = {
        'cv2': 'opencv-python',
        'requests': 'requests',
        'httpx': 'httpx',
        'boto3': 'boto3',
        'google': 'google-api-python-client',
        'googleapiclient': 'google-api-python-client',
        'psycopg2': 'psycopg2-binary',
        'pymongo': 'pymongo',
        'redis': 'redis',
        'sqlalchemy': 'sqlalchemy',
        'bs4': 'beautifulsoup4',
        'BeautifulSoup': 'beautifulsoup4',
        'duckduckgo_search': 'duckduckgo-search',
        'DDGS': 'duckduckgo-search',
        'ddgs': 'duckduckgo-search',
        'trafilatura': 'trafilatura',
        'wikipedia': 'wikipedia',
        'playwright': 'playwright',
        'psutil': 'psutil',
        'yaml': 'pyyaml',
        'yfinance': 'yfinance',
        'tavily': 'tavily-python',
    }
    
    for imp in imports:
        pkg = package_map.get(imp)
        if pkg:
            # Check if installed
            try:
                subprocess.check_output([sys.executable, "-m", "pip", "show", pkg], stderr=subprocess.DEVNULL)
            except subprocess.CalledProcessError:
                logger.info(f"Installing missing package: {pkg}")
                use_uv = shutil.which("uv") is not None
                cmd = ["uv", "pip", "install", pkg] if use_uv else [sys.executable, "-m", "pip", "install", pkg]
                subprocess.run(cmd, capture_output=True)
                
    return execute_code_locally(code, timeout)

def lint_code_locally(code: str) -> dict:
    """Lints code using ruff."""
    if shutil.which("ruff") is None:
        return {"success": True, "output": "Ruff not found, skipping lint."}

    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as tmp_file:
        tmp_file.write(code)
        tmp_path = tmp_file.name

    try:
        result = subprocess.run(["ruff", "check", tmp_path], capture_output=True, text=True)
        return {
            "success": result.returncode == 0,
            "output": (result.stdout + "\n" + result.stderr).strip()
        }
    finally:
        if os.path.exists(tmp_path):
            try: os.remove(tmp_path)
            except: pass
