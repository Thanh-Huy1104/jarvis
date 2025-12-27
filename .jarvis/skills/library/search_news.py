from tavily import TavilyClient
import os

def search_news(query: str, max_results: int = 5) -> str:
    """
    Search for the latest news articles and headlines using Tavily.
    Optimized for finding recent events and headlines.
    """
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return "Error: TAVILY_API_KEY not found."

    print(f"📰 News Search: '{query}'")
    
    try:
        tavily = TavilyClient(api_key=api_key)
        # topic="news" prioritizes recent and news-related content
        response = tavily.search(query=query, topic="news", max_results=max_results)
        
        results = response.get("results", [])
        if not results:
            return "No news found."
            
        output = [f"# News Report: {query}\n"]
        for i, r in enumerate(results, 1):
            title = r.get('title', 'No Title')
            url = r.get('url', 'No URL')
            content = r.get('content', 'No content')
            # Tavily news results often have a published date
            date = r.get('published_date', 'Unknown Date')
            
            output.append(f"## {i}. {title}\n**Date:** {date}\n**URL:** {url}\n\n{content}\n")
            
        return "\n".join(output)
        
    except Exception as e:
        return f"News search failed: {e}"