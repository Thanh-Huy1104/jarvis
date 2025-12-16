# Internet Search Integration

Jarvis can perform internet searches and scrape web content using multiple methods.

## 🔍 Search Providers

### 1. DuckDuckGo Search (Recommended - No API Key)

**Best for**: Quick searches, news, images, instant answers

**Package**: `ddgs` (replaces deprecated `duckduckgo-search`)

**Example Prompts**:
- "Search DuckDuckGo for latest AI news"
- "Find recent articles about climate change"
- "Search for Python tutorials"

**Code Example**:
```python
from ddgs import DDGS

# Text search
results = DDGS().text("artificial intelligence news", max_results=5)
for r in results:
    print(f"{r['title']}: {r['href']}")
    print(f"{r['body']}\n")

# News search (simpler API - no date filtering)
news = DDGS().news("Tesla stock", max_results=5)
for article in news:
    print(f"{article['title']} - {article['date']}")
    print(f"{article['url']}\n")

# Image search
images = DDGS().images("golden retriever", max_results=5)
for img in images:
    print(f"{img['title']}: {img['image']}")

# Instant answers
answer = DDGS().answers("what is the capital of France")
if answer:
    print(answer[0]['text'] if isinstance(answer, list) else answer)
```

### 2. Web Scraping with BeautifulSoup

**Best for**: Extracting specific content from websites

**Auto-installed**: `beautifulsoup4`, `requests`

**Example Prompts**:
- "Scrape the headlines from news.ycombinator.com"
- "Extract all links from example.com"
- "Get the main article text from this URL"

**Code Example**:
```python
import requests
from bs4 import BeautifulSoup

# Fetch and parse webpage
url = "https://news.ycombinator.com"
response = requests.get(url)
soup = BeautifulSoup(response.text, 'html.parser')

# Extract headlines
headlines = soup.find_all('span', class_='titleline')
for i, headline in enumerate(headlines[:10], 1):
    link = headline.find('a')
    print(f"{i}. {link.text}")
    print(f"   {link['href']}\n")

# Extract all links
all_links = soup.find_all('a')
for link in all_links[:20]:
    print(link.get('href'))

# Extract specific content
article = soup.find('article')
if article:
    paragraphs = article.find_all('p')
    text = '\n'.join(p.text for p in paragraphs)
    print(text)
```

### 3. Wikipedia Search

**Best for**: Encyclopedic information, summaries

**Auto-installed**: `wikipedia`

**Example Prompts**:
- "Search Wikipedia for quantum computing"
- "Get Wikipedia summary of Albert Einstein"
- "Find Wikipedia page about Python programming"

**Code Example**:
```python
import wikipedia

# Search for pages
results = wikipedia.search("machine learning", results=5)
print("Search results:", results)

# Get page summary
summary = wikipedia.summary("Artificial Intelligence", sentences=3)
print(summary)

# Get full page content
page = wikipedia.page("Python (programming language)")
print(f"Title: {page.title}")
print(f"URL: {page.url}")
print(f"Content preview: {page.content[:500]}...")

# Get page sections
print("Sections:", page.sections)
```

### 4. Advanced: JavaScript-Heavy Sites (Playwright)

**Best for**: Sites requiring JavaScript rendering (SPA, dynamic content)

**Setup required**: After first install, run browser setup

**Auto-installed**: `playwright`

**Code Example**:
```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    
    # Navigate and wait for content
    page.goto("https://example.com")
    page.wait_for_selector('.content')
    
    # Extract data
    title = page.title()
    content = page.inner_text('.main-content')
    
    print(f"Title: {title}")
    print(f"Content: {content}")
    
    browser.close()
```

## 🎯 Use Cases & Examples

### Search Current Events
**Prompt**: "Search for today's top tech news and summarize"

```python
from ddgs import DDGS

# Search for recent tech news
news = DDGS().news("technology", max_results=10)

print("Top Tech News:\n")
for i, article in enumerate(news, 1):
    print(f"{i}. {article['title']}")
    print(f"   Source: {article['source']}")
    print(f"   {article['body'][:200]}...")
    print(f"   {article['url']}\n")
```

### Research Topic
**Prompt**: "Research quantum computing - search web AND get Wikipedia summary"

### Research Topic
**Prompt**: "Research quantum computing - search web AND get Wikipedia summary"

