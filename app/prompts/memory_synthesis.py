"""Prompt templates for memory synthesis"""


def get_memory_synthesis_prompt(user_input: str, assistant_response: str, execution_result: str = "") -> str:
    """Generate prompt for synthesizing interaction into memory-friendly format"""
    
    context = f"User asked: {user_input}\n\n"
    
    if execution_result:
        context += f"Assistant executed code and produced:\n{execution_result}\n\n"
    
    context += f"Assistant responded:\n{assistant_response}"
    
    return f"""Summarize this interaction into 2-3 concise bullet points for memory storage.

{context}

Requirements:
- Extract key facts, preferences, or important information
- Include specific data points (names, numbers, results)
- Be concise but informative
- Use bullet point format with "-"
- Focus on what's worth remembering for future conversations

Example format:
- User requested CPU usage data; highest reading was 85%
- User prefers detailed explanations with code examples

Provide ONLY the bullet points, no introduction or conclusion."""
