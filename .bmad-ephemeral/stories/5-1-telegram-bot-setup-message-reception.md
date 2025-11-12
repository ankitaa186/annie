# Story 5.1: Telegram Bot Setup & Message Reception

Status: ready-for-dev

## Story

**As a** user,
**I want** to chat with Annie via Telegram,
**So that** I can get decision support on my mobile device.

**Epic:** Epic 5 - Telegram Bot Interface
**Prerequisites:** Story 2.1 (Backend API Foundation), Story 1.2 (Docker Compose & Service Configuration)
**Estimated Effort:** 2 points (2 days)

## Acceptance Criteria

### AC #1: Bot connects to Telegram API and starts polling
**Given** Telegram bot token is configured
**When** the bot service starts
**Then** it connects to Telegram API successfully and starts polling for updates

**Mapped to Tasks:** Task 1, Task 2

---

### AC #1.1: User authorization whitelist loaded on startup
**Given** AUTHORIZED_USER_IDS is configured in environment
**When** the bot starts
**Then** the whitelist is loaded into memory for fast authorization checks (<50ms)

**Mapped to Tasks:** Task 3

---

### AC #2: Authorized users receive message processing within 1 second
**Given** the bot is running and I am an authorized user
**When** I send a message via Telegram
**Then** the bot receives and processes the message within 1 second

**Mapped to Tasks:** Task 2, Task 4

---

### AC #2.1: Unauthorized users receive rejection message
**Given** the bot is running and I am NOT an authorized user
**When** I send a message via Telegram
**Then** the bot responds with "Sorry, you're not authorized to use Annie. Please contact the administrator for access." and does NOT forward to backend

**Mapped to Tasks:** Task 3, Task 4

---

### AC #3: User message data extracted and logged correctly
**Given** a message is received from an authorized user
**When** I check logs
**Then** user_id, message_text, timestamp, message_id are extracted correctly and authorization status is logged

**Mapped to Tasks:** Task 4, Task 7

---

### AC #4: Text messages handled correctly after authorization
**Given** different message types
**When** I send text messages
**Then** the bot handles them correctly (after authorization check)

**Mapped to Tasks:** Task 4, Task 5

---

### AC #5: Voice messages handled appropriately
**Given** different message types
**When** I send voice messages
**Then** the bot handles them appropriately (V1: return "Voice messages coming soon" or transcribe)

**Mapped to Tasks:** Task 5

---

### AC #6: Messages forwarded to backend API with proper formatting
**Given** the bot receives a message from an authorized user
**When** I check processing
**Then** it forwards the message to backend API (POST /api/chat) with proper formatting

**Mapped to Tasks:** Task 6

---

### AC #7: Connection failures handled gracefully with retry logic
**Given** the bot is running
**When** connection failures occur
**Then** they are handled gracefully with retry logic and logging

**Mapped to Tasks:** Task 2, Task 7

---

### AC #7.1: Unauthorized access attempts logged for security monitoring
**Given** unauthorized access attempts occur
**When** I check logs
**Then** unauthorized user_ids are logged for security monitoring without exposing sensitive data

**Mapped to Tasks:** Task 3, Task 7

---

## Tasks / Subtasks

### Task 1: Setup Telegram Bot Service Docker Container
**Status:** TODO
**Acceptance Criteria:** AC #1

**Implementation Details:**
- Create `telegram_bot/` directory structure
- Create `telegram_bot/Dockerfile`:
  ```dockerfile
  FROM python:3.12-slim

  WORKDIR /app

  COPY requirements.txt .
  RUN pip install --no-cache-dir -r requirements.txt

  COPY . .

  CMD ["python", "-m", "telegram_bot.bot"]
  ```
- Create `telegram_bot/requirements.txt`:
  ```
  python-telegram-bot==20.7
  aiohttp==3.9.1
  python-dotenv==1.0.0
  pydantic==2.5.0
  redis==5.0.0
  ```
- Add telegram-bot service to `docker-compose.yml`:
  ```yaml
  telegram-bot:
    build:
      context: ./telegram_bot
      dockerfile: Dockerfile
    container_name: annie-telegram-bot
    restart: unless-stopped
    env_file:
      - .env
    environment:
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
      - AUTHORIZED_USER_IDS=${AUTHORIZED_USER_IDS}
      - BACKEND_URL=http://backend:8000
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
      - ENVIRONMENT=${ENVIRONMENT:-dev}
    networks:
      - annie-network
    depends_on:
      - backend
    healthcheck:
      test: ["CMD", "python", "-c", "import sys; sys.exit(0)"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
  ```
- Update `.env.example` with new variables:
  ```
  # Telegram Bot Configuration
  TELEGRAM_BOT_TOKEN=REPLACE_ME
  AUTHORIZED_USER_IDS=REPLACE_ME  # Comma-separated Telegram user IDs
  POLLING_TIMEOUT=30
  ```

