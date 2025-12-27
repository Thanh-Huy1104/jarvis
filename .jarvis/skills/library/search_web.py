from tavily import TavilyClient
import os

def search_web(query: str, max_results: int = 5) -> str:
    """
    Perform a standard web search to find information, facts, or URLs using Tavily.
    Fast and efficient for quick fact-checking.
    """
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return "Error: TAVILY_API_KEY not found."

    print(f"🔍 Web Search: '{query}'")
    
    try:
        tavily = TavilyClient(api_key=api_key)
        # search_depth="basic" is faster
        response = tavily.search(query=query, search_depth="basic", max_results=max_results)
        
        results = response.get("results", [])
        if not results:
            return "No results found."
            
        output = []
        for i, r in enumerate(results, 1):
            title = r.get('title', 'No Title')
            url = r.get('url', 'No URL')
            content = r.get('content', 'No content')
            
            output.append(f"{i}. {title}\n   URL: {url}\n   {content}\n")
            
        return "\n".join(output)
        
    except Exception as e:
        return f"Web search failed: {e}"