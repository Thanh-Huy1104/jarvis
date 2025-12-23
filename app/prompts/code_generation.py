"""Prompt templates for code generation"""


def get_code_generation_prompt(
    user_input: str,
    memory_context: str,
    directives: list[str],
    skills_section: str,
    current_date: str
) -> str:
    """Generate prompt for code generation with skills"""
    directives_str = "\n".join(f"- {d}" for d in directives)
    
    return f"""
TASK: {user_input}

CURRENT DATE: {current_date}

{memory_context}

CORE DIRECTIVES:
{directives_str}

AVAILABLE CAPABILITIES:

Python Sandbox - All tasks:
   - Standard Python libraries are pre-installed
   - Common packages (pandas, numpy, requests, etc.) are available
   - Missing packages will be automatically installed based on imports
   
   Use for:
   - Web search (from ddgs import DDGS)
   - Web scraping (requests, beautifulsoup4)
   - Data analysis (pandas, numpy)
   - API calls (requests, httpx)
   - System monitoring (psutil)
   - Financial data (yfinance)
   - File processing, calculations

{skills_section}

Provide a clear, well-formatted response. If you need to write code:
1. Briefly explain what you'll do (1-2 sentences)
2. Write the Python code in a ```python``` code block
3. You can combine/modify the reference skills above if they're helpful
4. Import any packages you need - they will auto-install

CRITICAL CODE REQUIREMENTS:
- ALWAYS use print() to display results - without print(), the user sees no output!
- Store results in variables AND print them
- Example: result = function(); print(result)
- For functions that return data, call them and print the result

Keep your response concise and user-friendly. Do NOT output your internal reasoning process.
"""
