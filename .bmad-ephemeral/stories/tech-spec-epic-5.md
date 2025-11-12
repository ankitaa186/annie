# Epic Technical Specification: Telegram Bot Interface

Date: 2025-11-11
Author: Ankit
Epic ID: 5
Status: Draft

---

## Overview

Epic 5 implements the Telegram bot interface that serves as the primary user-facing platform for Annie in V1.0 MVP. This epic establishes the communication bridge between users and Annie's backend infrastructure, enabling users to interact with Annie's decision-making capabilities through Telegram's messaging platform. The Telegram bot receives user messages, forwards them to the Backend API for processing, and streams AI-generated responses back to users in real-time. This epic transforms Annie from a backend system into an accessible, user-friendly chatbot that friends and relatives can use daily for decision support.

The implementation leverages the python-telegram-bot library for Telegram API integration, connects to Annie's existing Backend API (Epic 2), and implements streaming response delivery to provide real-time feedback. This epic is critical for achieving the product goal of helping users with 80% of day-to-day decisions, as it provides the accessible interface through which users will interact with Annie's AI-powered analysis, memory, and tool capabilities.

## Objectives and Scope

**In Scope:**
- Telegram bot service setup with proper Docker configuration and health checks
- **User authentication and authorization via whitelisted Telegram user IDs**
- Message reception from Telegram API using long polling mechanism
- User message extraction and validation (user_id, message_text, timestamp, message_id)
- Backend API integration via HTTP calls to POST /api/chat and GET /api/stream/{conversation_id}
- Streaming response delivery with incremental token updates every 100-500ms
- **"Thinking..." indicators for LLM reasoning delays (thinking models can take 10-30s before first token)**
- Message formatting with Telegram markdown support (bold, italic, code, links)
- Error handling for backend failures, service unavailability, and network issues
- Typing indicators to show Annie is processing responses
- Message splitting for responses exceeding Telegram's 4096 character limit
- Connection retry logic and graceful degradation

**Out of Scope:**
- Voice message transcription (V1 may return "Voice messages coming soon" message)
- Image or video message handling (deferred to V2.0 multi-modality)
- Webhook-based message reception (V1 uses long polling; webhooks deferred to production optimization)
- Group chat support (V1 is individual user only)
- Inline keyboard/button interactions (deferred to V1.1+ for advanced UX)
- Message editing or deletion features (linear conversation flow only)
- Telegram-specific features like stickers, GIFs, or location sharing

## System Architecture Alignment

This epic aligns with the "Telegram Bot Service" component defined in the Architecture Plan. The Telegram bot operates as an isolated Docker container within the annie-network, communicating exclusively with the Backend API service via HTTP. The architecture follows a clear separation of concerns:

**Service Communication Flow:**
```
Telegram API (External)
    ↓ Long Polling
Telegram Bot Service (Container: telegram-bot)
    ↓ HTTP POST /api/chat
Backend API Service (Container: backend)
    ↓ SSE Stream via GET /api/stream/{conversation_id}
Telegram Bot Service
    ↓ Telegram API send_message
User receives streaming response
```

**Constraints Addressed:**
- Uses Docker containerization as required by architecture
- Integrates with Backend API's existing endpoints (Story 2.1: /api/chat, Story 2.3: /api/stream)
- Leverages SSE streaming architecture established in Epic 2
- Implements health checks consistent with other services
- Follows structured logging patterns defined in Epic 1
- Respects Telegram Bot API limitations (4096 char messages, rate limiting)

**Dependencies:**
- Backend API health endpoint (GET /health) for readiness checks
- Backend chat endpoint (POST /api/chat) for message processing
- Backend streaming endpoint (GET /api/stream/{conversation_id}) for response delivery
- Redis for session management (via Backend API)
- Environment variable TELEGRAM_BOT_TOKEN for authentication

## Detailed Design

### Services and Modules

