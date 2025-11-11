# Telegram Bot Dockerfile
# Python 3.12+ Telegram bot service

FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import telegram; print('ok')" || exit 1

# Entrypoint for Telegram bot
# Will be configured when Telegram bot implementation is created
CMD ["python", "-m", "telegram_bot.bot"]
