# Base image with Python
FROM python:3.12-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Create a working directory
WORKDIR /app

# Pre-install common data science libs to speed up execution
# This prevents 'uv' from downloading them every single time
RUN uv pip install --system numpy pandas requests scipy

# Default command (overridden by the tool)
CMD ["python3"]