| Service/Module | Responsibilities | Inputs | Outputs | Owner |
|----------------|------------------|--------|---------|-------|
| **TelegramBotService** | Main bot orchestration, polling, message routing | Telegram updates, backend responses | Telegram messages, logs | telegram_bot/bot.py |
| **AuthenticationModule** | Validate user authorization against whitelist | Telegram user_id | Authorized (bool), rejection message | telegram_bot/auth.py |
| **MessageHandler** | Extract and validate user messages | Telegram message object | Normalized message dict | telegram_bot/handlers/message.py |
| **StreamingHandler** | Poll backend SSE stream, update Telegram messages, handle thinking indicators | Backend SSE events | Incremental message updates, thinking messages | telegram_bot/handlers/streaming.py |
| **FormattingModule** | Convert markdown to Telegram format, split long messages | Raw text response | Formatted, split messages | telegram_bot/formatters.py |
| **ErrorHandler** | Handle backend errors, retries, user-friendly messaging | Exception objects, error codes | User error messages | telegram_bot/error_handler.py |
| **BackendClient** | HTTP client for backend API calls | User messages, conversation IDs | Chat responses, SSE streams | telegram_bot/backend_client.py |
| **HealthCheck** | Bot service health validation | N/A | Health status | telegram_bot/health.py |

### Data Models and Contracts

**User Message Model (Input):**
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

**SSE Stream Event (GET /api/stream/{conversation_id}):**
```
data: {"type":"token","content":"Based"}
data: {"type":"token","content":" on"}
data: {"type":"token","content":" your"}
data: {"type":"done","tokens_used":{"prompt":100,"completion":200}}
data: {"type":"error","message":"LLM API failure"}
```

**Telegram Response Message:**
```python
{
    "chat_id": int,
    "text": str,                   # Max 4096 characters
    "parse_mode": "Markdown",
    "disable_notification": bool
}
```

### APIs and Interfaces

**Backend API Endpoints (Consumed by Telegram Bot):**

1. **POST /api/chat**
   - **Purpose**: Submit user message for processing
   - **Request Body**: `{"user_id": str, "platform": str, "message": str, "conversation_id": str | None}`
   - **Response**: `{"conversation_id": str, "status": str, "message": str | None}` (200 OK)
   - **Errors**: 400 (invalid input), 500 (internal error), 503 (service unavailable)

2. **GET /api/stream/{conversation_id}**
   - **Purpose**: Stream LLM response tokens via SSE
   - **Path Params**: `conversation_id` (string)
   - **Response**: SSE event stream with `{"type": str, "content": str}` events
   - **Event Types**: "token" (incremental text), "done" (completion), "error" (failure)
   - **Errors**: 404 (conversation not found), 500 (streaming error)

3. **GET /health**
   - **Purpose**: Check backend availability
   - **Response**: `{"status": "ok", "timestamp": str}` (200 OK)
   - **Errors**: 503 (service unavailable)

**Telegram Bot API Methods (Used by Bot):**

1. **getUpdates** - Long polling for new messages
   - Params: `offset`, `timeout`, `allowed_updates`
   - Returns: Array of Update objects

2. **sendMessage** - Send text response to user
   - Params: `chat_id`, `text`, `parse_mode`, `disable_notification`
   - Returns: Message object

3. **sendChatAction** - Show typing indicator
   - Params: `chat_id`, `action` ("typing")
   - Returns: True on success

4. **editMessageText** - Update existing message (for streaming)
   - Params: `chat_id`, `message_id`, `text`, `parse_mode`
   - Returns: Message object

### Workflows and Sequencing

**Message Processing Sequence:**

1. **Telegram Bot polls for updates** (getUpdates with 30s timeout)
2. **New message received**:
   - Extract user_id, chat_id, message_text, message_id, timestamp
   - **Check user authorization**: Lookup user_id in AUTHORIZED_USER_IDS whitelist
   - **If unauthorized**: Send rejection message, log attempt, STOP processing
   - **If authorized**: Continue to step 3
   - Validate message is text (skip voice/media for V1)
   - Log message receipt with user context
3. **Send initial feedback**:
   - `sendChatAction(chat_id, "typing")`
   - Send placeholder message: "Annie is thinking deeply about your question..." (for thinking model UX)
4. **Forward to Backend API**: `POST /api/chat` with user message
5. **Backend returns conversation_id and status**
6. **If status == "processing"**: Open SSE stream to `GET /api/stream/{conversation_id}`
7. **Stream handling loop**:
   - Receive SSE event
   - **If no tokens after 5s**: Update message to "Still thinking... (complex reasoning takes time)" (repeat every 10s)
   - If type=="token": Accumulate text, send/edit message every 100-500ms
   - If type=="done": Finalize message, log completion
   - If type=="error": Handle error, send user-friendly error message