**Technical Notes:**
- Follow Docker patterns from Story 1.2
- Use Python 3.12-slim base image for consistency
- Service depends on backend for API calls
- Health check ensures container is running (basic check)

**Subtasks:**
- [ ] Create telegram_bot/ directory structure
- [ ] Create telegram_bot/Dockerfile
- [ ] Create telegram_bot/requirements.txt
- [ ] Update docker-compose.yml with telegram-bot service
- [ ] Update .env.example with new variables
- [ ] Test Docker build locally
- [ ] Verify service starts with make start

---

### Task 2: Initialize Telegram Bot with Long Polling
**Status:** TODO
**Acceptance Criteria:** AC #1, AC #2, AC #7

**Implementation Details:**
- Create `telegram_bot/bot.py` main entry point:
  ```python
  import asyncio
  import logging
  import os
  from telegram.ext import Application, ApplicationBuilder

  from telegram_bot.config import get_config
  from telegram_bot.logging import setup_logging
  from telegram_bot.handlers.message import setup_message_handlers

  logger = logging.getLogger(__name__)

  async def main():
      """Main entry point for Telegram bot."""
      # Setup logging
      setup_logging()

      # Load config
      config = get_config()
      bot_token = config["TELEGRAM_BOT_TOKEN"]

      # Build application
      app = (
          ApplicationBuilder()
          .token(bot_token)
          .build()
      )

      # Setup handlers
      setup_message_handlers(app)

      # Start polling
      logger.info("Starting Telegram bot polling", extra={
          "polling_timeout": config.get("POLLING_TIMEOUT", 30)
      })

      await app.run_polling(
          allowed_updates=["message"],
          drop_pending_updates=True,
          timeout=int(config.get("POLLING_TIMEOUT", 30))
      )

  if __name__ == "__main__":
      asyncio.run(main())
  ```
- Create `telegram_bot/config.py` for configuration:
  ```python
  import os
  from typing import Dict
  from dotenv import load_dotenv

  load_dotenv()

  def get_config() -> Dict[str, str]:
      """Load and validate configuration from environment."""
      config = {
          "TELEGRAM_BOT_TOKEN": os.getenv("TELEGRAM_BOT_TOKEN"),
          "AUTHORIZED_USER_IDS": os.getenv("AUTHORIZED_USER_IDS", ""),
          "BACKEND_URL": os.getenv("BACKEND_URL", "http://backend:8000"),
          "LOG_LEVEL": os.getenv("LOG_LEVEL", "INFO"),
          "ENVIRONMENT": os.getenv("ENVIRONMENT", "dev"),
          "POLLING_TIMEOUT": os.getenv("POLLING_TIMEOUT", "30"),
          "MAX_RETRIES": os.getenv("MAX_RETRIES", "3"),
      }

      # Validate required fields
      if not config["TELEGRAM_BOT_TOKEN"]:
          raise ValueError("TELEGRAM_BOT_TOKEN is required")
      if not config["AUTHORIZED_USER_IDS"]:
          raise ValueError("AUTHORIZED_USER_IDS is required")

      return config
  ```
- Implement connection retry logic with exponential backoff
- Add structured logging for polling events
- Long polling timeout: 30 seconds (configurable)
- Handle graceful shutdown on SIGTERM

**Technical Notes:**
- Use python-telegram-bot 20.7+ async API
- Long polling preferred over webhooks for V1 simplicity
- Exponential backoff for connection failures (1s, 2s, 4s, max 3 retries)
- Drop pending updates on startup to avoid processing stale messages
- allowed_updates=["message"] filters out non-message updates

**Subtasks:**
- [ ] Create telegram_bot/bot.py with main entry point
- [ ] Create telegram_bot/config.py for environment loading
- [ ] Implement polling initialization
- [ ] Add connection retry logic with exponential backoff
- [ ] Add graceful shutdown handler (SIGTERM)
- [ ] Add structured logging for polling events
- [ ] Test bot connects to Telegram API
- [ ] Verify polling starts successfully

---

### Task 3: Implement User Authorization Module
**Status:** TODO
**Acceptance Criteria:** AC #1.1, AC #2.1, AC #7.1

