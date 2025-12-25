"""
Prompts for generating rich skill documentation (SKILL.md).
"""

def get_skill_documentation_prompt(code: str, description: str, name: str = "") -> str:
    """
    Constructs the prompt for generating comprehensive skill documentation.
    """
    return f"""You are an expert technical writer and developer.
Your task is to create a high-quality, comprehensive documentation file for a Python skill.
The output must be a valid Markdown file with YAML frontmatter, following the "Claude Skill" format.

INPUT CONTEXT:
- Skill Name (suggested): {name if name else "Infer from code"}
- User Description: {description}
- Verified Python Code:
```python
{code}
```

OUTPUT REQUIREMENTS:
1. **YAML Frontmatter**:
   - name: kebab-case-name
   - description: 1-sentence summary
   - version: 1.0.0
   - tools: [python]
   - dependencies: [list, of, pypi, packages] (Infer from imports)

2. **Skill Title**: # Title Case Name

3. **Sections**:
   - **Description**: Detailed explanation of what it does and why it's useful.
   - **When to Use**: Specific scenarios or triggers.
   - **How to Use**: Instructions on how to call the function or use the skill.
   - **Dependencies**: List of required packages and how to install them (pip).
   - **Code**: The provided Python code in a python block.
   - **Troubleshooting**: Common errors (e.g., API keys missing, network issues) and how to fix them.

4. **Style**:
   - Clear, concise, professional.
   - Use Markdown headers (##).
   - Ensure the code block is exactly as provided (do not modify the logic).

Generate ONLY the Markdown content (starting with ---).
"""
