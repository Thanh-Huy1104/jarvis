from tavily import TavilyClient
import os

def deep_research(query: str, max_results: int = 5) -> str:
    """
    Performs a deep web search using the Tavily API, optimized for LLMs. 
    It returns clean, extracted content from multiple sources.
    """
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return "Error: TAVILY_API_KEY not found in environment."

    print(f"🔍 Tavily Research: '{query}'")
    
    try:
        tavily = TavilyClient(api_key=api_key)
        # 'advanced' search depth fetches full content
        response = tavily.search(query=query, search_depth="advanced", max_results=max_results)
        
        results = response.get("results", [])
        if not results:
            return "No results found."
            
        report = [f"# Research Report: {query}\n"]
        
        for i, r in enumerate(results, 1):
            title = r.get('title', 'No Title')
            url = r.get('url', 'No URL')
            content = r.get('content', 'No content')
            
            report.append(f"## Source {i}: {title}\n**URL:** {url}\n\n{content}\n\n{'-'*40}\n")
            
        return "\n".join(report)
        
    except Exception as e:
        return f"Tavily search failed: {e}"