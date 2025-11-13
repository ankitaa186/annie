# ADR: Channel-Aware Message Formatting via System Prompts

**Status:** Proposed
**Date:** 2025-11-13
**Authors:** John (PM), Winston (Architect)
**Decision Makers:** Ankit
**Related Story:** 5.3 - Message Formatting & Error Handling

---

## Context

Annie's backend API serves multiple client platforms (Telegram bot, potential future web/mobile clients). Different platforms have different message formatting requirements:

- **Telegram**: Requires MarkdownV2 syntax with specific escaping rules
- **Web/Mobile**: May require HTML, plain text, or other formats in the future
- **API**: May require JSON or unformatted responses

**Problem Statement:**
How should we handle platform-specific message formatting when LLM responses are unpredictable and we want to maintain a channel-agnostic backend architecture?

**Initial Considerations:**

Two approaches were evaluated:

1. **Post-Processing Pipeline**: Backend receives raw LLM output, applies platform-specific formatters, sanitizers, and chunkers before sending to client
2. **System Prompt Instructions**: LLM is instructed via system prompt to format responses appropriately for the target platform

---

## Decision

**We will use platform-specific system prompts to instruct the LLM to format responses appropriately, with a lightweight fallback mechanism for error handling.**

The backend will:
1. Accept a `platform` field in chat requests (e.g., `"telegram"`, `"web"`, `"api"`)
2. Build system prompts dynamically based on the platform
3. Instruct the LLM to format responses according to platform requirements
4. Implement a simple fallback to plain text if formatting fails

---

## Rationale

### Why System Prompts (Chosen Approach)

**Advantages:**
- **Simplicity**: Minimal code complexity - no complex formatter/sanitizer/chunker pipeline
- **Maintainability**: One place to define formatting rules (system prompt)
- **LLM Capability**: Modern LLMs (Grok-4, ChatGPT-5) reliably follow formatting instructions
- **Token Cost**: Negligible - approximately 50-100 tokens per request (~$0.0001-0.0002)
- **Channel-Agnostic**: Backend remains platform-agnostic; formatting is declarative
- **Extensibility**: Easy to add new platforms by extending prompt builder
- **Natural Output**: LLM formats as it generates, no post-processing delays

**Disadvantages:**
- **Non-Deterministic**: LLM might occasionally fail to follow formatting rules
- **Token Overhead**: Small additional cost per request (acceptable trade-off)
- **Testing Complexity**: Requires testing with real LLM outputs, not just unit tests

**Mitigation:**
- Implement fallback to plain text if Telegram API rejects formatted message
- Test with 50-100 real messages to validate 95%+ success rate
- Log formatting failures for monitoring

### Why Not Post-Processing Pipeline

**Disadvantages:**
- **High Complexity**: Requires formatter, sanitizer, chunker, and escape logic modules
- **Maintenance Burden**: More code = more bugs, especially with edge cases
- **Over-Engineering**: Solves problems we don't have (LLM formatting is reliable enough)
- **Development Time**: 4-6 hours vs 1-2 hours for system prompt approach
- **Testing Burden**: More unit tests, integration tests, chaos tests required

**Advantages (Not Compelling Enough):**
- **Deterministic**: Guaranteed formatting correctness
- **Zero Token Cost**: No additional LLM tokens

**Conclusion:** The complexity cost outweighs the reliability benefit, especially given modern LLM capability.

---

## Implementation

### Architecture Pattern

```
Client Request (platform="telegram")
        ↓
Backend API: Build System Prompt
        ↓
[Base Prompt] + [Telegram Formatting Instructions]
        ↓
LLM Client: Generate Response
        ↓
Telegram Bot: Send with parse_mode='MarkdownV2'
        ↓
Fallback: If formatting fails → Send as plain text
```

### Technical Components

#### 1. System Prompt Builder (`backend/api/prompts.py`)

```python
"""System prompts for different platforms."""

BASE_SYSTEM_PROMPT = """You are Annie, a helpful AI companion focused on decision-making support.
Provide thoughtful, personalized advice based on user context and preferences."""

TELEGRAM_FORMAT_INSTRUCTIONS = """
Format your responses using Telegram MarkdownV2 syntax:
- Use *bold* for emphasis
- Use _italic_ for secondary emphasis
- Use `code` for inline code
- Use ```language\\ncode\\n``` for code blocks
- Escape special characters (\\_ \\* \\[ \\] \\( \\) \\~ \\` \\> \\# \\+ \\- \\= \\| \\{ \\} \\. \\!) outside formatting tags

