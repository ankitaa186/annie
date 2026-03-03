# Epic Technical Specification: File Context Sharing

Date: 2026-01-23
Author: Ankit
Epic ID: 18
Status: Draft

---

## Overview

Epic 18 enables Annie to receive and understand files (images, documents, spreadsheets) shared by users via Telegram, transforming Annie from a text-only assistant into a truly multimodal companion. This addresses a core gap in the current user experience where users must manually type or copy-paste information that could be captured visually (e.g., portfolio screenshots, product images, conversation screenshots, PDF reports).

The implementation leverages Gemini's native multimodal capabilities for processing files directly, with ChatGPT/GPT-4o as a fallback provider. This approach requires no custom parsing pipelines—files are passed through to the LLM which handles vision and document understanding natively. The "process-and-discard" model ensures files exist only for the duration of the LLM request, avoiding storage complexity and privacy concerns.

## Objectives and Scope

### In Scope

- **Image Understanding**: Support JPEG, PNG, GIF, WEBP formats up to 10MB (Telegram limit)
- **Document Processing**: Support PDF, DOCX, TXT formats up to 20MB (Telegram limit)
- **Spreadsheet Processing**: Support XLSX, CSV formats up to 20MB
- **Multi-File Support**: Handle up to 10 files per message, processed together for cross-referencing
- **Telegram Integration**: File reception, validation, and base64 encoding in telegram_bot service
- **Backend Multimodal**: Gemini API multimodal request building with ChatGPT fallback
- **User Feedback**: Immediate acknowledgment of received files with processing status
- **Error Handling**: Comprehensive handling for unsupported formats, oversized files, corrupted files, timeouts
- **Process-and-Discard**: No file storage—files discarded after LLM response

### Out of Scope

- **File Storage/Retrieval**: No persistent storage for "show me that file from last week"
- **Video Support**: No video file processing
- **Audio Support**: Voice messages are handled separately (not in this epic)
- **OCR Pipelines**: No custom OCR—rely on LLM native vision
- **New Environment Variables**: Uses existing GEMINI_API_KEY, CHATGPT_API_KEY, TELEGRAM_BOT_TOKEN

## System Architecture Alignment

This epic aligns with the existing Annie architecture by extending three core components:

| Component | Modification | Architecture Alignment |
|-----------|--------------|------------------------|
| **Telegram Bot** | Add file detection, download, validation, base64 encoding | Extends existing message handling; no new services |
| **Backend API** | Extend chat/stream routes to accept files array; modify LLM client for multimodal | Stateless design maintained; files not persisted |
| **LLM Client** | Add Gemini multimodal request building; add ChatGPT fallback with text extraction | Existing provider abstraction extended |

**Key Constraints Respected**:
- Files processed in-memory only (no Redis/PostgreSQL storage)
- Docker container architecture unchanged
- MCP protocol not affected (no new tools required)
- Existing SSE streaming pattern reused for response delivery

## Detailed Design

### Services and Modules

| Module | Responsibility | Files | Changes |
|--------|---------------|-------|---------|
| **telegram_bot/file_handler.py** (NEW) | File detection, download, validation, base64 encoding | New module | Create new |
| **telegram_bot/handlers/message.py** | Route file messages to file_handler | Existing | Add file detection branch |
| **telegram_bot/backend_client.py** | Pass files to backend API | Existing | Add `files` param to request |
| **backend/api/routes/chat.py** | Accept files in ChatRequest | Existing | Extend Pydantic model |
| **backend/api/routes/stream.py** | Pass files to LLM client | Existing | Thread files through streaming |
| **backend/api/llm_client.py** | Delegate files to provider | Existing | Pass files param to provider |
| **backend/api/providers/gemini_provider.py** | Build multimodal Gemini request | Existing | Add `inline_data` parts |
| **backend/api/providers/chatgpt_provider.py** | Build multimodal ChatGPT request + fallback extraction | Existing | Add `image_url` + text extraction |

### Data Models and Contracts

**FileAttachment Schema** (shared across services):

```python
class FileAttachment(BaseModel):
    """File attachment sent from Telegram bot to backend."""
    filename: str                # Original filename (e.g., "portfolio.png")
    mime_type: str               # MIME type (e.g., "image/png", "application/pdf")
    size_bytes: int              # File size in bytes
    data_base64: str             # Base64-encoded file content

class ChatRequest(BaseModel):
    """Extended chat request with file support."""
    user_id: str
    message: str
    conversation_id: Optional[str] = None
    files: Optional[List[FileAttachment]] = None  # NEW: file attachments
```

