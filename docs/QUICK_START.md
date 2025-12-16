# Jarvis Intricate Code Execution - Quick Start

## ✅ What's Now Enabled

1. **Logging**: All INFO level logs now visible (routing, planning, execution details)
2. **Auto Package Installation**: 15+ common packages auto-detected and installed with `uv`
3. **Environment Variables**: API keys available in sandbox via `.env`
4. **Credentials Mount**: `/workspace/credentials/` for JSON credential files
5. **Network Access**: Full internet for APIs and package installation

## 🚀 Example Prompts You Can Now Use

### System Queries
```
"Check system uptime and memory usage"
"Find all Python files in the workspace"
"Show running processes"
```

### Web APIs
```
"Fetch the latest Bitcoin price from Coinbase API"
"Get weather forecast for San Francisco"
"Query the GitHub API for trending repositories"
```

### Internet Search (No API Key Required!)
```
"Search DuckDuckGo for latest AI news"
"Find recent articles about climate change and summarize"
"Search Wikipedia for quantum computing"
"Scrape Hacker News top 10 stories"
"Research Python 3.12 new features - search web AND get Wikipedia summary"
```

### Google Calendar (after setup)
```
"List my calendar events for tomorrow"
"Find all meetings next week"
"Show me today's schedule"
```

### Data Analysis
```
"Download CSV from URL and analyze top 10 patterns"
"Fetch stock data for AAPL and create a chart"
"Query API and generate statistical summary"
```

### Database Operations (after setup)
```
"Connect to PostgreSQL and show user table schema"
"Query MongoDB for recent documents"
"Run SELECT query and export to CSV"
```

### Complex Multi-Step
```
"Fetch Bitcoin AND Ethereum prices, then create comparison chart AND calculate 7-day moving average"
"Query database for users, filter by activity, AND generate report"
"Download 3 different datasets, analyze each, AND create combined visualization"
```

## 📦 Pre-Installed Package Detection

When your code imports these, Jarvis auto-installs the package:

| Import Statement | Package Installed |
|-----------------|------------------|
| `import numpy` or `import numpy as np` | `numpy` |
| `import pandas` or `import pandas as pd` | `pandas` |
| `import matplotlib.pyplot as plt` | `matplotlib` |
| `from sklearn import ...` | `scikit-learn` |
| `import cv2` | `opencv-python` |
| `import requests` | `requests` |
| `import httpx` | `httpx` |
| `import boto3` | `boto3` (AWS SDK) |
| `from google.oauth2 import ...` | `google-api-python-client` |
| `import psycopg2` | `psycopg2-binary` (PostgreSQL) |
| `import pymongo` | `pymongo` (MongoDB) |
| `import redis` | `redis` |
| `from sqlalchemy import ...` | `sqlalchemy` |
| `from duckduckgo_search import DDGS` | `duckduckgo-search` |
| `from bs4 import BeautifulSoup` | `beautifulsoup4` |
| `import wikipedia` | `wikipedia` |
| `from playwright.sync_api import ...` | `playwright` |

## 🔧 Setup for External APIs

### Google Calendar

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create project → Enable Calendar API
3. Create Service Account → Download JSON key
4. Save as `/home/th/jarvis_data/credentials/google-calendar.json`
5. Share your calendar with the service account email

### AWS Services

Add to `/home/th/jarvis-agent/.env`:
```bash
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_DEFAULT_REGION=us-east-1
```

### Database

Add to `/home/th/jarvis-agent/.env`:
```bash
DATABASE_URL=postgresql://user:password@host:5432/dbname
# or
DATABASE_URL=mysql://user:password@host:3306/dbname
```

Then restart Jarvis.

## 🔍 Debugging with Logs

With logging now enabled, you'll see:

```
============================================================
ROUTING: should_parallelize
User input: create table AND generate primes AND calculate pi
Keywords found: ['and']
AND count: 2, Comma count: 0
→ DECISION: parallel_planner
============================================================

============================================================
PARALLEL PLANNING STARTED
User input: create table AND generate primes AND calculate pi
============================================================
LLM response (sanitized): {"parallel":true,"subtasks":[...]}
✓ Task can be parallelized into 3 subtasks:
  Task 1: [task_1] Create multiplication table
  Task 2: [task_2] Generate prime numbers
  Task 3: [task_3] Calculate pi
Created 3 SubTask objects

============================================================
ROUTING: route_after_planning
Plan in state: [SubTask(...), SubTask(...), SubTask(...)]
Plan length: 3
→ DECISION: parallel_executor (3 tasks)
============================================================

============================================================
PARALLEL EXECUTION STARTED
============================================================
Creating 3 worker tasks...
  Worker 1: [task_1] Create multiplication table
  Worker 2: [task_2] Generate prime numbers  
  Worker 3: [task_3] Calculate pi
Starting parallel execution with asyncio.gather()

[Each worker shows detailed execution logs]
```

## 💡 Tips

1. **Parallel Execution**: Use "AND" between independent tasks
2. **Package Installation**: First run is slower (installs packages), subsequent runs are fast
## 📚 Full Documentation

- **Internet Search**: `/home/th/jarvis-agent/docs/INTERNET_SEARCH.md`
- **External APIs**: `/home/th/jarvis-agent/docs/EXTERNAL_APIS.md`

## 📚 Full Documentation

See `/home/th/jarvis-agent/docs/EXTERNAL_APIS.md` for complete guide.
