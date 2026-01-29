# Browser Service Dockerfile
# Headless Chromium browser automation via Playwright
# Base image has Chromium pre-installed

FROM mcr.microsoft.com/playwright/python:v1.50.0-noble

# Set working directory
WORKDIR /app

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Do NOT run `playwright install` - browsers are pre-installed in the base image

# Copy application code
COPY server.py .

# Create data directory for browser profiles
RUN mkdir -p /data/profiles

# Expose port
EXPOSE 8003

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import httpx; r = httpx.get('http://localhost:8003/health'); assert r.status_code == 200" || exit 1

# Run the server
CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8003"]