**MIME Type Constants**:

```python
SUPPORTED_MIME_TYPES = {
    # Images (Gemini + ChatGPT native)
    "image/jpeg": {"category": "image", "gemini": True, "chatgpt": True},
    "image/png": {"category": "image", "gemini": True, "chatgpt": True},
    "image/gif": {"category": "image", "gemini": True, "chatgpt": True},
    "image/webp": {"category": "image", "gemini": True, "chatgpt": True},

    # Documents (Gemini native, ChatGPT needs extraction)
    "application/pdf": {"category": "document", "gemini": True, "chatgpt": False},
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {
        "category": "document", "gemini": True, "chatgpt": False
    },
    "text/plain": {"category": "document", "gemini": True, "chatgpt": True},

    # Spreadsheets (Gemini native, ChatGPT needs extraction)
    "text/csv": {"category": "spreadsheet", "gemini": True, "chatgpt": True},
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {
        "category": "spreadsheet", "gemini": True, "chatgpt": False
    },
}

FILE_SIZE_LIMITS = {
    "image": 10 * 1024 * 1024,    # 10MB for images
    "document": 20 * 1024 * 1024,  # 20MB for documents
    "spreadsheet": 20 * 1024 * 1024,  # 20MB for spreadsheets
}
```

### APIs and Interfaces

**Extended Chat Endpoint**:

```
POST /api/chat
Content-Type: application/json

{
  "user_id": "telegram_12345",
  "message": "What stocks do I own?",
  "conversation_id": "conv_abc123",
  "files": [
    {
      "filename": "portfolio.png",
      "mime_type": "image/png",
      "size_bytes": 245000,
      "data_base64": "iVBORw0KGgoAAAANSUhEUgAA..."
    }
  ]
}

Response: 200 OK
{
  "conversation_id": "conv_abc123",
  "stream_url": "/api/stream/conv_abc123"
}
```

**Error Responses**:

| Error | HTTP Code | Response |
|-------|-----------|----------|
| Unsupported format | 400 | `{"detail": "Unsupported file type: application/zip"}` |
| File too large | 400 | `{"detail": "File exceeds size limit: 25MB > 20MB max"}` |
| Too many files | 400 | `{"detail": "Too many files: 15 > 10 max"}` |

### Workflows and Sequencing

**File Processing Sequence**:

```
1. User sends photo/document via Telegram
   ↓
2. Telegram Bot (file_handler.py):
   a. Detect message.photo or message.document
   b. Get file_id from Telegram message
   c. Call bot.get_file(file_id) → file_info
   d. Download via Bot API: GET /file/bot{token}/{file_path}
   e. Validate: mime_type in SUPPORTED_MIME_TYPES
   f. Validate: size_bytes <= FILE_SIZE_LIMITS[category]
   g. Encode: base64.b64encode(file_bytes)
   h. Build FileAttachment object
   ↓
3. Telegram Bot → Backend API:
   POST /api/chat with files array
   ↓
4. Backend API (chat.py):
   a. Parse ChatRequest with files
   b. Store files in request context (no persistence)
   c. Return conversation_id, stream_url
   ↓
5. Backend API (stream.py):
   a. Retrieve files from request context
   b. Pass to LLMClient.stream_chat_completion(messages, tools, files=files)
   ↓
6. LLM Client → Provider:
   - If Gemini: Build contents[] with inline_data parts
   - If ChatGPT: Build content[] with image_url parts (images)
                 Extract text for documents (fallback)
   ↓
7. Provider streams response
   ↓
8. File data discarded (garbage collected after response)
```

**Multi-File Handling**:

```
User sends media group (3 files):
  ↓
Telegram Bot collects all files from update.message.media_group_id
  ↓
Download all files in parallel (asyncio.gather)
  ↓
Build single ChatRequest with files=[f1, f2, f3]
  ↓
Gemini sees all files in one request (can cross-reference)
```

**Gemini Multimodal Request Building** (in GeminiProvider):

```python
def _build_multimodal_contents(
    self,
    messages: List[Dict],
    files: Optional[List[FileAttachment]] = None
) -> List[Dict]:
    """Build Gemini contents with text and file parts."""
    contents = []

    for msg in messages:
        parts = []

        # Add text part
        if msg.get("content"):
            parts.append({"text": msg["content"]})

        # Add file parts (for user messages with attachments)
        if msg["role"] == "user" and files:
            for file in files:
                parts.append({
                    "inline_data": {
                        "mime_type": file.mime_type,
                        "data": file.data_base64
                    }
                })
            # Clear files after first user message (only attach once)
            files = None

        contents.append({
            "role": "user" if msg["role"] == "user" else "model",
            "parts": parts
        })

    return contents
```

