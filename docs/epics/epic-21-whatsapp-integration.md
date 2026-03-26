# annie - Epic 21: Annie on WhatsApp

**Author:** Ankit
**Date:** 2026-03-05
**Project Level:** Level 3-4
**Target Scale:** V1.0 Extension

---

## Overview

Enable Annie to communicate via WhatsApp with a platform-adapted user experience, using Twilio as the messaging gateway. Annie shares the same backend brain and memory across platforms, with responses adapted to WhatsApp conventions (shorter messages, native formatting, no streaming). Includes media handling, voice note transcription, and cross-platform identity linking.

**Stories:**

| # | Story | Description |
|---|-------|-------------|
| 21.1 | WhatsApp Gateway Setup | Twilio integration, webhook endpoint, `whatsapp_bot/` service |
| 21.2 | Inbound/Outbound Message Handling | Receive messages via webhook, call `/api/chat`, send responses |
| 21.3 | Response Adaptation & Message Chunking | Format responses for WhatsApp — shorter, chunked, native formatting |
| 21.4 | Media File Support | Handle inbound images, documents — map to file attachment flow |
| 21.5 | Typing Indicators & UX Polish | Typing indicators, error messages, delivery feedback |
| 21.6 | Cross-Platform Identity Linking | Link WhatsApp user to Telegram user via phone number matching |
| 21.7 | Voice Note Transcription | Speech-to-text for inbound WhatsApp voice notes |

**Dependency Chain:** 21.1 -> 21.2 -> (21.3, 21.4, 21.5, 21.6 in parallel) -> 21.7 (depends on 21.4)

---

## Epic 21: Annie on WhatsApp

**Goal:** Enable Annie to be accessible via WhatsApp with a native, platform-adapted experience while sharing the same backend intelligence, memory, and tools across all messaging platforms.

---

### Story 21.1: WhatsApp Gateway Setup (Twilio)

**As a** developer,
**I want** a WhatsApp messaging gateway using Twilio,
**So that** Annie can send and receive WhatsApp messages through a reliable, managed service.

**Acceptance Criteria:**

**Given** Twilio account credentials and WhatsApp sandbox/number are configured in `.env`
**When** the `whatsapp_bot/` service starts
**Then** it registers a webhook endpoint with Twilio and is ready to receive inbound messages

**And** the service exposes a health check endpoint at `/health`
**And** Twilio webhook signature validation is enabled for security
**And** the service is added to `docker-compose.yaml` with proper dependency ordering (after backend)
**And** environment variables `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and `TWILIO_WHATSAPP_NUMBER` are validated on startup

**Prerequisites:** None (foundation story)

**Technical Notes:**
- Create `whatsapp_bot/` service directory mirroring `telegram_bot/` structure
- Use FastAPI for the webhook server (consistent with backend)
- Twilio WhatsApp API uses webhooks (POST) for inbound messages, REST API for outbound
- Implement Twilio request signature validation using `twilio` Python SDK
- Add `twilio>=9.0.0` to requirements.txt
- Docker service: `whatsapp-bot`, port 8004, depends on backend
- Add to Makefile targets (logs, shell, health)

---

### Story 21.2: Inbound/Outbound Message Handling

**As a** WhatsApp user,
**I want** to send a text message to Annie on WhatsApp and receive a response,
**So that** I can have a conversation with Annie from my preferred messaging platform.

**Acceptance Criteria:**

**Given** the WhatsApp gateway service is running and webhook is registered
**When** a user sends a text message to Annie's WhatsApp number
**Then** the message is received via Twilio webhook, the user is identified by phone number, and the message is forwarded to `POST /api/chat`

**And** when the backend processes the message and returns a response
**Then** the full response is sent back to the user via Twilio's Messages API

**And** the `user_id` format is `whatsapp_{phone_number}` (e.g., `whatsapp_+1234567890`)
**And** conversation history is maintained in Redis using the same session mechanism as Telegram
**And** errors are handled gracefully with user-friendly WhatsApp messages

**Prerequisites:** Story 21.1

**Technical Notes:**
- Webhook receives POST with `Body`, `From`, `To`, `MessageSid` fields
- Since WhatsApp doesn't support streaming, call `/api/chat` and wait for the complete response (not SSE streaming)
- May need a new backend endpoint or mode that returns complete response instead of streaming
- Alternatively, consume the SSE stream internally and collect the full response before sending
- Phone number format from Twilio: `whatsapp:+1234567890`
- Use Twilio REST client to send outbound messages
- Handle Twilio delivery status callbacks (optional but recommended)

---

### Story 21.3: Response Adaptation & Message Chunking

**As a** WhatsApp user,
**I want** Annie's responses to feel natural on WhatsApp,
**So that** the conversation feels like chatting with a friend rather than reading a document.

**Acceptance Criteria:**

**Given** Annie generates a response longer than 1,500 characters
**When** the response is sent to WhatsApp
**Then** it is split into multiple messages at natural breakpoints (paragraph boundaries, list boundaries, or sentence endings)

**And** each chunk is sent sequentially with a brief delay (500-1000ms) to simulate natural typing rhythm
**And** markdown headers (`#`, `##`) are converted to bold text with line breaks
**And** bullet points and numbered lists are preserved (WhatsApp renders these natively)
**And** code blocks are converted to monospace formatting using backticks
**And** tables are converted to a readable plain-text format
**And** messages under 1,500 characters are sent as a single message without chunking