**Implementation Details:**
- Create `telegram_bot/auth.py`:
  ```python
  import logging
  from typing import Set

  logger = logging.getLogger(__name__)

  class AuthenticationModule:
      """Manages user authorization via whitelist."""

      def __init__(self, authorized_user_ids: str):
          """
          Initialize authentication module.

          Args:
              authorized_user_ids: Comma-separated list of Telegram user IDs
          """
          self.authorized_users: Set[int] = set()
          self._load_whitelist(authorized_user_ids)

      def _load_whitelist(self, authorized_user_ids: str):
          """Load and parse whitelist from comma-separated string."""
          if not authorized_user_ids:
              logger.warning("No authorized users configured")
              return

          for user_id_str in authorized_user_ids.split(","):
              user_id_str = user_id_str.strip()
              if user_id_str:
                  try:
                      user_id = int(user_id_str)
                      self.authorized_users.add(user_id)
                  except ValueError:
                      logger.error(
                          "Invalid user ID in whitelist",
                          extra={"invalid_value": user_id_str}
                      )

          logger.info(
              "Authorization whitelist loaded",
              extra={"authorized_count": len(self.authorized_users)}
          )

      def is_authorized(self, user_id: int) -> bool:
          """
          Check if user is authorized.

          Args:
              user_id: Telegram user ID

          Returns:
              True if authorized, False otherwise
          """
          authorized = user_id in self.authorized_users

          if not authorized:
              logger.warning(
                  "Unauthorized access attempt",
                  extra={
                      "user_id": user_id,
                      "authorized": False
                  }
              )

          return authorized

      def get_rejection_message(self) -> str:
          """Get rejection message for unauthorized users."""
          return (
              "Sorry, you're not authorized to use Annie. "
              "Please contact the administrator for access."
          )
  ```
- Whitelist loaded on bot startup (in-memory set for O(1) lookup)
- Authorization check happens BEFORE backend forwarding
- Unauthorized attempts logged with user_id (no PII)
- Performance target: <50ms for authorization check

**Technical Notes:**
- Use Python set for O(1) authorization lookup
- Parse AUTHORIZED_USER_IDS on startup (comma-separated)
- Log unauthorized attempts for security monitoring
- Rejection message user-friendly, no technical details
- Consider future migration to database-backed user management

**Subtasks:**
- [ ] Create telegram_bot/auth.py
- [ ] Implement AuthenticationModule class
- [ ] Implement whitelist loading from environment
- [ ] Implement is_authorized check (O(1) lookup)
- [ ] Add logging for unauthorized attempts
- [ ] Test with valid and invalid user IDs
- [ ] Verify <50ms lookup performance

---

### Task 4: Implement Message Handler with Authorization
**Status:** TODO
**Acceptance Criteria:** AC #2, AC #2.1, AC #3, AC #4

**Implementation Details:**
- Create `telegram_bot/handlers/message.py`:
  ```python
  import logging
  from telegram import Update
  from telegram.ext import ContextTypes, MessageHandler, filters

  from telegram_bot.auth import AuthenticationModule
  from telegram_bot.config import get_config

  logger = logging.getLogger(__name__)

  # Global auth module (initialized once)
  auth_module = None

  def setup_message_handlers(application):
      """Setup message handlers with authorization."""
      global auth_module

      config = get_config()
      auth_module = AuthenticationModule(config["AUTHORIZED_USER_IDS"])

      # Register message handler
      application.add_handler(
          MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
      )

  async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
      """
      Handle incoming text messages with authorization.

      Args:
          update: Telegram update object
          context: Bot context
      """
      global auth_module

      # Extract message data
      message = update.message
      user_id = message.from_user.id
      chat_id = message.chat_id
      message_text = message.text
      message_id = message.message_id
      timestamp = message.date
      username = message.from_user.username

      # Log message receipt
      logger.info(
          "Message received",
          extra={
              "user_id": user_id,
              "chat_id": chat_id,
              "message_id": message_id,
              "message_length": len(message_text),
              "timestamp": timestamp.isoformat()
          }
      )

      # Authorization check
      if not auth_module.is_authorized(user_id):
          logger.warning(
              "Unauthorized message blocked",
              extra={"user_id": user_id}
          )
          await message.reply_text(auth_module.get_rejection_message())
          return

      # Authorized - proceed with processing
      logger.info(
          "Message authorized",
          extra={"user_id": user_id, "authorized": True}
      )

      # Send typing indicator
      await context.bot.send_chat_action(chat_id=chat_id, action="typing")

      # Forward to backend (Task 6)
      # TODO: Implement backend forwarding

      # Placeholder response for testing
      await message.reply_text("Message received! (Backend integration pending)")
  ```
- Extract user_id, chat_id, message_text, message_id, timestamp from Update
- Check authorization BEFORE forwarding (fail-fast pattern)
- Send rejection message for unauthorized users
- Log all message events with structured logging
- Send typing indicator for authorized messages

**Technical Notes:**
- Use python-telegram-bot MessageHandler with filters.TEXT
- Authorization check is first operation (fail-fast)
- Structured logging with user context (user_id, message_id, timestamp)
- Do not log message content (privacy consideration)
- typing indicator shows Annie is processing

