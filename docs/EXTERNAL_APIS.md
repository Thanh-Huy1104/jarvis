# External API Integration Guide

## Overview
Jarvis can execute code that interacts with external APIs and services. This guide shows how to enable different integrations.

## Supported Integrations

### 1. Google Calendar API

**Setup:**
1. Enable Google Calendar API in Google Cloud Console
2. Create OAuth2 credentials or Service Account
3. Download credentials JSON file
4. Mount credentials in docker-compose:

```yaml
services:
  jarvis_sandbox:
    volumes:
      - ./jarvis_data/workspace:/workspace
      - ./credentials/google-calendar.json:/workspace/credentials/google-calendar.json:ro
```

**Environment Variables:**
Add to `.env`:
```bash
GOOGLE_APPLICATION_CREDENTIALS=/workspace/credentials/google-calendar.json
```

**Usage Example:**
```python
# Jarvis will auto-install google-api-python-client
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/calendar']
creds = service_account.Credentials.from_service_account_file(
    '/workspace/credentials/google-calendar.json', scopes=SCOPES)

service = build('calendar', 'v3', credentials=creds)

# List upcoming events
events = service.events().list(
    calendarId='primary',
    maxResults=10,
    singleEvents=True,
    orderBy='startTime'
).execute()

for event in events.get('items', []):
    print(event['summary'])
```

### 2. System Queries (Safe)

The sandbox can execute safe system queries. Dangerous commands are blocked.

**Allowed:**
- File system queries: `ls`, `find`, `grep`
- System info: `uname`, `hostname`, `whoami`
- Process info: `ps`, `top` (read-only)
- Network info: `ping`, `curl` (GET only)

**Blocked:**
- Write operations: `rm`, `mv`, `cp`
- System modifications: `chmod`, `chown`
- Network writes: `curl -X POST`

**Usage Example:**
```python
import subprocess

# Check system info
result = subprocess.run(['uname', '-a'], capture_output=True, text=True)
print(f"System: {result.stdout}")

# List files
result = subprocess.run(['ls', '-la'], capture_output=True, text=True)
print(result.stdout)
```

### 3. Web APIs (REST)

**Auto-installed packages:**
- `requests` - HTTP library
- `httpx` - Async HTTP library

**Usage Example:**
```python
import requests

# Weather API
response = requests.get('https://api.weather.gov/gridpoints/TOP/31,80/forecast')
data = response.json()
print(data['properties']['periods'][0]['detailedForecast'])

# Cryptocurrency prices
response = requests.get('https://api.coinbase.com/v2/prices/BTC-USD/spot')
price = response.json()['data']['amount']
print(f"Bitcoin: ${price}")
```

### 4. Database Connections

**Supported databases:**
- PostgreSQL: `psycopg2-binary`
- MySQL: `mysql-connector-python`
- SQLite: Built-in
- MongoDB: `pymongo`
- Redis: `redis`

**Setup (PostgreSQL example):**
Add to `.env`:
```bash
DATABASE_URL=postgresql://user:password@host:5432/dbname
```

Mount in docker-compose:
```yaml
services:
  jarvis_sandbox:
    environment:
      - DATABASE_URL=${DATABASE_URL}
```

**Usage Example:**
```python
import os
import psycopg2

conn = psycopg2.connect(os.environ['DATABASE_URL'])
cursor = conn.cursor()

cursor.execute("SELECT * FROM users LIMIT 10")
for row in cursor.fetchall():
    print(row)

conn.close()
```

### 5. Cloud Storage

**AWS S3:**
```python
import boto3
import os

s3 = boto3.client('s3',
    aws_access_key_id=os.environ['AWS_ACCESS_KEY_ID'],
    aws_secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY']
)

# List buckets
response = s3.list_buckets()
for bucket in response['Buckets']:
    print(bucket['Name'])
```

**Google Cloud Storage:**
```python
from google.cloud import storage

client = storage.Client()
buckets = client.list_buckets()
for bucket in buckets:
    print(bucket.name)
```

## Package Auto-Installation

The sandbox automatically detects and installs common packages:

| Import | Package Installed |
|--------|------------------|
| `numpy`, `np` | `numpy` |
| `pandas`, `pd` | `pandas` |
| `matplotlib`, `plt` | `matplotlib` |
| `sklearn` | `scikit-learn` |
| `cv2` | `opencv-python` |
| `requests` | `requests` |
| `httpx` | `httpx` |

To add more mappings, edit `app/execution/sandbox.py`:

```python
package_map = {
    'numpy': 'numpy',
    'pandas': 'pandas',
    # Add your custom mappings
    'google': 'google-api-python-client',
    'boto3': 'boto3',
}
```

## Security Considerations

1. **Network Access**: Sandbox has internet access for package installation and API calls
2. **Credentials**: Mount credentials as read-only volumes
3. **Environment Variables**: Use `.env` file, never hardcode secrets
4. **Resource Limits**: Sandbox limited to 512MB RAM, 1 CPU
5. **Timeout**: Code execution limited to 30 seconds by default

## Advanced: Custom Docker Image

For pre-installed packages and credentials:

1. Create `Dockerfile`:
```dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y curl

# Pre-install Python packages
RUN pip install uv && \
    uv pip install --system \
    numpy pandas matplotlib requests \
    google-api-python-client boto3

# Copy credentials
COPY credentials/ /workspace/credentials/

WORKDIR /workspace
CMD ["tail", "-f", "/dev/null"]
```

2. Update `docker-compose.yml`:
```yaml
services:
  jarvis_sandbox:
    build: ./sandbox
    # ... rest of config
```

3. Rebuild:
```bash
docker-compose build jarvis_sandbox
docker-compose up -d jarvis_sandbox
```

## Examples

### Query Google Calendar
"Show my calendar events for tomorrow"

### System Monitoring
"Check CPU usage and running processes"

### Weather Data
"Get the weather forecast for San Francisco"

### Database Query
"Show the top 10 users from the database"

### File System
"Find all Python files modified in the last 24 hours"

### API Integration
"Fetch Bitcoin price and create a chart of the last 30 days"
