# Web Search with DuckDuckGo

Search the web using DuckDuckGo. Get search results with titles, URLs, and snippets for any query.

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

# Example usage
result = search_web('Python programming tutorials')
```

## Usage Examples

- Search for programming tutorials
- Find documentation or articles
- Research any topic on the web
