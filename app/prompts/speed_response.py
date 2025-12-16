"""Prompt templates for speed mode responses"""


def get_speed_response_prompt(user_input: str, memory_context: str, directives: list[str]) -> str:
    """Generate prompt for quick speed responses"""
    directives_str = "\n".join(f"- {d}" for d in directives)
    
    return f"""
TASK: {user_input}

{memory_context}

CORE DIRECTIVES:
{directives_str}

Provide a clear, concise, and helpful response. Keep it brief and to the point.
"""
