"""Prompt templates for skill naming"""


def get_skill_naming_prompt(description: str, code: str) -> str:
    """Generate prompt for LLM-based skill naming"""
    return f"""Generate a short, descriptive, kebab-case name for this code skill.

Description: {description}

Code:
```python
{code[:500]}...
```

Requirements:
- Use kebab-case (lowercase with hyphens)
- 2-4 words maximum
- Descriptive and specific
- Examples: "fetch-bitcoin-price", "plot-cpu-usage", "search-news-yahoo"

Respond with ONLY the skill name, no explanations."""
