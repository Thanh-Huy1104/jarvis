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
    return f"""You executed multiple tasks in parallel. Analyze the results and provide a clear, insightful summary.

{results_context}

Provide a natural response that:
1. Acknowledges what was done in parallel
2. For EACH task, show the code that was generated and its output
3. Highlight interesting findings or patterns in the results
4. Answer the user's original question directly

Format each task's output like this:
**Task: [description]**
```python
[the actual code]
```
**Output:**
```
[the result]
```

Be concise but informative. Show all code blocks and results."""
