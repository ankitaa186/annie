# MCP Server Dockerfile
# Python 3.12+ MCP protocol server

FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies including procps for pgrep and Playwright deps
RUN apt-get update && apt-get install -y \
    procps \
    # Playwright/Chromium dependencies
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers for crawl4ai
RUN playwright install chromium

# Copy application code (will be overridden by volume mount in dev)
COPY . /app/mcp_server

# Expose port for HTTP transport
EXPOSE 8002

# Health check - HTTP endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8002/health').raise_for_status()" || exit 1

# Copy and set entrypoint script
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

CMD ["/docker-entrypoint.sh"]
