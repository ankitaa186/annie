# Telegram Bot Dockerfile
# Python 3.12+ Telegram bot service

FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python packages
COPY requirements.txt /app/telegram_bot/requirements.txt
RUN pip install --no-cache-dir -r /app/telegram_bot/requirements.txt

# Copy application code into telegram_bot package
COPY . /app/telegram_bot/

# Set Python path to include /app
ENV PYTHONPATH=/app

# Health check - verify bot module can be imported. The real liveness signal
# is the watchdog inside bot.py (sys.exit(1) when polling dies → Docker restart).
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import telegram_bot; import sys; sys.exit(0)" || exit 1

# Entrypoint for Telegram bot - run as module
CMD ["python", "-m", "telegram_bot"]