```python
from ddgs import DDGS
import wikipedia

topic = "quantum computing"

# Web search
print("=== Web Search Results ===")
results = DDGS().text(topic, max_results=5)
for r in results:
    print(f"{r['title']}: {r['href']}")

# Wikipedia summary
print("\n=== Wikipedia Summary ===")
summary = wikipedia.summary(topic, sentences=5)
print(summary)

# Get detailed page
page = wikipedia.page(topic)
print(f"\nFull article: {page.url}")
### Price Comparison
**Prompt**: "Search for iPhone 15 prices across multiple sites"

```python
from ddgs import DDGS

product = "iPhone 15 Pro price"

results = DDGS().text(product, max_results=10)

print(f"Price comparison for iPhone 15:\n")
for result in results:
    if any(word in result['title'].lower() for word in ['price', '$', 'buy']):
        print(f"{result['title']}")
        print(f"{result['href']}")
        print(f"{result['body'][:150]}...\n")
```
### Scrape Structured Data
**Prompt**: "Scrape top GitHub trending repositories"

```python
import requests
from bs4 import BeautifulSoup

url = "https://github.com/trending"
response = requests.get(url)
soup = BeautifulSoup(response.text, 'html.parser')

repos = soup.find_all('article', class_='Box-row')

print("GitHub Trending Repositories:\n")
for i, repo in enumerate(repos[:10], 1):
    title = repo.find('h2').text.strip().replace('\n', '').replace(' ', '')
    desc = repo.find('p', class_='col-9')
    description = desc.text.strip() if desc else "No description"
    
    stars = repo.find('span', class_='d-inline-block float-sm-right')
    star_count = stars.text.strip() if stars else "N/A"
    
    print(f"{i}. {title}")
    print(f"   {description}")
    print(f"   ⭐ {star_count}\n")
```

### Monitor Website Changes
**Prompt**: "Check if website content has changed"

```python
import requests
from bs4 import BeautifulSoup
import hashlib

def get_content_hash(url, selector):
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    content = soup.select_one(selector).text if soup.select_one(selector) else ""
    return hashlib.md5(content.encode()).hexdigest()

url = "https://news.ycombinator.com"
selector = ".titleline"

current_hash = get_content_hash(url, selector)
print(f"Content hash: {current_hash}")
print("Save this hash and compare later to detect changes")
```

## 🔐 Best Practices

1. **Respect robots.txt**: Check site's robots.txt before scraping
2. **Rate Limiting**: Add delays between requests
3. **User Agent**: Set appropriate User-Agent header
4. **Error Handling**: Handle HTTP errors, timeouts gracefully
5. **Caching**: Cache results to minimize requests

**Example with Best Practices**:
```python
import requests
from bs4 import BeautifulSoup
import time

headers = {
    'User-Agent': 'Mozilla/5.0 (compatible; JarvisBot/1.0)'
}

urls = ["https://example.com/page1", "https://example.com/page2"]

for url in urls:
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        # Process content
        
        time.sleep(1)  # Be nice to the server
        
    except requests.RequestException as e:
        print(f"Error fetching {url}: {e}")
```

## ⚡ Quick Reference

| Task | Best Tool | Code |
|------|-----------|------|
| General search | DuckDuckGo | `DDGS().text(query)` |
| News search | DuckDuckGo News | `DDGS().news(query)` |
| Images | DuckDuckGo Images | `DDGS().images(query)` |
| Encyclopedia | Wikipedia | `wikipedia.summary(topic)` |
| Static HTML | BeautifulSoup | `BeautifulSoup(html, 'html.parser')` |
| JavaScript sites | Playwright | `page.goto(url)` |
| Instant answers | DuckDuckGo Answers | `DDGS().answers(query)` |

## 🚀 Example Prompts to Try

1. "Search for latest Python 3.12 features and summarize"
2. "Find trending AI tools on Product Hunt"
3. "Scrape Hacker News top 10 stories"
4. "Search Wikipedia for history of internet AND get web articles"
5. "Monitor Bitcoin price from multiple sources"
6. "Research best practices for React hooks - search web and documentation"
7. "Find recent research papers on climate change"
8. "Get current weather from weather.com by scraping"
9. "Search for job postings for 'Python developer' and list top 10"
10. "Compare prices for product across Amazon, eBay, and other sites"

## 📦 Installation Notes

All packages auto-install on first use:
- `duckduckgo-search` - ~200ms install time
- `beautifulsoup4` - ~100ms install time  
- `wikipedia` - ~150ms install time
- `playwright` - ~2s install time (larger package)

After first Playwright install, may need browser setup (handled automatically in most cases).