**Subtasks:**
- [ ] Create telegram_bot/handlers/message.py
- [ ] Implement setup_message_handlers function
- [ ] Implement handle_message with authorization check
- [ ] Extract message data (user_id, text, timestamp, message_id)
- [ ] Send rejection message for unauthorized users
- [ ] Send typing indicator for authorized users
- [ ] Add structured logging for all events
- [ ] Test with authorized and unauthorized users

---

### Task 5: Handle Different Message Types (Text, Voice)
**Status:** TODO
**Acceptance Criteria:** AC #4, AC #5

**Implementation Details:**
- Extend message handlers to handle voice messages:
  ```python
  # In telegram_bot/handlers/message.py

  async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
      """Handle voice messages."""
      message = update.message
      user_id = message.from_user.id

      # Authorization check
      if not auth_module.is_authorized(user_id):
          await message.reply_text(auth_module.get_rejection_message())
          return

      # V1: Voice messages not supported
      await message.reply_text(
          "Voice messages coming soon! For now, please send text messages."
      )

      logger.info(
          "Voice message received",
          extra={
              "user_id": user_id,
              "message_id": message.message_id,
              "voice_duration": message.voice.duration if message.voice else None
          }
      )

  def setup_message_handlers(application):
      """Setup message handlers."""
      global auth_module

      config = get_config()
      auth_module = AuthenticationModule(config["AUTHORIZED_USER_IDS"])

      # Text messages
      application.add_handler(
          MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
      )

      # Voice messages
      application.add_handler(
          MessageHandler(filters.VOICE, handle_voice)
      )
  ```
- Text messages: Fully supported (handled by handle_message)
- Voice messages: Return "Voice messages coming soon" (V1 limitation)
- Other message types (images, videos, documents): Ignored for V1

**Technical Notes:**
- Use python-telegram-bot filters (filters.TEXT, filters.VOICE)
- Voice transcription deferred to future version
- Log unsupported message types for future feature prioritization
- Authorization check required for all message types

**Subtasks:**
- [ ] Add voice message handler
- [ ] Return "Voice messages coming soon" message
- [ ] Add authorization check for voice messages
- [ ] Log voice message events
- [ ] Test voice message handling
- [ ] Verify text messages still work correctly

---

### Task 6: Integrate Backend API Client for Message Forwarding
**Status:** TODO
**Acceptance Criteria:** AC #6

**Implementation Details:**
- Create `telegram_bot/backend_client.py`:
  ```python
  import logging
  import aiohttp
  from typing import Dict, Optional

  logger = logging.getLogger(__name__)

  class BackendClient:
      """HTTP client for Backend API communication."""

      def __init__(self, backend_url: str, timeout: int = 10):
          """
          Initialize backend client.

          Args:
              backend_url: Base URL for backend API
              timeout: Request timeout in seconds
          """
          self.backend_url = backend_url.rstrip("/")
          self.timeout = aiohttp.ClientTimeout(total=timeout)

      async def send_message(
          self,
          user_id: int,
          message: str,
          conversation_id: Optional[str] = None
      ) -> Dict:
          """
          Send user message to backend API.

          Args:
              user_id: Telegram user ID
              message: User message text
              conversation_id: Optional conversation ID for context

          Returns:
              Response from backend API

          Raises:
              aiohttp.ClientError: If request fails
          """
          payload = {
              "user_id": f"telegram_{user_id}",
              "platform": "telegram",
              "message": message,
              "conversation_id": conversation_id
          }

          url = f"{self.backend_url}/api/chat"

          async with aiohttp.ClientSession(timeout=self.timeout) as session:
              try:
                  async with session.post(url, json=payload) as response:
                      response.raise_for_status()
                      result = await response.json()

                      logger.info(
                          "Message sent to backend",
                          extra={
                              "user_id": user_id,
                              "conversation_id": result.get("conversation_id"),
                              "status": result.get("status"),
                              "status_code": response.status
                          }
                      )

                      return result

              except aiohttp.ClientError as e:
                  logger.error(
                      "Backend request failed",
                      extra={
                          "user_id": user_id,
                          "error": str(e),
                          "url": url
                      }
                  )
                  raise
  ```
- Update `telegram_bot/handlers/message.py` to use BackendClient:
  ```python
  from telegram_bot.backend_client import BackendClient

  backend_client = None

  def setup_message_handlers(application):
      """Setup message handlers."""
      global auth_module, backend_client

      config = get_config()
      auth_module = AuthenticationModule(config["AUTHORIZED_USER_IDS"])
      backend_client = BackendClient(config["BACKEND_URL"])

      # ... handler setup

  async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
      """Handle incoming messages."""
      # ... authorization check ...

      # Forward to backend
      try:
          response = await backend_client.send_message(
              user_id=user_id,
              message=message_text,
              conversation_id=None  # TODO: Track conversation_id
          )

          conversation_id = response.get("conversation_id")
          status = response.get("status")

          logger.info(
              "Backend response received",
              extra={
                  "conversation_id": conversation_id,
                  "status": status
              }
          )

          # TODO: Stream response from backend (Story 5.2)

      except Exception as e:
          logger.error("Failed to forward message to backend", exc_info=True)
          await message.reply_text(
              "I'm having trouble right now. Please try again in a moment."
          )
  ```
