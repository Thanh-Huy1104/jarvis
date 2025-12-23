"""Prompt templates for parallel task planning and execution"""


def get_parallel_planning_prompt(user_input: str) -> str:
    """Generate prompt for parallel task planning"""
    return f"""Analyze this task and determine if it can be broken into independent parallel subtasks:

Task: {user_input}

If the task involves multiple INDEPENDENT operations that can run simultaneously (e.g., "fetch Bitcoin AND Ethereum prices", "search for info on 3 different topics"), break it into subtasks.

If the task is sequential or single-operation, return a single task.

Respond ONLY with valid JSON, no explanations:
{{
  "parallel": true/false,
  "subtasks": [
    {{"id": "task_1", "description": "...", "code_hint": "..."}},
    {{"id": "task_2", "description": "...", "code_hint": "..."}}
  ]
}}"""


def get_parallel_worker_prompt(task_description: str, code_hint: str, task_id: str, skills_section: str = "") -> str:
    """Generate prompt for parallel worker task execution"""
    skills_text = ""
    if skills_section:
        skills_text = f"\nRELEVANT SKILLS FROM LIBRARY:\n{skills_section}\n"

    return f"""Write ONLY the Python code for this task:

Task: {task_description}
Hint: {code_hint}
{skills_text}
Available packages:
- Standard libraries + common packages (pandas, requests, etc.)
- Missing packages will be AUTO-INSTALLED based on imports

CRITICAL: Use print() to display results - without print(), output is invisible!
Example: result = function(); print(result)

Import what you need and write the code. You can use/modify the reference skills if they are helpful.
Respond with ONLY a Python code block, nothing else. No explanations."""
