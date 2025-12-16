"""Prompt templates for code generation"""


def get_code_generation_prompt(
    user_input: str,
    memory_context: str,
    directives: list[str],
    skills_section: str
) -> str:
    """Generate prompt for code generation with skills"""
    directives_str = "\n".join(f"- {d}" for d in directives)
    
    return f"""
TASK: {user_input}

{memory_context}

CORE DIRECTIVES:
{directives_str}

AVAILABLE CAPABILITIES:

1. Python Sandbox (PREFERRED for most tasks):
   Pre-installed packages: psutil, numpy, pandas, matplotlib, scipy, scikit-learn,
   requests, httpx, beautifulsoup4, ddgs, wikipedia, boto3, google-api-python-client,
   psycopg2, pymongo, redis, sqlalchemy, openpyxl, pillow, pyyaml
   
   Use for:
   - Web search (DDGS().text() or DDGS().news())
   - Web scraping (BeautifulSoup)
   - Data analysis (pandas, numpy)
   - API calls (requests, httpx)
   - System monitoring inside sandbox (psutil)

2. MCP Tools (ONLY for host system operations):
   Available when Python sandbox cannot access host system:
   - list_directory(path) - List files on HOST filesystem
   - read_file(filepath) - Read files from HOST
   - write_file(filepath, content) - Write files to HOST
   - run_shell_command(command) - Execute shell on HOST (git, apt, etc.)
   - manage_docker(action, container_name) - Control Docker containers
   
   Use ONLY when you need to:
   - Access files outside the sandbox (host filesystem)
   - Run git commands or system package managers
   - Manage Docker containers
   - Execute system-level operations

DECISION GUIDE:
- Default to Python sandbox code for 90% of tasks
- Use MCP tools ONLY when you need host system access

{skills_section}

Provide a clear, well-formatted response. If you need to write code:
1. Briefly explain what you'll do (1-2 sentences)
2. Write the Python code in a ```python``` code block
3. You can combine/modify the reference skills above if they're helpful
4. Import any packages you need - they're pre-installed or will auto-install

CRITICAL CODE REQUIREMENTS:
- ALWAYS use print() to display results - without print(), the user sees no output!
- Store results in variables AND print them
- Example: result = function(); print(result)
- For functions that return data, call them and print the result

MATPLOTLIB PLOTS:
- DO NOT use plt.show() - the sandbox is headless and cannot display plots
- Instead, SAVE plots to /workspace/plot.png using plt.savefig('/workspace/plot.png')
- After saving, print the message: "Plot saved to /workspace/plot.png"
- Example:
  plt.figure()
  plt.plot(data)
  plt.savefig('/workspace/plot.png')
  print("Plot saved to /workspace/plot.png")

IMPORTANT: Only write Python code for sandbox execution. If the task requires host system access 
(reading/writing host files, git operations, docker management), explicitly state that MCP tools 
are needed and DO NOT generate Python code. Instead, describe what MCP tools should be used.

Keep your response concise and user-friendly. Do NOT output your internal reasoning process.
"""