Keep responses clear, well-structured, and easy to read on mobile.
"""

def build_system_prompt(platform: str) -> str:
    """
    Build system prompt based on client platform.

    Args:
        platform: Client platform identifier ("telegram", "web", "api", etc.)

    Returns:
        System prompt string with platform-specific formatting instructions
    """
    prompt = BASE_SYSTEM_PROMPT

    if platform == "telegram":
        prompt += "\n\n" + TELEGRAM_FORMAT_INSTRUCTIONS
    # Future platforms can be added here:
    # elif platform == "web":
    #     prompt += WEB_FORMAT_INSTRUCTIONS

    return prompt
```

#### 2. Stream Generator Update (`backend/api/routes/stream.py`)

```python
async def stream_generator(
    conversation_id: str,
    messages: List[Dict[str, Any]],
    request: Request,
    platform: str = "api",  # NEW PARAMETER
    state_manager: Optional[StateManager] = None
) -> AsyncGenerator[Dict[str, Any], None]:
    """Generate SSE events with platform-aware system prompt."""

    from api.prompts import build_system_prompt

    # Build platform-specific system prompt
    system_message = {
        "role": "system",
        "content": build_system_prompt(platform)
    }

    # Prepend system message to conversation
    conversation_messages = [system_message] + messages.copy()

    # Continue with existing logic...
```

#### 3. Chat Route Update (`backend/api/routes/chat.py`)

```python
@router.post("/chat", response_model=ChatResponse)
async def handle_chat(request: ChatRequest, background_tasks: BackgroundTasks):
    """Handle chat request and store platform in metadata."""

    # Store platform in conversation metadata for stream route
    await state.set_conversation_metadata(
        conversation_id,
        {
            "platform": request.platform,  # Store for later retrieval
            "user_id": request.user_id,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
    )
```

#### 4. Stream Route Update (`backend/api/routes/stream.py`)

```python
@router.get("/stream/{conversation_id}")
async def stream_response(conversation_id: str, request: Request):
    """Stream LLM response with platform-specific formatting."""

    # Retrieve platform from conversation metadata
    metadata = await state.get_conversation_metadata(conversation_id)
    platform = metadata.get("platform", "api")  # Default to "api"

    # Pass platform to stream generator
    return EventSourceResponse(
        stream_generator(
            conversation_id,
            messages,
            request,
            platform=platform,  # Platform-aware streaming
            state_manager=state
        )
    )
```

#### 5. Telegram Bot Update (`telegram_bot/backend_client.py`)

```python
async def send_message(
    self,
    user_id: int,
    message: str,
    message_type: str = "text"
) -> dict:
    """Send message to backend with platform identifier."""
    response = await self.client.post(
        f"{self.backend_url}/api/chat",
        json={
            "user_id": str(user_id),
            "platform": "telegram",  # Identify as Telegram client
            "message": message,
            "context": {"message_type": message_type}
        },
        timeout=self.request_timeout
    )
    return response.json()
```

#### 6. Telegram Handler Update (`telegram_bot/handlers/message.py`)

```python
# Update all message sending calls to use MarkdownV2
await message.reply_text(current_text, parse_mode='MarkdownV2')

# Add fallback for formatting failures
try:
    await message.reply_text(current_text, parse_mode='MarkdownV2')
except TelegramError as e:
    logger.warning(
        "Markdown formatting failed, falling back to plain text",
        extra={
            "user_id": user_id,
            "error": str(e),
            "event": "markdown_fallback"
        }
    )
    # Fallback to plain text
    await message.reply_text(current_text)
```

---

## Consequences

### Positive

1. **Minimal Code Changes**: ~100 lines of new code vs ~500+ for post-processing pipeline
2. **Fast Implementation**: 1-2 hours vs 4-6 hours
3. **Easy Testing**: Test with real LLM outputs, measure success rate
4. **Future-Proof**: Easy to extend for web, mobile, API clients
5. **Maintainable**: Single source of truth for formatting rules
6. **No Performance Impact**: System prompt overhead is negligible

### Negative

1. **LLM Dependency**: Relies on LLM following instructions correctly
2. **Token Cost**: Small ongoing cost (~$0.0001-0.0002 per message)
3. **Non-Deterministic**: Small chance of formatting failures

### Neutral

1. **Monitoring Required**: Need to track formatting failure rate
2. **Prompt Engineering**: May need to refine instructions based on real-world usage

---

## Validation

### Success Criteria

1. **Formatting Success Rate**: ≥95% of messages render correctly in Telegram
2. **Fallback Coverage**: 100% of formatting failures gracefully degrade to plain text
3. **User Experience**: No visible errors or broken formatting reported by users
4. **Performance**: No measurable impact on response latency

### Testing Strategy

1. **LLM Output Testing**: Collect 100 real LLM responses, validate Telegram accepts them
2. **Edge Case Testing**: Test with code blocks, special characters, long messages, emojis
3. **Fallback Testing**: Simulate formatting failures, verify plain text fallback works
4. **Integration Testing**: End-to-end test with real Telegram bot and backend

### Monitoring

Track in production logs:
- `event: "markdown_success"` - Message rendered successfully
- `event: "markdown_fallback"` - Fallback to plain text triggered
- Success rate metric: `markdown_success / (markdown_success + markdown_fallback)`

Alert if success rate drops below 90%.

---

## Alternatives Considered

### Alternative 1: Post-Processing Pipeline (Rejected)

**Description:** Build formatter/sanitizer/chunker modules in backend to process LLM output before sending to Telegram.

**Pros:**
- Deterministic formatting
- Zero additional token cost
- Full control over output

**Cons:**
- High implementation complexity (~500 lines of code)
- Maintenance burden (escape logic, edge cases)
- Over-engineered for the problem
- 3-4x longer development time

**Why Rejected:** Complexity outweighs benefits. Modern LLMs are reliable enough.

### Alternative 2: Client-Side Formatting (Rejected)

**Description:** Telegram bot receives raw LLM output and applies formatting locally.

**Pros:**
- Backend remains completely agnostic
- Zero backend changes

**Cons:**
- Duplicates formatting logic across clients (Telegram, future web/mobile)
- Telegram bot becomes more complex
- Breaks separation of concerns (bot should be thin client)

**Why Rejected:** Violates architecture principle of thin clients. Backend should own business logic.

### Alternative 3: Hybrid Approach (Considered but not chosen)

**Description:** Use system prompts for formatting, but add lightweight sanitizer as safety net.

**Pros:**
- Best of both worlds
- Higher reliability

**Cons:**
- Still adds code complexity (though less than full pipeline)
- May not be needed if LLM success rate is high enough

**Decision:** Start with pure system prompt approach. Add sanitizer only if production data shows formatting failures >5%.

---

## Future Extensions

### Multi-Platform Support

When adding new platforms, extend `build_system_prompt()`:

```python
def build_system_prompt(platform: str) -> str:
    prompt = BASE_SYSTEM_PROMPT

    if platform == "telegram":
        prompt += TELEGRAM_FORMAT_INSTRUCTIONS
    elif platform == "web":
        prompt += WEB_FORMAT_INSTRUCTIONS  # HTML/Rich Text
    elif platform == "mobile":
        prompt += MOBILE_FORMAT_INSTRUCTIONS  # Concise responses
    # "api" or unknown platforms get no special formatting

    return prompt
```

### A/B Testing

Platform-specific prompts enable easy A/B testing:

```python
TELEGRAM_FORMAT_V1 = "..."  # Current instructions
TELEGRAM_FORMAT_V2 = "..."  # Experimental variation

def build_system_prompt(platform: str, variant: str = "v1") -> str:
    if platform == "telegram":
        if variant == "v2":
            prompt += TELEGRAM_FORMAT_V2
        else:
            prompt += TELEGRAM_FORMAT_V1
```

### Dynamic Prompt Loading

For advanced use cases, prompts could be loaded from database or config files for runtime updates without deployment.

---

## References

- **Story 5.3**: Message Formatting & Error Handling
- **Telegram MarkdownV2 Spec**: https://core.telegram.org/bots/api#markdownv2-style
- **ChatRequest Model**: `backend/api/routes/chat.py:184`
- **Stream Generator**: `backend/api/routes/stream.py:33`

---

## Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2025-11-13 | Use system prompts for platform-specific formatting | Simplicity, maintainability, and LLM reliability outweigh determinism benefits of post-processing |
| 2025-11-13 | Implement lightweight fallback to plain text | Mitigates risk of formatting failures without complex pipeline |
| 2025-11-13 | Store platform in conversation metadata | Enables stream route to access platform without passing through request chain |

---

**Next Steps:**

1. Implement `backend/api/prompts.py` with system prompt builder
2. Update stream generator to accept and use platform parameter
3. Update chat/stream routes to store and retrieve platform
4. Update Telegram bot to pass `platform="telegram"` and use `parse_mode='MarkdownV2'`
5. Test with 50-100 real messages to validate approach
6. Monitor formatting success rate in production
7. Consider adding sanitizer if success rate < 95%