8. **Send final complete message** to user via `editMessageText` (replace "thinking" message)
9. **Log conversation completion** with message count, duration, reasoning time

**Error Handling Sequence:**

1. **Error occurs** (backend timeout, API failure, network error)
2. **Classify error type**:
   - Transient (network timeout) → Retry with exponential backoff (max 3 attempts)
   - Backend unavailable (503) → Send "I'm having trouble right now. Please try again in a moment."
   - Invalid input (400) → Send "I didn't understand that. Could you try rephrasing?"
   - Unknown error (500) → Send "I encountered an issue. Please try again."
3. **Log error** with context (user_id, conversation_id, error type, stack trace)
4. **Notify user** with appropriate error message (no technical jargon)
5. **Reset state** for next message

**Streaming Update Flow:**

1. **Initialize**: Create placeholder message "Annie is thinking..."
2. **Accumulate tokens**: Buffer incoming tokens from SSE stream
3. **Update frequency**: Every 100-500ms or every 50 tokens (whichever comes first)
4. **Telegram rate limiting**: Max 20 edits per minute per message
5. **Message splitting**: If accumulated text exceeds 4000 chars:
   - Send current message as-is
   - Create new message for continuation
   - Continue streaming to new message
6. **Completion**: Send final message with complete response

## Non-Functional Requirements

### Performance

- **First Token Latency (Thinking Models)**: 10-30 seconds for first token due to LLM reasoning (Grok-4, ChatGPT-5 with extended thinking)
  - Telegram poll latency: <1s
  - Backend API call: <500ms
  - **LLM reasoning time**: 10-30s (thinking models analyze before responding)
  - SSE stream initiation: <500ms
  - **User Feedback**: Show "Annie is thinking deeply about your question..." message immediately, update every 5s during reasoning
- **Streaming Update Frequency**: 100-500ms between message updates (once tokens start flowing)
- **Message Processing Throughput**: Handle 100 concurrent users without degradation
- **Polling Efficiency**: Long polling timeout of 30 seconds to minimize unnecessary API calls
- **Error Recovery Time**: <5 seconds to retry and recover from transient failures
- **Authentication Check**: <50ms for user authorization check (in-memory whitelist lookup)

**Source**: PRD Success Metrics - <2s response time adjusted for thinking models; Architecture Plan - Backend API <500ms (p95)

**Note**: Thinking models (Grok-4, ChatGPT-5 with reasoning) require significantly longer time before first token compared to standard models. User experience optimization via "thinking" indicators is critical.

### Security

- **User Authorization**: Whitelist-based access control via AUTHORIZED_USER_IDS environment variable
  - Comma-separated list of authorized Telegram user IDs (e.g., "12345,67890,111213")
  - Unauthorized users receive clear rejection: "Sorry, you're not authorized to use Annie. Please contact the administrator for access."
  - Authorization check occurs BEFORE forwarding any message to backend (fail-fast pattern)
  - Unauthorized attempts logged with user_id for security monitoring
- **Authentication**: Telegram bot token stored as environment variable TELEGRAM_BOT_TOKEN
- **Token Protection**: Never log or expose bot token in error messages or logs
- **User Privacy**: Do not log message content beyond necessary debugging info (mask PII)
- **Input Validation**: Validate all incoming messages for expected structure before processing
- **Rate Limiting**: Respect Telegram API rate limits (30 messages/second per bot, 20 edits/minute per message)
- **Error Message Sanitization**: Never expose internal error details, stack traces, or service names to users

**Source**: Architecture Plan - Secrets Management via environment variables; Security Architecture; User requirement for friends/relatives-only access

### Reliability/Availability

- **Target Uptime**: 99%+ uptime aligned with PRD success metrics
- **Graceful Degradation**: Continue accepting messages even if backend is temporarily unavailable (queue locally or inform user)
- **Retry Logic**: Exponential backoff for transient errors (1s, 2s, 4s waits, max 3 retries)
- **Connection Recovery**: Automatic reconnection to Telegram API if polling connection drops
- **Health Checks**: Docker health check every 30 seconds via internal health endpoint
- **Restart Policy**: Automatic restart on failure (unless-stopped)
- **Failover**: If backend unavailable, inform user and suggest retry rather than silently failing

**Source**: PRD - 99%+ uptime; Architecture Plan - Error Handling Strategy