- POST request to `/api/chat` with user_id (prefixed "telegram_"), platform, message, conversation_id
- Timeout: 10 seconds (backend should respond quickly)
- Error handling: Retry with exponential backoff (3 attempts)
- User-friendly error message on failure

**Technical Notes:**
- Use aiohttp for async HTTP requests
- Prefix user_id with "telegram_" for platform identification
- conversation_id tracked for multi-turn conversations (future)
- Error handling critical for user experience
- Structured logging for debugging

**Subtasks:**
- [ ] Create telegram_bot/backend_client.py
- [ ] Implement BackendClient class
- [ ] Implement send_message method with POST /api/chat
- [ ] Add timeout and error handling
- [ ] Integrate BackendClient into message handler
- [ ] Add retry logic with exponential backoff
- [ ] Test backend forwarding with running backend
- [ ] Test error handling (backend down)

---

### Task 7: Logging Infrastructure for Telegram Bot
**Status:** TODO
**Acceptance Criteria:** AC #3, AC #7, AC #7.1

**Implementation Details:**
- Create `telegram_bot/logging.py`:
  ```python
  import logging
  import sys
  from telegram_bot.config import get_config

  def setup_logging():
      """Setup structured logging for Telegram bot."""
      config = get_config()
      log_level = config.get("LOG_LEVEL", "INFO")
      environment = config.get("ENVIRONMENT", "dev")

      # Configure root logger
      logging.basicConfig(
          level=getattr(logging, log_level),
          format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
          stream=sys.stdout
      )

      # Create service logger
      logger = logging.getLogger("telegram_bot")
      logger.setLevel(getattr(logging, log_level))

      # Add structured logging adapter
      # TODO: Consider JSON logging for production

      logger.info(
          "Logging initialized",
          extra={
              "service": "telegram-bot",
              "log_level": log_level,
              "environment": environment
          }
      )

      return logger
  ```
- Structured logging with JSON format for production
- Log levels: DEBUG (dev), INFO (production), WARNING, ERROR, CRITICAL
- Required signals:
  - Message received: `{"event":"message_received","user_id":...,"message_length":...}`
  - Authorization check: `{"event":"authorization","user_id":...,"authorized":...}`
  - Backend call: `{"event":"backend_call","user_id":...,"status_code":...}`
  - Unauthorized attempt: `{"event":"unauthorized_attempt","user_id":...}`
- Sensitive data masking: Do not log message content, only metadata
- All logs include service="telegram-bot" for filtering

**Technical Notes:**
- Follow logging patterns from Story 1.4
- Use structured logging with extra fields
- Mask sensitive data (message content, user personal info)
- Include request context (user_id, message_id) in all logs
- Performance: Log at INFO level, DEBUG for development

**Subtasks:**
- [ ] Create telegram_bot/logging.py
- [ ] Implement setup_logging function
- [ ] Configure log levels from environment
- [ ] Add structured logging format
- [ ] Test logging output format
- [ ] Verify sensitive data masked
- [ ] Test log levels (INFO, DEBUG, ERROR)

---

## Definition of Done

- [ ] All 7 tasks completed
- [ ] All 9 acceptance criteria validated with evidence
- [ ] Telegram bot service running in Docker
- [ ] Bot connects to Telegram API successfully
- [ ] User authorization whitelist working (<50ms lookup)
- [ ] Authorized users can send messages
- [ ] Unauthorized users receive rejection message
- [ ] Messages forwarded to backend API correctly
- [ ] Voice messages handled with "coming soon" message
- [ ] Connection failures handled with retry logic
- [ ] Structured logging operational
- [ ] Unauthorized attempts logged for security monitoring
- [ ] Health check passing
- [ ] Service starts with make start
- [ ] No regressions in existing functionality (Stories 1.1-3.2 tests still pass)

---

## Learnings from Previous Story

**From Story 3.2: Memory Retrieval for Decision Support (Status: done)**

**Relevant Patterns for This Story:**

**1. Async HTTP Client Patterns:**
- Use aiohttp.AsyncClient for async HTTP operations (similar to MemoryClient)
- Set timeouts to prevent hanging (10s for backend, 300ms for memory)
- Handle connection errors gracefully (catch aiohttp.ClientError)
- Connection pooling automatic with aiohttp
- Implement retry logic for transient failures
- Pattern:
  ```python
  async with aiohttp.ClientSession(timeout=timeout) as session:
      async with session.post(url, json=payload) as response:
          response.raise_for_status()
          return await response.json()
  ```

