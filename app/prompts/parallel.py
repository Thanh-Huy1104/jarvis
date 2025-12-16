"""Prompt templates for parallel task planning and execution"""


def get_parallel_planning_prompt(user_input: str) -> str:
    """Generate prompt for parallel task planning"""
    return f"""Analyze this task and determine if it can be broken into independent parallel subtasks:

Task: {user_input}

If the task involves multiple INDEPENDENT operations that can run simultaneously (e.g., "fetch Bitcoin AND Ethereum prices", "generate 3 different charts"), break it into subtasks.

If the task is sequential or single-operation, return a single task.

Respond ONLY with valid JSON, no explanations:
{{
  "parallel": true/false,
  "subtasks": [
    {{"id": "task_1", "description": "...", "code_hint": "..."}},
    {{"id": "task_2", "description": "...", "code_hint": "..."}}
  ]
}}"""


def get_parallel_worker_prompt(task_description: str, code_hint: str, task_id: str) -> str:
    """Generate prompt for parallel worker task execution"""
    return f"""Write ONLY the Python code for this task:

Task: {task_description}
Hint: {code_hint}

Available packages (pre-installed):
- psutil, numpy, pandas, matplotlib, requests, httpx
- ddgs (use: from ddgs import DDGS), wikipedia, beautifulsoup4
- boto3, google-api-python-client, psycopg2, pymongo

CRITICAL: Use print() to display results - without print(), output is invisible!
Example: result = function(); print(result)

For matplotlib plots:
- DO NOT use plt.show() (sandbox is headless)
- SAVE to /workspace/plot_{task_id}.png using plt.savefig()
- Print confirmation: "Plot saved to /workspace/plot_{task_id}.png"

Import what you need and write the code. Respond with ONLY a Python code block, nothing else. No explanations."""
