# Story 5.3: Message Formatting & Error Handling

Status: drafted

## Story

As a **user**,
I want **clearly formatted messages and helpful error messages**,
so that **I understand Annie's responses and know what to do if something goes wrong**.

## Acceptance Criteria

**AC #1:** Given Annie responds, when messages are sent, then markdown formatting is properly rendered in Telegram:
  - **Bold** text renders correctly
  - *Italic* text renders correctly
  - `Code` blocks render correctly
  - Links render as clickable

**AC #2:** Given tool results (stock data, search results), when Annie responds, then results are formatted clearly with structure:
  - Stock data: Tables or structured text
  - Search results: Numbered list with titles and URLs
  - Memory references: Clear attribution

**AC #3:** Given an error occurs, when the backend fails, then the user receives a user-friendly error message: "I'm having trouble right now. Please try again in a moment." (not technical error details)

**AC #4:** Given service failures, when agentic-memories is down, then the user is informed: "Note: I'm having trouble accessing your memory, but I can still help." and conversation continues

**AC #5:** Given retry scenarios, when a transient error occurs (network timeout, rate limit), then the bot suggests retrying: "Please try again in a few seconds."

**AC #6:** Given error messages, when I check the format, then they're clear, actionable, and not technical jargon

**AC #7:** Given message formatting, when I check edge cases, then:
  - Empty responses are handled gracefully
  - Very long responses are split properly
  - Special characters are escaped correctly
  - Emojis render properly

## Tasks / Subtasks

- [ ] Task 1: Implement markdown formatting in Telegram responses (AC: #1)
  - [ ] Configure python-telegram-bot to parse markdown (ParseMode.MARKDOWN_V2)
  - [ ] Test bold, italic, code, and link rendering
  - [ ] Handle markdown escaping for special characters

- [ ] Task 2: Format structured tool results (AC: #2)
  - [ ] Create formatters for stock data (tables/structured text)
  - [ ] Create formatters for search results (numbered lists with titles/URLs)
  - [ ] Create formatters for memory references (clear attribution)
  - [ ] Add formatting logic in message handling

- [ ] Task 3: Implement user-friendly error messages (AC: #3, #6)
  - [ ] Map backend errors to user-friendly messages
  - [ ] Replace technical error details with simple messages
  - [ ] Add error message constants/templates
  - [ ] Test error handling paths

- [ ] Task 4: Handle service-specific failures (AC: #4)
  - [ ] Detect agentic-memories failures specifically
  - [ ] Show degraded functionality message
  - [ ] Allow conversation to continue without memory
  - [ ] Log service failures for monitoring

- [ ] Task 5: Implement retry guidance (AC: #5)
  - [ ] Detect transient errors (timeout, rate limit)
  - [ ] Suggest retry with appropriate message
  - [ ] Add retry-after timing hints if available

- [ ] Task 6: Handle message edge cases (AC: #7)
  - [ ] Handle empty LLM responses gracefully
  - [ ] Implement message splitting for long responses (Telegram 4096 char limit)
  - [ ] Escape markdown special characters properly
  - [ ] Test emoji rendering

## Dev Notes

### Architecture Context

**Telegram Bot Service** (from ARCHITECTURE_PLAN.md):
- Technology: python-telegram-bot
- Features: Long polling, message splitting for long responses, error handling and retries
- Responsible for: Streaming responses to users, handling Telegram-specific features

**Error Handling Patterns**:
- Backend errors should be caught and translated to user-friendly messages
- Service failures (agentic-memories down) should allow degraded operation
- Transient errors should suggest retry

**Message Flow**:
1. Backend API generates response (text/streaming)
2. Telegram Bot receives response
3. Bot formats message (markdown, structure)
4. Bot sends to user via Telegram API

### Affected Components

**Files to Modify**:
- `telegram_bot/bot.py` - Message formatting and error handling logic
- `telegram_bot/backend_client.py` - Error detection and mapping
- `telegram_bot/formatters.py` (NEW) - Tool result formatting utilities

**Telegram API Considerations**:
- Message limit: 4096 characters
- ParseMode.MARKDOWN_V2 requires escaping: `_`, `*`, `[`, `]`, `(`, `)`, `~`, `` ` ``, `>`, `#`, `+`, `-`, `=`, `|`, `{`, `}`, `.`, `!`
- Long messages must be split intelligently (preserve formatting, don't break mid-word)

### Implementation Strategy

1. **Markdown Formatting**:
   - Enable ParseMode.MARKDOWN_V2 in telegram bot
   - Create escape_markdown() utility function
   - Test with various formatting combinations

2. **Tool Result Formatting**:
   - Create formatter classes/functions for each tool type
   - Stock data → use simple table format or bullet points
   - Search results → numbered list with `[Title](URL)` format
   - Memory references → "Based on our conversation on [date]..."

3. **Error Message Mapping**:
   ```python
   ERROR_MESSAGES = {
       "backend_error": "I'm having trouble right now. Please try again in a moment.",
       "memory_service_down": "Note: I'm having trouble accessing your memory, but I can still help.",
       "rate_limit": "Please try again in a few seconds.",
       "timeout": "The request took too long. Please try again.",
       "unknown": "Something went wrong. Please try again later."
   }
   ```

4. **Message Splitting**:
   - Check message length before sending
   - If > 4096 chars, split at sentence/paragraph boundaries
   - Preserve markdown formatting across splits
   - Send as multiple messages in sequence

### Testing Approach

- Unit tests for formatters (stock, search, memory)
- Unit tests for markdown escaping
- Integration tests for error scenarios
- Manual testing with real Telegram client for formatting verification

### Learnings from Previous Story

**From Story 2.7 (Status: done)**

- **Configuration Pattern**: Used `get_config()` from config modules with fallback defaults
- **Logging**: Added startup logging showing configuration values - apply similar pattern for formatter initialization
- **Backward Compatibility**: Ensured changes don't break existing functionality - important for error handling changes
- **Type Conversions**: Used appropriate type conversions (float vs int) - relevant for message length checks

[Source: stories/2-7-move-timeout-configuration-to-environment-variables-technical-debt.md#Dev-Agent-Record]

### Project Structure Notes

- Telegram bot code located in `telegram_bot/` directory
- Configuration loaded via `telegram_bot/config.py`
- Logging via `telegram_bot/logger.py`
- Backend client at `telegram_bot/backend_client.py`
- Main bot logic in `telegram_bot/bot.py`

### References

- [Source: docs/epics-and-stories.md#Story-5.3] - Story requirements and acceptance criteria
- [Source: docs/02-architecture/ARCHITECTURE_PLAN.md#Telegram-Bot-Service] - Architecture context for Telegram bot
- [Source: telegram_bot/bot.py] - Current bot implementation
- [Source: telegram_bot/backend_client.py] - Backend client with error handling

## Dev Agent Record

### Context Reference

<!-- Path(s) to story context XML will be added here by context workflow -->

### Agent Model Used

<!-- Will be filled by dev agent -->

### Debug Log References

<!-- Will be filled by dev agent during implementation -->

### Completion Notes List

<!-- Will be filled by dev agent after implementation -->

### File List

<!-- Will be filled by dev agent with NEW/MODIFIED/DELETED markers -->