**2. Structured Logging Patterns:**
- Add timing instrumentation: `start_time = time.time()` → `duration_ms = int((time.time() - start_time) * 1000)`
- Log performance metrics with structured logging
- Include user context in all logs (user_id, message_id)
- Log at INFO level for successful operations, WARNING for empty/failed results
- Pattern:
  ```python
  logger.info("Event description", extra={
      "user_id": user_id,
      "message_id": message_id,
      "duration_ms": duration_ms,
      "status": "success"
  })
  ```

**3. Graceful Degradation:**
- Continue core functionality when external services fail
- Return user-friendly error messages (no technical details)
- Log failures but don't crash the service
- Pattern:
  ```python
  try:
      result = await external_service.call()
  except Exception as e:
      logger.error("Service call failed", exc_info=True)
      return fallback_response()
  ```

**4. Configuration and Environment Variables:**
- Load from .env file using python-dotenv
- Validate required fields on startup (fail fast)
- Use sensible defaults for optional fields
- Pattern:
  ```python
  config = {
      "REQUIRED_FIELD": os.getenv("REQUIRED_FIELD"),
      "OPTIONAL_FIELD": os.getenv("OPTIONAL_FIELD", "default_value")
  }
  if not config["REQUIRED_FIELD"]:
      raise ValueError("REQUIRED_FIELD is required")
  ```

**5. Performance Monitoring:**
- Set performance targets (e.g., <1s message processing, <50ms auth check)
- Add timing instrumentation throughout
- Log performance warnings if targets exceeded
- Monitor metrics from day 1

**Technical Debt from Story 3.2:**
- Tests not implemented (comprehensive test suite needed)
- Documentation not fully updated
- These should be addressed in Story 5.1 to avoid accumulation

**Recommendations for This Story:**
- **FOLLOW async/await patterns** from Story 3.2 for HTTP client
- **USE aiohttp** for backend API communication (same as MemoryClient)
- **APPLY structured logging** pattern with user context
- **IMPLEMENT graceful degradation** when backend unavailable
- **TEST thoroughly** - don't defer testing like Story 3.2
- **DOCUMENT as you go** - update CLAUDE.md, add code comments
- **MONITOR performance** from day 1 (message processing time, auth check time)
- **VALIDATE security** - authorization check, logging patterns

[Source: .bmad-ephemeral/stories/3-2-memory-retrieval-decision-support.md]

---

## Dev Notes

### Architecture Context

**Component Overview:**
- **TelegramBotService** (`telegram_bot/bot.py`): Main orchestration, polling, message routing
- **AuthenticationModule** (`telegram_bot/auth.py`): User authorization via whitelist
- **MessageHandler** (`telegram_bot/handlers/message.py`): Message extraction, validation, routing
- **BackendClient** (`telegram_bot/backend_client.py`): HTTP client for backend API
- **FormattingModule** (`telegram_bot/formatters.py`): Future - Telegram markdown formatting (Story 5.3)
- **StreamingHandler** (`telegram_bot/handlers/streaming.py`): Future - SSE streaming (Story 5.2)
- **Telegram Bot API** (External): Message reception/sending

**Service Communication Flow:**
```
1. Telegram API → Long Polling → Telegram Bot Service
2. Telegram Bot Service → Extract message data
3. Telegram Bot Service → AuthenticationModule.is_authorized(user_id)
4. If unauthorized → Send rejection message → STOP
5. If authorized → Send typing indicator
6. Telegram Bot Service → BackendClient.send_message(user_id, message)
7. BackendClient → HTTP POST /api/chat
8. Backend API → Process message (LLM, tools, memory)
9. Backend API → Return conversation_id and status
10. Telegram Bot Service → Log response
11. Future (Story 5.2): Stream response back to user
```

**User Message Model:**
```python
{
    "user_id": int,              # Telegram user ID (numeric)
    "message_text": str,         # Full message content
    "timestamp": datetime,       # Message timestamp (ISO 8601)
    "message_id": int,           # Telegram message ID
    "chat_id": int,              # Telegram chat ID
    "username": str | None       # Telegram username (optional)
}
```

**Backend API Request (POST /api/chat):**
```python
{
    "user_id": "telegram_12345",   # Platform-prefixed user ID
    "platform": "telegram",
    "message": "Should I buy AAPL stock?",
    "conversation_id": str | None  # Existing conversation or null
}
```

**Backend API Response:**
```python
{
    "conversation_id": "conv_abc123",
    "status": "processing" | "completed" | "error",
    "message": str | None          # For synchronous responses
}
```

### Technical Constraints

