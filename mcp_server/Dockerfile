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

# Health check - verify process is running
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD pgrep -f "python.*mcp_server.server" || exit 1

# Entrypoint for stdio transport (MCP server)
# PYTHONPATH includes /app so mcp_server package can be imported
CMD ["sh", "-c", "PYTHONPATH=/app python -m mcp_server.server"]
