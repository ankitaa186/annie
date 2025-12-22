# MCP Server Dockerfile
# Python 3.12+ MCP protocol server

FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies including procps for pgrep
RUN apt-get update && apt-get install -y \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

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