### Observability

- **Structured Logging**: JSON format with service="telegram-bot", log_level, timestamp, user_id, conversation_id, message
- **Log Levels**: DEBUG (development), INFO (production), WARNING (degraded performance), ERROR (failures), CRITICAL (service down)
- **Required Signals**:
  - Message received events: `{"event":"message_received","user_id":...,"message_length":...}`
  - Backend API calls: `{"event":"backend_call","endpoint":...,"duration_ms":...,"status_code":...}`
  - Streaming events: `{"event":"stream_token","conversation_id":...,"token_count":...}`
  - Error events: `{"event":"error","error_type":...,"retry_attempt":...,"user_notified":...}`
  - Performance metrics: `{"event":"performance","metric":"first_token_latency","value_ms":...}`
- **Metrics to Track**: Messages per minute, average response time, error rate, active users, backend availability
- **Sensitive Data Masking**: Mask message content in logs, only log first 50 chars for debugging if necessary

**Source**: Architecture Plan - Logging Architecture; Epic 1 Story 1.4 - Structured logging requirements

## Dependencies and Integrations

**Internal Dependencies:**

| Dependency | Version/Constraint | Purpose | Integration Point |
|------------|-------------------|---------|-------------------|
| Backend API | Epic 2 complete | Message processing, LLM responses | HTTP endpoints: /api/chat, /api/stream, /health |
| Redis | 7.2+ (via Backend) | Session state management | Indirect (Backend manages) |
| Docker Network | annie-network | Service discovery | DNS name resolution: `backend:8000` |
| Structured Logging | Epic 1 complete | Consistent log format | Shared logging module |

**External Dependencies:**

| Dependency | Version/Constraint | Purpose | Integration Point |
|------------|-------------------|---------|-------------------|
| python-telegram-bot | 20.7+ | Telegram Bot API client | `telegram.ext.Application`, `telegram.Bot` |
| Telegram Bot API | Latest | Message reception/sending | HTTPS API: `api.telegram.org/bot{token}/` |
| aiohttp | 3.9+ | Async HTTP client for backend | Backend API calls, SSE streaming |
| python-dotenv | 1.0+ | Environment variable loading | .env file parsing |

**Configuration Dependencies:**

- `TELEGRAM_BOT_TOKEN`: Required, from BotFather registration
- `AUTHORIZED_USER_IDS`: Required, comma-separated list of authorized Telegram user IDs (e.g., "12345,67890")
- `BACKEND_URL`: Default `http://backend:8000`, Backend API base URL
- `LOG_LEVEL`: Default `INFO`, logging verbosity
- `ENVIRONMENT`: Default `dev`, environment type (dev/staging/prod)
- `POLLING_TIMEOUT`: Default `30`, long polling timeout in seconds
- `MAX_RETRIES`: Default `3`, maximum retry attempts for failed requests
- `THINKING_UPDATE_INTERVAL`: Default `10`, seconds between "still thinking" updates for long reasoning

**Dependency Manifests:**

From `telegram_bot/requirements.txt`:
```
python-telegram-bot==20.7
aiohttp==3.9.1
python-dotenv==1.0.0
pydantic==2.5.0
```

## Acceptance Criteria (Authoritative)

**Story 5.1: Telegram Bot Setup & Message Reception**

- **AC #1**: Given Telegram bot token is configured, when the bot service starts, then it connects to Telegram API successfully and starts polling for updates
- **AC #1.1**: Given AUTHORIZED_USER_IDS is configured, when the bot starts, then the whitelist is loaded into memory for fast authorization checks
- **AC #2**: Given the bot is running and I am an authorized user, when I send a message via Telegram, then the bot receives and processes the message within 1 second
- **AC #2.1**: Given the bot is running and I am NOT an authorized user, when I send a message via Telegram, then the bot responds with "Sorry, you're not authorized to use Annie. Please contact the administrator for access." and does NOT forward to backend
- **AC #3**: Given a message is received from an authorized user, when I check logs, then user_id and message text are extracted correctly (user_id: numeric, message_text: full content, timestamp, message_id) and authorization status is logged
- **AC #4**: Given different message types, when I send text messages, then the bot handles them correctly (after authorization check)
- **AC #5**: Given different message types, when I send voice messages, then the bot handles them appropriately (V1: return "Voice messages coming soon" or transcribe)
- **AC #6**: Given the bot receives a message from an authorized user, when I check processing, then it forwards the message to backend API (POST /api/chat) with proper formatting
- **AC #7**: Given the bot, when I check error handling, then connection failures are handled gracefully with retry logic and logging
- **AC #7.1**: Given unauthorized access attempts, when I check logs, then unauthorized user_ids are logged for security monitoring without exposing sensitive data