**Prerequisites:** Story 21.2

**Technical Notes:**
- Create `whatsapp_bot/formatter.py` for WhatsApp-specific response formatting
- WhatsApp supports: *bold*, _italic_, ~strikethrough~, ```monospace```
- WhatsApp does NOT support: markdown headers, syntax-highlighted code blocks, inline links with text
- Max message size for Twilio WhatsApp: 1,600 characters (use 1,500 as safe limit)
- Chunking strategy: split on double newlines first, then single newlines, then sentences
- Consider adding a system prompt modifier for WhatsApp context that encourages shorter, conversational responses

---

### Story 21.4: Media File Support

**As a** WhatsApp user,
**I want** to send images and documents to Annie via WhatsApp,
**So that** Annie can analyze my files the same way she does on Telegram.

**Acceptance Criteria:**

**Given** a user sends an image (JPEG, PNG, WebP) via WhatsApp
**When** the webhook receives the message with `MediaUrl0` and `MediaContentType0`
**Then** the file is downloaded from Twilio's media URL (with authentication), base64-encoded, and sent to `/api/chat` as a `FileAttachment`

**And** documents (PDF, DOCX, XLSX, CSV) are handled the same way
**And** multiple media files in a single message are all processed
**And** file size validation matches existing limits (10MB images, 20MB documents)
**And** unsupported file types return a friendly error message to the user
**And** media URLs are accessed using Twilio credentials (Basic auth with Account SID and Auth Token)

**Prerequisites:** Story 21.2

**Technical Notes:**
- Twilio webhook includes `NumMedia`, `MediaUrl0`, `MediaContentType0`, `MediaUrl1`, etc.
- Media URLs require HTTP Basic Auth with Twilio credentials to download
- Reuse `FileAttachment` model from `backend/api/models/file_attachment.py`
- Create `whatsapp_bot/file_handler.py` mirroring `telegram_bot/file_handler.py`
- Process-and-discard model: no file persistence, same as Telegram
- WhatsApp compresses images — inform users to send as "document" for full quality if needed

---

### Story 21.5: Typing Indicators & UX Polish

**As a** WhatsApp user,
**I want** visual feedback while Annie is thinking,
**So that** I know my message was received and Annie is working on a response.

**Acceptance Criteria:**