**ChatGPT Fallback with Text Extraction**:

```python
async def _build_multimodal_messages(
    self,
    messages: List[Dict],
    files: Optional[List[FileAttachment]] = None
) -> List[Dict]:
    """Build ChatGPT messages with image_url and text extraction fallback."""
    result = []

    for msg in messages:
        if msg["role"] == "user" and files:
            content = []
            content.append({"type": "text", "text": msg.get("content", "")})

            for file in files:
                if file.mime_type.startswith("image/"):
                    # Native image support
                    content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{file.mime_type};base64,{file.data_base64}"
                        }
                    })
                elif file.mime_type == "application/pdf":
                    # Extract text from PDF
                    text = await self._extract_pdf_text(file.data_base64)
                    content.append({
                        "type": "text",
                        "text": f"[Content from {file.filename}]:\n{text}"
                    })
                # ... similar for DOCX, XLSX

            result.append({"role": "user", "content": content})
            files = None  # Only attach once
        else:
            result.append(msg)

    return result
```

## Non-Functional Requirements

### Performance

| Metric | Target | Source |
|--------|--------|--------|
| File reception latency (Telegram → Backend) | <2s p95 | Epic 18 Success Criteria |
| Image processing (LLM response start) | <10s p95 | Epic 18 Success Criteria |
| Document processing (LLM response start) | <30s p95 | Epic 18 Success Criteria |
| File download from Telegram API | <5s for 20MB | Telegram Bot API SLA |
| Base64 encoding overhead | <500ms for 20MB | Local CPU operation |
| Multi-file parallel download | <8s for 10 files × 10MB | asyncio.gather parallelism |

**Memory Budget**:
- Single file max in-memory: ~27MB (20MB + 33% base64 overhead)
- Multi-file worst case: ~270MB (10 files × 27MB)
- Files discarded after LLM response (no accumulation)

**Timeout Configuration**:
- Telegram file download: 30s timeout
- Gemini API with files: 60s timeout (increased from 30s for large docs)
- ChatGPT API with files: 60s timeout

### Security

| Concern | Mitigation |
|---------|------------|
| **Sensitive data in files** | Process-and-discard model; files never persisted to disk or database |
| **File content injection** | Files sent as binary blobs to LLM; no execution or parsing by Annie |
| **Oversized files (DoS)** | Size limits enforced at Telegram Bot layer before download |
| **Malicious file types** | Allowlist of MIME types; unknown types rejected |
| **Base64 in logs** | File content (data_base64) NEVER logged; only metadata (filename, mime_type, size) |
| **Memory exhaustion** | Max 10 files per request; size limits; files GC'd after response |

**Data Handling**:
- Files exist only in memory during request lifecycle
- No file content written to Redis, PostgreSQL, or filesystem
- Telegram Bot API handles secure file transfer (HTTPS)
- LLM providers (Google, OpenAI) have their own data handling policies

### Reliability/Availability

| Scenario | Behavior |
|----------|----------|
| Telegram file download fails | Retry once with 2s delay; if still fails, return user-friendly error |
| Gemini API unavailable | Fallback to ChatGPT with text extraction for documents |
| ChatGPT fallback also fails | Return error: "I'm having trouble processing files right now" |
| File corrupted/unreadable | Log error, skip file, process remaining valid files |
| Timeout on large document | Return partial response if available, else timeout error |
| Rate limit on Gemini | Automatic fallback to ChatGPT (existing provider failover) |

**Graceful Degradation**:
- If all file processing fails, conversation continues text-only
- Partial multi-file success: process valid files, report which failed
- Password-protected PDFs: clear error message, suggest unlocked version

### Observability

**Structured Logging Events**:

```python
# File reception (Telegram Bot)
logger.info("File received", extra={
    "event": "file_received",
    "filename": file.filename,
    "mime_type": file.mime_type,
    "size_bytes": file.size_bytes,
    "user_id": user_id,
    # NEVER log data_base64
})

# File validation error
logger.warning("File validation failed", extra={
    "event": "file_validation_failed",
    "filename": file.filename,
    "mime_type": file.mime_type,
    "reason": "unsupported_format",  # or "size_exceeded"
})

# Multimodal request (Backend)
logger.info("Multimodal LLM request", extra={
    "event": "multimodal_request",
    "provider": "gemini-3.1-pro-preview",
    "file_count": 2,
    "total_size_bytes": 1500000,
    "mime_types": ["image/png", "application/pdf"],
})

# Processing complete
logger.info("File processing complete", extra={
    "event": "file_processing_complete",
    "duration_ms": 4500,
    "provider": "gemini-3.1-pro-preview",
    "fallback_used": False,
})
```

**Langfuse Tracing**:
- Existing `@observe` decorators on chat/stream endpoints capture file metadata
- New span: `file_download` for Telegram file retrieval timing
- New span: `multimodal_llm_call` for LLM processing with files
- Metadata: `file_count`, `total_file_size`, `mime_types`

**Metrics to Track**:
| Metric | Purpose |
|--------|---------|
| `file_requests_total` | Count of requests with files |
| `file_processing_duration_seconds` | Histogram of processing time |
| `file_validation_errors_total` | Count by error type |
| `fallback_extractions_total` | ChatGPT text extraction fallback usage |

## Dependencies and Integrations

### External Services

| Service | Purpose | Required | Notes |
|---------|---------|----------|-------|
| **Telegram Bot API** | File reception via `getFile` endpoint | Yes | Already integrated |
| **Gemini API** | Native multimodal processing (images + documents) | Yes | Already integrated (Epic 9) |
| **ChatGPT API (GPT-4o)** | Fallback multimodal (images native, docs extracted) | Fallback | Already integrated |

### Python Package Dependencies

**Backend (backend/requirements.txt)** - New packages for ChatGPT fallback:

```
# Document text extraction (ChatGPT fallback only) - Epic 18
pypdf>=4.0.0           # PDF text extraction
python-docx>=1.1.0     # DOCX text extraction
openpyxl>=3.1.0        # XLSX text extraction
```

**Telegram Bot (telegram_bot/requirements.txt)** - No new packages needed:
- `python-telegram-bot==20.7` already supports file downloads
- `aiohttp==3.9.1` already supports async file operations

### Existing Dependencies (Already Present)

| Package | Service | Purpose |
|---------|---------|---------|
| `google-generativeai>=0.3.0` | Backend | Gemini API client with multimodal support |
| `httpx>=0.25.0` | Backend | ChatGPT API calls |
| `python-telegram-bot==20.7` | Telegram Bot | Bot API including file handling |
| `aiohttp==3.9.1` | Telegram Bot | Async HTTP for file downloads |
| `pydantic>=2.9.0` | Both | FileAttachment model validation |

### Integration Points

**1. Telegram Bot API File Handling**:
```python
# Get file info
file = await context.bot.get_file(message.photo[-1].file_id)

# Download file bytes
file_bytes = await file.download_as_bytearray()

# Or download to BytesIO
from io import BytesIO
buffer = BytesIO()
await file.download_to_memory(buffer)
```

**2. Gemini Multimodal API**:
```python
# google-generativeai SDK supports inline_data natively
model = genai.GenerativeModel("gemini-3.1-pro-preview")
response = model.generate_content([
    "Analyze this document",
    {"mime_type": "application/pdf", "data": base64_data}
])
```

**3. ChatGPT Vision API**:
```python
# OpenAI SDK format for images
messages = [{
    "role": "user",
    "content": [
        {"type": "text", "text": "What's in this image?"},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{data}"}}
    ]
}]
```

### Environment Variables

No new environment variables required. Uses existing:

| Variable | Service | Purpose |
|----------|---------|---------|
| `TELEGRAM_BOT_TOKEN` | Telegram Bot | File download authentication |
| `GEMINI_API_KEY` | Backend | Gemini multimodal requests |
| `CHATGPT_API_KEY` | Backend | ChatGPT fallback requests |

## Acceptance Criteria (Authoritative)

### AC-18.1: Image File Support
1. User can send JPEG, PNG, GIF, WEBP images up to 10MB via Telegram
2. Annie acknowledges receipt with filename and file type indicator
3. Annie analyzes image content and responds contextually
4. Unsupported image formats return clear error message

### AC-18.2: Document File Support
1. User can send PDF, DOCX, TXT files up to 20MB via Telegram
2. Annie acknowledges receipt with filename and page count (for PDFs)
3. Annie reads and understands document content
4. Password-protected PDFs return helpful error message