**Story 5.2: Streaming Response Delivery**

- **AC #1**: Given an authorized user sends a message, when Annie responds, then responses stream incrementally to Telegram (tokens appear as they're generated)
- **AC #1.1**: Given Annie is using a thinking model (Grok-4, ChatGPT-5), when processing begins, then user immediately sees "Annie is thinking deeply about your question..." message
- **AC #1.2**: Given LLM reasoning takes >10 seconds, when no tokens have arrived, then the message updates to "Still thinking... (complex reasoning takes time)" and updates every 10 seconds until tokens arrive
- **AC #2**: Given streaming responses, when tokens start arriving, then I see tokens appearing in real-time (not all at once), with updates every 100-500ms
- **AC #3**: Given a long response (>4096 chars), when Annie responds, then messages are split appropriately for Telegram (max 4096 chars per message) with proper message continuation
- **AC #4**: Given streaming, when Annie is processing, then a typing indicator is shown in Telegram (`send_chat_action(chat_id, "typing")`)
- **AC #5**: Given streaming completes, when I check the conversation, then the complete response is visible as a single coherent message (or properly split messages), replacing the "thinking" placeholder
- **AC #6**: Given streaming fails, when an error occurs, then the user receives a clear error message: "I encountered an issue generating a response. Please try again."
- **AC #7**: Given streaming with thinking models, when I check performance, then "thinking" message appears within 2 seconds, and first token appears within 30 seconds (accounting for LLM reasoning time)

**Story 5.3: Message Formatting & Error Handling**

- **AC #1**: Given Annie responds, when messages are sent, then markdown formatting is properly rendered in Telegram (bold, italic, code, links)
- **AC #2**: Given tool results (stock data, search results), when Annie responds, then results are formatted clearly with structure (tables, numbered lists)
- **AC #3**: Given an error occurs, when the backend fails, then the user receives a user-friendly error message (not technical error details)
- **AC #4**: Given service failures, when agentic-memories is down, then the user is informed ("Note: I'm having trouble accessing your memory, but I can still help.") and conversation continues
- **AC #5**: Given retry scenarios, when a transient error occurs (network timeout, rate limit), then the bot suggests retrying: "Please try again in a few seconds."
- **AC #6**: Given error messages, when I check the format, then they're clear, actionable, and not technical jargon
- **AC #7**: Given message formatting, when I check edge cases, then empty responses are handled gracefully, very long responses are split properly, special characters are escaped correctly, and emojis render properly

## Traceability Mapping