**Given** a user sends a message to Annie
**When** the message is received and forwarded to the backend
**Then** a "typing" indicator is shown in WhatsApp (via Twilio's `typing` channel action) within 1 second

**And** if the backend takes longer than 10 seconds, a "thinking" reaction or interim message is sent (e.g., "Annie is thinking...")
**And** delivery failures are retried once with exponential backoff
**And** if the final send fails after retry, the user receives an error message: "Sorry, I had trouble sending that. Please try again."
**And** rate limiting prevents more than 1 message per second to the same user (Twilio compliance)

**Prerequisites:** Story 21.2

**Technical Notes:**
- Twilio doesn't have a native "typing indicator" API for WhatsApp like Telegram does
- Alternative: Use WhatsApp message reactions (Twilio supports this) to acknowledge receipt
- Or send a brief "..." message that gets replaced by the actual response (not ideal)
- Evaluate Twilio's `read` and `delivered` status callbacks for tracking
- Consider using WhatsApp message reactions API: react with a "thinking" emoji, then remove when response is sent
- Implement graceful error messages that don't expose technical details
- Respect Twilio rate limits: 1 message/second per user, 80 messages/second account-wide

---

### Story 21.6: Cross-Platform Identity Linking

**As a** user who uses both Telegram and WhatsApp,
**I want** Annie to recognize me on both platforms as the same person,
**So that** my conversation history, memories, and profile are shared seamlessly.

**Acceptance Criteria:**

**Given** a user has an existing Telegram profile with Annie (e.g., `telegram_12345`)
**When** they message Annie on WhatsApp from a phone number that matches their Telegram account
**Then** the system links the WhatsApp identity (`whatsapp_+1234567890`) to the existing Telegram identity

**And** subsequent WhatsApp conversations access the same agentic-memories, profile, and preferences
**And** if no phone number match is found, a new independent profile is created for the WhatsApp user
**And** the user can manually trigger linking by sending a command (e.g., "link my accounts") which generates a verification code
**And** the verification code can be entered on the other platform to confirm the link
**And** linked identities are stored in Redis with a bidirectional mapping

**Prerequisites:** Story 21.2

**Technical Notes:**
- Primary linking method: phone number matching (Telegram users who shared their phone number)
- Fallback: verification code flow (6-digit code, 10-minute expiry, stored in Redis)
- Redis key structure: `identity_link:{platform}:{user_id}` -> canonical user ID
- Canonical user ID: first platform the user used becomes the primary ID
- Backend `/api/chat` needs to resolve canonical user ID before processing
- Add `resolve_user_identity()` function to backend that checks for linked accounts
- Consider privacy: only link if both platforms have the same phone number or user explicitly requests it
- Store linked identities: `linked_identities:{canonical_id}` -> set of platform-specific IDs

---

### Story 21.7: Voice Note Transcription

**As a** WhatsApp user,
**I want** to send voice notes to Annie and have her understand them,
**So that** I can talk to Annie hands-free when I'm busy or on the go.

**Acceptance Criteria:**

**Given** a user sends a voice note via WhatsApp
**When** the webhook receives the audio message (`MediaContentType0: audio/ogg`)
**Then** the audio is downloaded, transcribed to text using a speech-to-text service, and the transcription is sent to `/api/chat` as the user's message

**And** the original voice note duration is logged for monitoring
**And** voice notes up to 5 minutes are supported (longer notes return a friendly limit message)
**And** transcription errors fall back to a message: "I couldn't understand that voice note. Could you try again or type your message?"
**And** the transcribed text is shown back to the user as a quoted reply before Annie's response (so they can verify what Annie heard)
**And** supported audio formats: OGG/Opus (WhatsApp native), MP3, M4A, WAV

**Prerequisites:** Story 21.4 (media handling infrastructure)

**Technical Notes:**
- WhatsApp voice notes are sent as `audio/ogg; codecs=opus`
- Speech-to-text provider options (defer final choice to architecture):
  - OpenAI Whisper API (`POST /v1/audio/transcriptions`) - high quality, ~$0.006/min
  - Google Cloud Speech-to-Text - similar quality and pricing
  - Local Whisper model - free but compute-heavy
- Add `SPEECH_TO_TEXT_PROVIDER` and `SPEECH_TO_TEXT_API_KEY` to environment config
- Create `whatsapp_bot/transcription.py` for STT integration
- Consider caching transcriptions briefly (30s) in case of retry
- Log transcription latency and confidence scores for monitoring
- Max voice note size: ~10MB (5 minutes at WhatsApp quality)

---

## Implementation Notes

### New Service Structure
```
whatsapp_bot/
  __init__.py
  app.py              # FastAPI webhook server
  config.py           # Environment config
  logging.py          # Structured logging
  webhook.py          # Twilio webhook handler
  message_handler.py  # Message processing logic
  file_handler.py     # Media download and processing
  formatter.py        # Response adaptation for WhatsApp
  transcription.py    # Voice note STT integration
  identity.py         # Cross-platform identity resolution
  Dockerfile
  requirements.txt
```

### New Environment Variables
```
TWILIO_ACCOUNT_SID=       # Twilio account SID
TWILIO_AUTH_TOKEN=        # Twilio auth token
TWILIO_WHATSAPP_NUMBER=   # WhatsApp sender number (e.g., +14155238886)
SPEECH_TO_TEXT_PROVIDER=  # whisper-api | google-stt (default: whisper-api)
SPEECH_TO_TEXT_API_KEY=   # API key for STT service
```

### Docker Compose Addition
- Service: `whatsapp-bot`
- Port: 8004:8000
- Depends on: backend, redis
- Health check: GET /health
- Restart policy: unless-stopped

---

_For implementation: Use the `create-story` workflow to generate individual story implementation plans from this epic breakdown._
