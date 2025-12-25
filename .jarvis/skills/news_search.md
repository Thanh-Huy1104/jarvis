---
name: news-search
description: Search for recent news articles using DuckDuckGo.
version: 1.0.0
tools: [python]
dependencies: [ddgs]
---

# News Search

## Description
This skill performs a news-specific search using DuckDuckGo. It returns a formatted list of recent articles including titles, sources, URLs, and excerpts. Useful for catching up on current events, company news, or specific topics.

## When to Use
- When the user asks for "news about X".
- When checking recent developments for a company or topic.
- Example queries: "Latest news on OpenAI", "What's happening in tech today?".

## How to Use
Call `search_news(query, region='us', max_results=10)`.

```python
# Get 5 recent news items about Bloomberg
news = search_news('Bloomberg', max_results=5)
```

## Dependencies
- `ddgs`: DuckDuckGo Search library.

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
```

## Troubleshooting
- **No Results**: Try removing specific keywords or changing the region.
- **Rate Limits**: Excessive searching might trigger DDG rate limits.

```