| AC ID | Spec Section | Component/API | Test Idea |
|-------|--------------|---------------|-----------|
| 5.1-AC#1 | Detailed Design - TelegramBotService | bot.py, Telegram API getUpdates | Integration test: Start bot, verify polling active within 5s |
| 5.1-AC#1.1 | Security - User Authorization | AuthenticationModule.load_whitelist | Unit test: Verify whitelist loaded on startup, <50ms lookup |
| 5.1-AC#2 | Performance - Authentication Check | MessageHandler, AuthenticationModule | Performance test: Authorized message, receipt <1s |
| 5.1-AC#2.1 | Security - Authorization Rejection | AuthenticationModule.check_user | Integration test: Unauthorized user_id, verify rejection message |
| 5.1-AC#3 | Data Models - User Message Model | MessageHandler.extract_message | Unit test: Parse Telegram update, assert all fields + auth status |
| 5.1-AC#4 | Workflows - Message Processing | MessageHandler.handle_text | Integration test: Send text message, verify forwarded to backend |
| 5.1-AC#5 | Workflows - Message Processing | MessageHandler.handle_voice | Unit test: Send voice message, assert "Voice messages coming soon" |
| 5.1-AC#6 | APIs - POST /api/chat | BackendClient.send_message | Integration test: Mock backend, verify correct request format |
| 5.1-AC#7 | Error Handling - Error Handling Sequence | ErrorHandler, retry logic | Chaos test: Kill backend, verify retry with exponential backoff |
| 5.1-AC#7.1 | Security - Unauthorized Logging | AuthenticationModule, logging | Security test: Unauthorized attempt, verify logged without PII |
| 5.2-AC#1 | Workflows - Streaming Update Flow | StreamingHandler.poll_sse | Integration test: Mock SSE stream, verify incremental updates |
| 5.2-AC#1.1 | Performance - Thinking Indicator | StreamingHandler.send_thinking | Integration test: Verify "thinking" message sent within 2s |
| 5.2-AC#1.2 | Performance - Thinking Updates | StreamingHandler.update_thinking | Performance test: No tokens for 15s, verify "still thinking" updates |
| 5.2-AC#2 | Performance - Streaming Update Frequency | StreamingHandler.update_message | Performance test: Measure update intervals 100-500ms |
| 5.2-AC#3 | Workflows - Message splitting | FormattingModule.split_message | Unit test: 5000 char response, assert 2 messages sent |
| 5.2-AC#4 | APIs - sendChatAction | StreamingHandler.send_typing | Integration test: Verify typing indicator sent before streaming |
| 5.2-AC#5 | Workflows - Streaming completion | StreamingHandler.finalize | Integration test: Verify final message matches complete response |
| 5.2-AC#6 | Error Handling - SSE stream errors | StreamingHandler.handle_error | Unit test: Mock SSE error, assert user-friendly message sent |
| 5.2-AC#7 | Performance - Thinking Model Latency | End-to-end flow | Performance test: User message → "thinking" <2s, first token <30s |
| 5.3-AC#1 | Data Models - Telegram Response | FormattingModule.format_markdown | Unit test: Markdown text, verify Telegram parse_mode rendering |
| 5.3-AC#2 | Workflows - Tool result formatting | FormattingModule.format_tool_results | Integration test: Stock data response, verify table formatting |
| 5.3-AC#3 | Error Handling - User-friendly errors | ErrorHandler.sanitize_error | Unit test: Backend 500 error, assert generic user message |
| 5.3-AC#4 | Error Handling - Service degradation | ErrorHandler.handle_service_down | Integration test: Mock memory service down, verify informative message |
| 5.3-AC#5 | Reliability - Retry Logic | ErrorHandler.retry_transient | Unit test: Network timeout, verify "retry in a few seconds" message |
| 5.3-AC#6 | Observability - User-facing messages | ErrorHandler.format_error | Manual test: Review error messages for clarity, no jargon |
| 5.3-AC#7 | Data Models - Edge cases | FormattingModule edge case handlers | Unit test suite: Empty response, 10k chars, special chars, emojis |

## Risks, Assumptions, Open Questions

**Risks:**

- **Risk**: User ID whitelist management becomes cumbersome as user base grows
  - **Mitigation**: Phase 1 uses environment variable for simplicity; Phase 2 can migrate to database-backed user management with admin interface
  - **Severity**: Low (V1 targets friends/relatives only, small user base expected)

- **Risk**: Thinking models (10-30s latency) may frustrate users expecting instant responses
  - **Mitigation**: Clear "thinking" indicators with periodic updates; educate users that deep reasoning takes time; consider fast-mode toggle in future
  - **Severity**: Medium

- **Risk**: Telegram API rate limiting (20 message edits/minute) may limit streaming update frequency for very active users
  - **Mitigation**: Implement smart batching of token updates, only edit message when sufficient new content accumulated (50+ tokens or 500ms)
  - **Severity**: Medium

- **Risk**: Backend API downtime causes poor user experience if not handled gracefully
  - **Mitigation**: Implement circuit breaker pattern; after 3 consecutive failures, wait 5 minutes before retrying; inform user of degraded service
  - **Severity**: High

- **Risk**: Long polling connection drops may cause message delivery delays
  - **Mitigation**: Implement connection monitoring and automatic reconnection with exponential backoff
  - **Severity**: Low

- **Risk**: SSE stream disconnections during long responses may result in incomplete messages
  - **Mitigation**: Implement SSE reconnection with Last-Event-ID, Backend API resume capability
  - **Severity**: Medium

**Assumptions:**

- **Assumption**: Backend API is ready and operational (Epic 2 complete) before Epic 5 implementation begins
  - **Validation**: Confirm Epic 2 stories 2.1, 2.3 marked "done" in sprint-status.yaml

