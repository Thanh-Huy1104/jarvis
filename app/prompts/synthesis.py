"""Prompt templates for result synthesis"""


def get_synthesis_prompt(user_input: str, execution_result: str) -> str:
    """Generate prompt for synthesizing execution results"""
    return f"""The user asked: {user_input}

Code was executed and produced this output:
{execution_result}

Create a clear, natural response that:
1. Answers the user's question directly
2. Presents the data in an easy-to-read format
3. Highlights key findings or important information
4. Keep it concise but informative

DO NOT include the raw code or technical details unless relevant.
"""


def get_parallel_synthesis_prompt(user_input: str, results_context: str) -> str:
    """Generate prompt for synthesizing parallel execution results"""
    return f"""You executed multiple tasks in parallel. Analyze the ACTUAL results below.

{results_context}

Instructions:
1. Report ONLY what is shown in the "Result" sections above.
2. If a task failed or produced an error, state that it failed. DO NOT invent data.
3. If the result is an error message, report the error.
4. Compare the findings if relevant (e.g., "Apple is higher than Bitcoin").

Format:
- Summarize the successful findings.
- Mention any failures clearly.
- Answer the user's original question based on the REAL data.

CRITICAL: Do not hallucinate numbers or APIs. If the code didn't work, say so."""