### AC-18.3: Spreadsheet File Support
1. User can send XLSX, CSV files up to 20MB via Telegram
2. Annie acknowledges receipt with filename
3. Annie understands tabular data and can answer questions about it

### AC-18.4: Multi-File Support
1. User can send up to 10 files in a single message (media group)
2. Annie acknowledges all files received with itemized list
3. Annie can cross-reference between files in the same message
4. Requests exceeding 10 files return clear error message

### AC-18.5: User Acknowledgment Flow
1. Immediate acknowledgment when file(s) received (before LLM processing)
2. Typing indicator shown during file processing
3. Response references file content naturally ("I can see your portfolio shows...")
4. Processing errors communicated gracefully with actionable suggestions

### AC-18.6: Error Handling
1. Unsupported file types rejected with list of supported formats
2. Oversized files rejected with size limit information
3. Corrupted/empty files handled gracefully with retry suggestion
4. Network failures during download trigger automatic retry (once)
5. If file processing fails completely, conversation continues text-only

### AC-18.7: ChatGPT Fallback
1. When Gemini unavailable, ChatGPT processes images natively
2. When ChatGPT receives documents, text is extracted and included
3. User notified if fallback cannot process a format ("Could you copy the key text?")

### AC-18.8: Privacy and Security
1. Files never persisted to disk or database (process-and-discard)
2. File content (base64) never logged
3. Only file metadata logged (filename, mime_type, size_bytes)

## Traceability Mapping

| AC | Spec Section | Component(s) | Story | Test Approach |
|----|--------------|--------------|-------|---------------|
| AC-18.1 | Data Models, Workflows | telegram_bot/file_handler.py, gemini_provider.py | 18.1, 18.2 | Unit: MIME validation; Integration: Image → Gemini → Response |
| AC-18.2 | Data Models, Workflows | telegram_bot/file_handler.py, gemini_provider.py | 18.1, 18.2 | Unit: PDF detection; Integration: PDF → Gemini → Response |
| AC-18.3 | Data Models, Workflows | telegram_bot/file_handler.py, gemini_provider.py | 18.1, 18.2 | Unit: Spreadsheet validation; Integration: XLSX → Gemini |
| AC-18.4 | Workflows (Multi-File) | telegram_bot/file_handler.py, chat.py | 18.1, 18.2 | Unit: Media group handling; Integration: 3 files → combined response |
| AC-18.5 | Workflows, APIs | telegram_bot/bot.py, stream.py | 18.4 | Unit: Acknowledgment formatting; E2E: User sees ack before response |
| AC-18.6 | NFR Reliability | file_handler.py, llm_client.py | 18.5 | Unit: Error scenarios; Integration: Invalid file → graceful error |
| AC-18.7 | Workflows (ChatGPT) | chatgpt_provider.py | 18.3 | Unit: Text extraction; Integration: PDF → ChatGPT fallback |
| AC-18.8 | NFR Security, Observability | All modules | 18.1-18.6 | Code review: No base64 in logs; Unit: Verify GC after response |

## Risks, Assumptions, Open Questions

### Risks

| ID | Risk | Impact | Probability | Mitigation |
|----|------|--------|-------------|------------|
| R1 | **Large files cause memory pressure** | High - Could OOM container | Medium | Enforce size limits at Telegram layer; monitor memory usage; consider streaming for files >10MB |
| R2 | **Gemini rate limits on multimodal requests** | Medium - Degraded experience | Low | Existing provider failover to ChatGPT; exponential backoff |
| R3 | **Base64 encoding doubles payload size** | Low - Increased latency/memory | High (certain) | Accept as tradeoff; Telegram → Backend is internal network; consider chunked transfer for very large files |
| R4 | **ChatGPT fallback text extraction loses formatting** | Medium - Reduced doc quality | Medium | Document in user messaging; suggest Gemini-native formats |
| R5 | **Telegram Bot API file download limits** | Medium - Fails for large files | Low | Telegram allows up to 20MB; we enforce same limit |
| R6 | **Sensitive data in user files** | High - Privacy concern | Medium | Process-and-discard model; clear privacy messaging; no logging of content |

### Assumptions