- **Assumption**: Telegram Bot Token is available from BotFather before development starts
  - **Validation**: Token obtained and added to .env file, verified via test API call

- **Assumption**: Authorized user IDs are known before deployment and won't change frequently
  - **Validation**: Collect Telegram user IDs from friends/relatives; update AUTHORIZED_USER_IDS in .env

- **Assumption**: Users understand thinking models require time; willing to wait 10-30s for deep reasoning
  - **Validation**: User feedback post-launch; consider adding fast-mode if users prefer speed over depth

- **Assumption**: 100 concurrent users is sufficient for V1 MVP; scaling beyond this is post-V1 optimization
  - **Validation**: Monitor user growth metrics; plan horizontal scaling if approaching capacity

- **Assumption**: Voice message transcription is not critical for V1; can be deferred or return placeholder message
  - **Validation**: User feedback post-launch; prioritize if heavily requested

**Open Questions:**

- **Question**: Should user authorization be moved to Backend API instead of Telegram bot service?
  - **Impact**: Centralizes auth logic but adds latency; bot-level auth fails fast and saves backend resources
  - **Decision Needed By**: Before Story 5.1 implementation
  - **Recommendation**: Keep bot-level auth for V1 (fail-fast), consider centralized auth in V1.1 if user management becomes complex

- **Question**: Should we implement webhook-based message reception instead of long polling for production?
  - **Impact**: Webhooks reduce latency and API calls but require HTTPS endpoint and webhook setup
  - **Decision Needed By**: Before production deployment
  - **Recommendation**: Start with long polling for V1 simplicity, migrate to webhooks in V1.1 optimization

- **Question**: How should we handle Telegram-specific features like inline keyboards for decision options (e.g., "Buy/Hold/Sell" buttons)?
  - **Impact**: Enhances UX but increases complexity
  - **Decision Needed By**: Before Story 5.3 implementation
  - **Recommendation**: Defer to V1.1 for advanced UX features; V1 focuses on text-only interaction

- **Question**: What is the expected behavior if a user sends multiple messages rapidly before Annie responds?
  - **Impact**: Could create race conditions or multiple concurrent conversations
  - **Decision Needed By**: Before Story 5.1 implementation
  - **Recommendation**: Queue messages, process sequentially; inform user "Processing your previous message, one moment..."

## Test Strategy Summary

**Test Levels:**

1. **Unit Tests** (80%+ coverage target):
   - MessageHandler: Message extraction, validation, type detection
   - FormattingModule: Markdown formatting, message splitting, edge cases (empty, long, special chars)
   - ErrorHandler: Error classification, user message generation, retry logic
   - BackendClient: HTTP request formatting, response parsing, timeout handling

2. **Integration Tests**:
   - Telegram Bot → Backend API: Message forwarding, response handling
   - SSE Stream handling: Token accumulation, message updates, completion
   - End-to-end message flow: User message → Backend → Streaming → User response
   - Health check integration: Verify bot service health endpoint

3. **Performance Tests**:
   - First message latency: User sends message → first token appears <2s (p95)
   - Streaming update frequency: Measure update intervals 100-500ms
   - Concurrent users: 100 concurrent conversations without degradation
   - Backend API call latency: <500ms (p95)

4. **Error Scenario Tests**:
   - Backend unavailable: Verify graceful degradation, user-friendly error
   - Network timeout: Verify retry logic with exponential backoff
   - SSE stream disconnection: Verify reconnection and message completion
   - Telegram API rate limit: Verify backoff and queue handling
   - Invalid message types: Voice, image, video → appropriate handling

5. **Edge Case Tests**:
   - Empty responses from backend
   - Very long responses (>10k chars) → proper splitting
   - Special characters and emojis → correct rendering
   - Rapid message sending → queuing and sequential processing
   - Markdown injection attempts → proper escaping

**Test Frameworks:**
- **pytest**: Unit and integration tests
- **pytest-asyncio**: Async test support
- **unittest.mock**: Mocking Telegram API and Backend API
- **locust** or **k6**: Performance and load testing

**Coverage Targets:**
- Unit tests: 80%+ code coverage
- Integration tests: All AC scenarios covered
- Performance tests: All NFR metrics validated (latency, throughput, concurrency)
- Error scenarios: All error types in Error Handling Strategy section tested
