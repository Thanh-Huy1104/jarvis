# Web Scraping with BeautifulSoup

Scrape and parse HTML content from websites.

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

# Example usage
# result = scrape_webpage('https://example.com')
# print(result)
```

## Usage Examples

- Extract content from web pages
- Parse HTML tables
- Collect links or specific elements
- Monitor website changes