**From Tech Spec (tech-spec-epic-5.md):**

1. **Performance Requirements:**
   - Message receipt latency: <1 second from Telegram API to bot processing
   - Authorization check: <50ms (in-memory set lookup)
   - Backend API call: <10s timeout (backend should respond quickly)
   - Long polling timeout: 30 seconds

2. **Security Requirements:**
   - User authorization via AUTHORIZED_USER_IDS whitelist
   - Comma-separated list of Telegram user IDs
   - Unauthorized users receive rejection message
   - Authorization check BEFORE backend forwarding (fail-fast)
   - Unauthorized attempts logged for security monitoring
   - No sensitive data in logs (mask message content, PII)

3. **Telegram API Constraints:**
   - Long polling timeout: 30 seconds maximum
   - Rate limiting: 30 messages/second per bot
   - Message edits: 20 edits/minute per message (Story 5.2 concern)
   - Message length limit: 4096 characters (Story 5.2 concern)

4. **Error Handling:**
   - Retry logic with exponential backoff (1s, 2s, 4s, max 3 retries)
   - Graceful degradation when backend unavailable
   - User-friendly error messages (no technical jargon)
   - Connection failures logged and retried
   - Circuit breaker pattern for persistent backend failures (future)

5. **Logging Requirements:**
   - Structured logging with JSON format (production)
   - Log levels: DEBUG (dev), INFO (prod), WARNING, ERROR, CRITICAL
   - Required signals:
     - message_received (user_id, message_length, timestamp)
     - authorization (user_id, authorized: true/false)
     - backend_call (user_id, conversation_id, status_code, duration_ms)
     - unauthorized_attempt (user_id)
   - Mask sensitive data (message content, personal info)

### Dependencies

**New Dependencies:**
- `python-telegram-bot==20.7` - Telegram Bot API client
- `aiohttp==3.9.1` - Async HTTP client for backend
- `python-dotenv==1.0.0` - Environment variable loading
- `pydantic==2.5.0` - Data validation (optional, for future)
- `redis==5.0.0` - Redis client (for future caching)

**Existing Dependencies** (from previous stories):
- Docker and Docker Compose (Epic 1)
- Backend API (Epic 2): POST /api/chat, GET /api/stream/{conversation_id}
- Redis (Epic 2): For session management (via backend)
- Structured logging infrastructure (Epic 1)

