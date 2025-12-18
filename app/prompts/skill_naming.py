"""Prompt templates for skill naming"""


def get_skill_naming_prompt(user_input: str, code: str) -> str:
    """Generate prompt for naming a new skill"""
    return f"""Analyze this Python code and the user's original request to generate a concise, descriptive name for this skill.

User Request: {user_input}

Code:
```python
{code}
```

Requirements:
- Name should be 2-4 words
- Use kebab-case (e.g., fetch-bitcoin-price)
- Focus on the ACTION and the OBJECT
- Examples: "fetch-bitcoin-price", "monitor-cpu-usage", "search-news-yahoo"
- Provide ONLY the name, no quotes or explanation."""
