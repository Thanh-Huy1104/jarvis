# News Search with DuckDuckGo

Search for recent news articles using DuckDuckGo. Get news about companies, topics, or events with titles, sources, URLs and excerpts.

## Code

```python
from ddgs import DDGS

def search_news(query, region='us', max_results=10):
    """
    Search for recent news using DuckDuckGo.
    Note: date filtering is not supported in ddgs package.
    """
    try:
        results = list(DDGS().news(
            query=query,
            region=region,
            max_results=max_results
        ))
        
        if not results:
            return f"No news found for '{query}'. Try broader search terms."
        
        news_summary = []
        for i, result in enumerate(results, 1):
            title = result.get('title', 'No title')
            source = result.get('source', 'Unknown source')
            url = result.get('url', result.get('href', 'No URL'))
            excerpt = result.get('excerpt', result.get('body', 'No excerpt available'))
            
            news_summary.append(
                f"{i}. {title}\n   {source}: {url}\n   {excerpt}\n"
            )
        
        output = '\n'.join(news_summary)
        print(output)
        return output
        
    except Exception as e:
        error_msg = f'Error searching news: {str(e)}'
        print(error_msg)
        return error_msg

# Example usage
result = search_news('Bloomberg', max_results=5)
```

## Usage Examples

- Get latest news about a company (e.g., "Bloomberg recent developments")
- Search for current events or breaking news
- Find news in specific regions
