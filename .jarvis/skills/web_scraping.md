---
name: web-scraping
description: Scrape and parse HTML content from websites using BeautifulSoup.
version: 1.0.0
tools: [python]
dependencies: [requests, beautifulsoup4]
---

# Web Scraping

## Description
Fetches and parses the HTML content of a given URL using `requests` and `BeautifulSoup`. It extracts the page title and the first 10 links as a default behavior, but the code can be easily modified to extract specific data tables, text, or images.

## When to Use
- When the user wants to read a website.
- When extracting specific data from a page (like a table or list).
- Example queries: "Scrape example.com", "Get links from this page".

## How to Use
Call `scrape_webpage(url)`.

```python
data = scrape_webpage('https://example.com')
print(data['title'])
```

## Dependencies
- `requests`: HTTP client.
- `beautifulsoup4`: HTML parser.

## Code

```python
import requests
from bs4 import BeautifulSoup

def scrape_webpage(url):
    """
    Fetch and parse a webpage.
    """
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Example: Extract all links
        links = []
        for a in soup.find_all('a', href=True):
            links.append({
                'text': a.get_text(strip=True),
                'url': a['href']
            })
        
        return {
            'title': soup.title.string if soup.title else 'No title',
            'links': links[:10]  # First 10 links
        }
    except Exception as e:
        return f'Error: {str(e)}'
```

## Troubleshooting
- **403 Forbidden**: The site might be blocking bots. Set a User-Agent header in `requests.get`.
- **Connection Error**: Check internet connection or URL validity.
- **Dynamic Content**: This skill cannot scrape content rendered by JavaScript (React/Vue/Angular sites). Use a headless browser skill for that.

```