**External Services:**
- Telegram Bot API (api.telegram.org)
- Backend API (http://backend:8000)
- Configuration: TELEGRAM_BOT_TOKEN, AUTHORIZED_USER_IDS in .env

### Key Files to Create/Modify

**New Files:**
- `telegram_bot/bot.py` - Main entry point, polling initialization
- `telegram_bot/config.py` - Environment configuration
- `telegram_bot/logging.py` - Structured logging setup
- `telegram_bot/auth.py` - User authorization module
- `telegram_bot/handlers/__init__.py` - Handlers package
- `telegram_bot/handlers/message.py` - Message handler with authorization
- `telegram_bot/backend_client.py` - Backend API HTTP client
- `telegram_bot/Dockerfile` - Docker container definition
- `telegram_bot/requirements.txt` - Python dependencies
- `telegram_bot/__init__.py` - Package initialization

**Files to Modify:**
- `docker-compose.yml` - Add telegram-bot service
- `.env.example` - Add TELEGRAM_BOT_TOKEN, AUTHORIZED_USER_IDS
- `CLAUDE.md` - Document Telegram bot setup and usage

**Future Files (Story 5.2, 5.3):**
- `telegram_bot/handlers/streaming.py` - SSE streaming handler
- `telegram_bot/formatters.py` - Telegram markdown formatting
- `telegram_bot/error_handler.py` - Centralized error handling

### Testing Strategy

**Unit Tests:**
- Test AuthenticationModule.is_authorized with valid/invalid user IDs
- Test AuthenticationModule whitelist loading (valid/invalid formats)
- Test BackendClient.send_message with mocked aiohttp responses
- Test BackendClient error handling (timeout, connection error, HTTP errors)
- Test config validation (missing required fields)
- Test logging setup and output format
- Mock all external services (Telegram API, Backend API)
- Target: >80% code coverage

**Integration Tests:**
- Test full message flow (Telegram update → authorization → backend forwarding)
- Test authorized user can send messages
- Test unauthorized user receives rejection
- Test backend forwarding with running backend (or mocked)
- Test connection retry logic (simulate backend failures)
- Test graceful degradation (backend down)
- Use python-telegram-bot test utilities
- Use fakeredis or Docker Redis for caching

**Manual Testing:**
- Test with real Telegram bot (BotFather registration)
- Test with authorized Telegram user ID
- Test with unauthorized user ID
- Test voice message handling
- Test connection failures (stop backend)
- Test message processing latency (<1s)
- Test authorization check latency (<50ms)

**Performance Validation:**
- Measure message receipt latency (target: <1s)
- Measure authorization check time (target: <50ms)
- Measure backend API call time (target: <10s)
- Load test with 100 concurrent messages
- Monitor polling connection stability

### Implementation Approach

**Phase 1: Docker Setup (Task 1)**
1. Create telegram_bot/ directory structure
2. Create Dockerfile and requirements.txt
3. Add telegram-bot service to docker-compose.yml
4. Update .env.example
5. Test Docker build and service startup

**Phase 2: Bot Initialization (Task 2)**
1. Create bot.py with main entry point
2. Implement polling initialization
3. Add connection retry logic
4. Test bot connects to Telegram API

**Phase 3: Authorization (Task 3)**
1. Implement AuthenticationModule
2. Load whitelist from environment
3. Implement is_authorized check
4. Test authorization logic

**Phase 4: Message Handling (Task 4)**
1. Create message handler with authorization
2. Extract message data
3. Send rejection message for unauthorized users
4. Send typing indicator for authorized users
5. Test message handling flow

**Phase 5: Message Types (Task 5)**
1. Add voice message handler
2. Return "Voice messages coming soon"
3. Test voice message handling

**Phase 6: Backend Integration (Task 6)**
1. Create BackendClient
2. Implement send_message method
3. Integrate into message handler
4. Add retry logic
5. Test backend forwarding

**Phase 7: Logging (Task 7)**
1. Setup structured logging
2. Add logging to all components
3. Test log output format
4. Verify sensitive data masked

**Phase 8: Testing & Documentation**
1. Create unit tests (>80% coverage)
2. Create integration tests
3. Update CLAUDE.md
4. Code review and validation

### Success Metrics

- ✅ All 9 acceptance criteria implemented and validated
- ✅ Telegram bot connects successfully
- ✅ User authorization working (<50ms lookup)
- ✅ Authorized users can send messages
- ✅ Unauthorized users receive rejection
- ✅ Messages forwarded to backend correctly
- ✅ Voice messages handled appropriately
- ✅ Connection failures handled gracefully
- ✅ Structured logging operational
- ✅ Performance: <1s message receipt, <50ms auth check
- ✅ Test coverage: >80% for bot modules
- ✅ Zero regressions in Stories 1.1-3.2 functionality

---

## References

1. **Epic & Story Breakdown** (`docs/epics-and-stories.md`)
   - Lines 726-760: Story 5.1 user story and acceptance criteria
   - Prerequisites: Story 2.1 (Backend API), Story 1.2 (Docker)
   - Estimated effort: 2 points (2 days)

2. **Epic 5 Technical Specification** (`.bmad-ephemeral/stories/tech-spec-epic-5.md`)
   - Services and Modules section: TelegramBotService, AuthenticationModule, MessageHandler, BackendClient
   - Data Models: User Message Model, Backend API Request/Response
   - Performance requirements: <1s message receipt, <50ms auth check
   - Security requirements: User authorization whitelist, logging
   - Complete acceptance criteria for all Story 5.1 ACs

3. **Story 3.2: Memory Retrieval** (`.bmad-ephemeral/stories/3-2-memory-retrieval-decision-support.md`)
   - Async HTTP client patterns (aiohttp)
   - Structured logging patterns
   - Graceful degradation patterns
   - Performance monitoring patterns
   - Testing patterns (pytest-asyncio, respx)

4. **Product Requirements** (`docs/01-product/PRODUCT_REQUIREMENTS.md`)
   - Telegram bot interface requirement
   - User authentication requirement (friends/relatives only)
   - Decision support value proposition

5. **Architecture Plan** (`docs/02-architecture/ARCHITECTURE_PLAN.md`)
   - Telegram Bot Service architecture
   - Service communication flow
   - Data flow patterns

6. **Project Instructions** (`CLAUDE.md`)
   - Docker Compose patterns
   - Environment variable management
   - Service configuration

---

**Created:** 2025-11-11
**Epic:** Epic 5 - Telegram Bot Interface
**Story:** 5.1 - Telegram Bot Setup & Message Reception
**Status:** drafted

---

## Dev Agent Record

### Context Reference

**Story Context XML:** `.bmad-ephemeral/stories/5-1-telegram-bot-setup-message-reception.context.xml`

Generated: 2025-11-11
Generated by: story-context workflow
Contains: Documentation artifacts, code interfaces, dependencies, development constraints, testing standards and ideas

### Agent Model Used

<!-- Will be filled when story implementation begins -->

### Debug Log References

<!-- Will be filled during implementation -->

### Completion Notes List

<!-- Will be filled when story is completed -->

### File List

<!-- Will be filled when story is completed -->
