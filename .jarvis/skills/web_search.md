---
name: web-search
description: Search the web using DuckDuckGo to find articles, documentation, or general information.
version: 1.0.0
tools: [python]
dependencies: [ddgs]
---

# Web Search

## Description
Performs a general web search using DuckDuckGo. Returns a list of results with titles, URLs, and text snippets. This is the primary tool for finding information on the internet.

## When to Use
- When the user asks a question requiring external knowledge.
- When finding documentation, tutorials, or facts.
- Example queries: "Search for Python tutorials", "Who won the super bowl?", "Find documentation for FastAPI".

## How to Use
Call `search_web(query, max_results=5)`.

```python
results = search_web('Python programming tutorials')
print(results)
```

## Dependencies
- `ddgs`: DuckDuckGo Search library.

## Code

```python
from ddgs import DDGS

def search_web(query, max_results=5):
    """
    Search the web using DuckDuckGo.
    Returns: title, href (URL), and body (snippet)
    """
    try:
        results = list(DDGS().text(query, max_results=max_results))
        
        if not results:
            return f"No results found for '{query}'. Try different search terms."
        
        search_results = []
        for i, result in enumerate(results, 1):
            title = result.get('title', 'No title')
            url = result.get('href', result.get('url', 'No URL'))
            body = result.get('body', result.get('excerpt', 'No description'))
            
            search_results.append(
                f"{i}. {title}\n   URL: {url}\n   {body}\n"
            )
        
        output = '\n'.join(search_results)
        print(output)
        return output
        
    except Exception as e:
        error_msg = f'Error searching web: {str(e)}'
        print(error_msg)
        return error_msg
```

## Troubleshooting
- **No Results**: Broaden search terms.
- **Rate Limits**: If searching too frequently, DDG might block the request temporarily.

```