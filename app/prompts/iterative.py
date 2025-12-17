"""Prompt templates for iterative research"""
from typing import List, Dict, Any


def get_iterative_prompt(
    user_input: str, 
    memory_context: str, 
    current_date: str, 
    skills_section: str = ""
) -> str:
    """Generate initial prompt for iterative research"""
    
    context_section = f"\n{memory_context}\n" if memory_context else ""
    
    return f"""TASK: {user_input}{context_section}

CURRENT DATE: {current_date}

You are an iterative research assistant. You can make multiple tool calls to thoroughly answer this question.

APPROACH:
1. Start by searching for information (use ddgs)
2. Review the search results
3. Scrape specific URLs to get detailed content (use requests + BeautifulSoup)
4. Analyze and synthesize the information
5. Repeat if you need more information
6. Provide a comprehensive final answer when done

AVAILABLE TOOLS (Python packages):
- ddgs (DDGS) - Web search
- requests + beautifulsoup4 - Web scraping
- pandas, numpy - Data analysis
{skills_section}

INSTRUCTIONS:
- Write Python code for each step
- Print results so you can see them
- After seeing results, decide if you need more information
- When satisfied, write code that prints "[DONE]" and provide your final answer
- Be thorough - don't stop after just one search

Start by writing Python code to search for information about this topic."""


def get_continuation_prompt(
    user_input: str, 
    research_history: List[Dict[str, Any]], 
    last_result: str,
    current_date: str
) -> str:
    """Generate continuation prompt after each tool call"""
    
    steps_summary = f"You've completed {len(research_history)} research steps so far.\n\n"
    steps_summary += f"Last result:\n{last_result[:1000]}\n\n"
    
    return f"""TASK: {user_input}

CURRENT DATE: {current_date}

{steps_summary}

What's your next action?

AVAILABLE TOOLS (Python packages):
- ddgs (DDGS) - Web search.
- requests + beautifulsoup4 - Web scraping.
- pandas, numpy - Data analysis.

OPTIONS:
1. If you need MORE information:
   - Write Python code to search different keywords
   - Scrape specific URLs from previous results
   - Analyze data in a different way

2. If you have ENOUGH information:
   - Write code that prints "[DONE]"
   - Provide your comprehensive final answer

Remember: The goal is to FULLY answer the question with detailed, specific information.
Don't stop after just surface-level results - dig deeper when needed."""