| ID | Assumption | Validation |
|----|------------|------------|
| A1 | Gemini API supports all listed MIME types natively | Verify with Gemini docs; test each format |
| A2 | Telegram Bot API `get_file` returns files up to 20MB | Confirmed in Telegram Bot API docs |
| A3 | Base64 encoding in Python is fast enough (<500ms for 20MB) | Benchmark during implementation |
| A4 | Users primarily send screenshots and small documents | Monitor file sizes in production |
| A5 | `google-generativeai` SDK handles multimodal requests correctly | Already using SDK; test with files |
| A6 | ChatGPT GPT-4o supports vision for all image formats | Confirmed in OpenAI docs |

### Open Questions

| ID | Question | Owner | Resolution |
|----|----------|-------|------------|
| Q1 | Should we support HEIC/HEIF images (iPhone native format)? | PM | **Defer to future** - Convert to JPEG if needed |
| Q2 | What happens if user sends file without any text message? | Dev | Process file with implicit "What's in this?" prompt |
| Q3 | Should file metadata be included in memory storage? | PM | **No** - Process-and-discard means no memory of files |
| Q4 | Max concurrent file downloads per user? | Dev | **10** - Same as max files per message |
| Q5 | Should we show file processing progress for large docs? | UX | **Yes** - Use status updates: "Reading page 5 of 12..." |

## Test Strategy Summary

### Test Levels

| Level | Scope | Tools | Coverage Target |
|-------|-------|-------|-----------------|
| **Unit Tests** | Individual functions (validation, encoding, formatting) | pytest, pytest-asyncio | 90%+ for new code |
| **Integration Tests** | Telegram → Backend → LLM provider flow | pytest, mocked APIs | Happy path + error scenarios |
| **E2E Tests** | Real Telegram → Real Gemini (staging) | Manual + scripted | Core user journeys |

### Unit Test Cases

**telegram_bot/file_handler.py**:
- `test_detect_photo_message` - Correctly identifies photo messages
- `test_detect_document_message` - Correctly identifies document messages
- `test_validate_mime_type_supported` - Accepts valid MIME types
- `test_validate_mime_type_unsupported` - Rejects invalid MIME types
- `test_validate_file_size_within_limit` - Accepts files within limits
- `test_validate_file_size_exceeds_limit` - Rejects oversized files
- `test_base64_encode_small_file` - Correctly encodes small file
- `test_base64_encode_large_file` - Correctly encodes 20MB file
- `test_media_group_collection` - Collects multiple files from media group

**backend/api/providers/gemini_provider.py**:
- `test_build_multimodal_contents_single_image` - Builds correct structure
- `test_build_multimodal_contents_multiple_files` - Handles multi-file
- `test_build_multimodal_contents_text_only` - No files = text-only request
- `test_inline_data_mime_type` - Correct MIME type in request

**backend/api/providers/chatgpt_provider.py**:
- `test_build_multimodal_messages_image` - Correct image_url structure
- `test_extract_pdf_text` - Extracts text from PDF
- `test_extract_docx_text` - Extracts text from DOCX
- `test_fallback_unsupported_format` - Returns error for unsupported

### Integration Test Cases

- `test_image_upload_to_gemini_response` - Full flow with real image
- `test_pdf_upload_to_gemini_response` - Full flow with PDF
- `test_multifile_upload_combined_analysis` - 3 files → cross-referenced response
- `test_chatgpt_fallback_on_gemini_failure` - Gemini fails → ChatGPT succeeds
- `test_chatgpt_pdf_text_extraction` - PDF → text extraction → response
- `test_invalid_file_rejected` - .zip file → clear error
- `test_oversized_file_rejected` - 25MB file → size error
- `test_corrupted_file_graceful_error` - Corrupted PNG → helpful error

### Test Data Requirements

| File Type | Test Files Needed |
|-----------|-------------------|
| Images | Small PNG (100KB), Large JPEG (5MB), GIF, WEBP |
| Documents | PDF (text-based), PDF (scanned/image), DOCX, TXT |
| Spreadsheets | XLSX (simple), CSV |
| Edge Cases | Empty file, corrupted file, password-protected PDF |

### E2E Test Scenarios

1. **Happy Path: Screenshot Analysis**
   - Send portfolio screenshot → Annie describes holdings

2. **Happy Path: Document Q&A**
   - Send PDF report → Ask "What's the main conclusion?"

3. **Multi-File Cross-Reference**
   - Send screenshot + PDF → Ask "Does the PDF match the screenshot?"

4. **Error Recovery**
   - Send unsupported .zip → Receive helpful error → Send PNG → Success

5. **Fallback Path**
   - (Simulate Gemini down) → Send image → ChatGPT responds
