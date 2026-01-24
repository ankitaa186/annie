# Epic: File Context Sharing

> **Epic ID**: 18
> **Status**: Draft
> **Priority**: High
> **Estimated Effort**: 3-5 days
> **Dependencies**: Gemini API multimodal support, Telegram Bot API file handling

---

## 1. Overview

### 1.1 Problem Statement

Annie currently operates in a text-only mode, limiting how users can share context:

- **No Visual Context**: Users cannot share screenshots of portfolios, products, or conversations
- **Manual Data Entry**: Users must manually type or copy-paste information that could be captured visually
- **No Document Analysis**: Users cannot share PDFs, spreadsheets, or documents for Annie to analyze
- **Friction in Communication**: Instead of "look at this", users must describe what they're seeing

This creates unnecessary friction in scenarios where visual or document-based context would be natural:
- Sharing a brokerage screenshot instead of typing portfolio details
- Sending a product image for Annie to identify and research
- Forwarding a conversation screenshot for advice on how to respond
- Uploading a PDF report for analysis

### 1.2 Solution

Leverage Gemini's native multimodal capabilities to enable seamless file sharing:

1. **Image Understanding**: Users send screenshots/photos, Annie sees and understands them natively
2. **Document Processing**: PDFs, DOCX, spreadsheets processed directly by Gemini (native support)
3. **Multi-File Support**: Multiple files in a single message, processed together for cross-referencing
4. **Process-and-Discard**: No file storage - files exist only for the duration of the LLM request

**Key Insight**: Gemini 1.5 Pro/2.0 and GPT-4o handle images and documents natively. No custom parsing pipelines needed - we simply pass files through to the LLM.

### 1.3 Success Criteria

| Metric | Target |
|--------|--------|
| File reception latency | <2s from send to acknowledgment |
| LLM processing with file | <10s for images, <30s for large documents |
| Supported image formats | JPEG, PNG, GIF, WEBP |
| Supported document formats | PDF, DOCX, TXT, XLSX, CSV |
| Max image size | 10MB (Telegram limit) |
| Max document size | 20MB (Telegram limit) |
| Multi-file support | Up to 10 files per message |
| User acknowledgment | Always confirm what files were received |

---

## 2. Architecture

### 2.1 File Processing Flow

```
User sends file(s) via Telegram
         |
         v
Telegram Bot receives message
         |
         v
    +--------------------+
    | File Detection     |
    | - Photo/Document?  |
    | - Get file_id      |
    +--------------------+
         |
         v
    +--------------------+
    | Download File      |
    | via Bot API        |
    | (getFile endpoint) |
    +--------------------+
         |
         v
    +--------------------+
    | Convert to Base64  |
    | or temp file URL   |
    +--------------------+
         |
         v
    +--------------------+
    | POST /api/chat     |
    | with file content  |
    +--------------------+
         |
         v
    +--------------------+
    | Backend builds     |
    | multimodal request |
    | for Gemini API     |
    +--------------------+
         |
         v
    +--------------------+
    | Gemini processes   |
    | text + files       |
    | natively           |
    +--------------------+
         |
         v
    +--------------------+
    | Stream response    |
    | back to user       |
    +--------------------+
         |
         v
    +--------------------+
    | Discard file data  |
    | (no storage)       |
    +--------------------+
```

### 2.2 Multi-File Handling

```
User sends 3 files in one message:
- portfolio_screenshot.png
- investment_strategy.pdf
- transactions.xlsx

         |
         v
    +------------------------+
    | Telegram Bot collects  |
    | all files from message |
    +------------------------+
         |
         v
    +------------------------+
    | Download all files     |
    | in parallel            |
    +------------------------+
         |
         v
    +------------------------+
    | Build single Gemini    |
    | request with all files |
    | as content array       |
    +------------------------+
         |
         v
    +------------------------+
    | Gemini sees all files  |
    | together, can cross-   |
    | reference between them |
    +------------------------+
```

### 2.3 Gemini Multimodal Request Structure

```python
# Single image
{
    "contents": [
        {
            "role": "user",
            "parts": [
                {"text": "What do you see in this portfolio?"},
                {
                    "inline_data": {
                        "mime_type": "image/png",
                        "data": "<base64-encoded-image>"
                    }
                }
            ]
        }
    ]
}

# Multiple files
{
    "contents": [
        {
            "role": "user",
            "parts": [
                {"text": "Analyze these documents together"},
                {"inline_data": {"mime_type": "image/png", "data": "..."}},
                {"inline_data": {"mime_type": "application/pdf", "data": "..."}},
                {"inline_data": {"mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "data": "..."}}
            ]
        }
    ]
}
```

### 2.4 ChatGPT Fallback Structure

```python
# GPT-4o format for images
{
    "messages": [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "What do you see?"},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "data:image/png;base64,<base64-data>"
                    }
                }
            ]
        }
    ]
}
```

---

## 3. Stories

### Story 18.1: Telegram Bot File Reception

**Priority**: P0
**Estimate**: 1 day

Enhance Telegram bot to detect, download, and forward files to the backend.

**Files**:
- `telegram_bot/bot.py`
- `telegram_bot/file_handler.py` (new)

**Acceptance Criteria**:

- [ ] Detect photo messages (`message.photo`)
- [ ] Detect document messages (`message.document`)
- [ ] Support multiple files in a single message (media groups)
- [ ] Download files via Telegram Bot API `getFile` endpoint
- [ ] Validate file size against limits (10MB photos, 20MB documents)
- [ ] Validate file type against supported formats
- [ ] Convert downloaded files to base64 encoding
- [ ] Include file metadata in backend request:
  ```json
  {
    "files": [
      {
        "filename": "screenshot.png",
        "mime_type": "image/png",
        "size_bytes": 245000,
        "data_base64": "..."
      }
    ]
  }
  ```
- [ ] Return clear error for unsupported formats: "Sorry, I can't process .zip files yet. I support images (JPEG, PNG, GIF, WEBP) and documents (PDF, DOCX, TXT, XLSX, CSV)."
- [ ] Return clear error for oversized files: "That file is too large (25MB). Please send files under 20MB for documents or 10MB for images."
- [ ] Log file reception with filename, mime_type, size (NOT content)
- [ ] Unit tests for file detection and validation

---

### Story 18.2: Backend Multimodal Support (Gemini)

**Priority**: P0
**Estimate**: 1.5 days

Enhance LLM client to build multimodal requests for Gemini API.

**Files**:
- `backend/api/llm_client.py`
- `backend/api/routes/chat.py`
- `backend/api/routes/stream.py`

**Acceptance Criteria**:

- [ ] Accept files array in chat/stream request payload
- [ ] Build Gemini `contents` array with mixed text and file parts
- [ ] Support `inline_data` format with mime_type and base64 data
- [ ] Handle single file requests
- [ ] Handle multi-file requests (up to 10 files)
- [ ] Validate mime types supported by Gemini:
  - Images: `image/jpeg`, `image/png`, `image/gif`, `image/webp`
  - Documents: `application/pdf`, `text/plain`
  - Spreadsheets: `text/csv`, `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
  - Word: `application/vnd.openxmlformats-officedocument.wordprocessingml.document`
- [ ] Include files in conversation context for follow-up questions
- [ ] Discard file data after LLM response (no persistence)
- [ ] Handle Gemini API errors for file processing gracefully
- [ ] Log multimodal request metadata (file count, total size, mime types)
- [ ] Unit tests with mocked Gemini responses

**Gemini API Notes**:
- Gemini 1.5 Pro supports up to 1M tokens context including files
- PDFs are processed natively - no extraction needed
- Images analyzed with vision capabilities

---

### Story 18.3: Backend Multimodal Support (ChatGPT Fallback)

**Priority**: P1
**Estimate**: 1 day

Implement multimodal fallback for ChatGPT/GPT-4o when Gemini is unavailable.

**Files**:
- `backend/api/llm_client.py`

**Acceptance Criteria**:

- [ ] Build GPT-4o `content` array with mixed text and image_url parts
- [ ] Convert files to data URLs: `data:image/png;base64,...`
- [ ] Support image formats: JPEG, PNG, GIF, WEBP
- [ ] Handle PDF/document fallback:
  - If GPT-4o doesn't support format, extract text first (fallback path)
  - Use `pypdf` for PDF text extraction
  - Use `python-docx` for DOCX text extraction
  - Include extracted text in message content
- [ ] Log when document extraction fallback is used
- [ ] Clear error if file type not supported by fallback: "I'm using a backup system that can't read PDFs right now. Could you copy the key text instead?"
- [ ] Unit tests for ChatGPT multimodal format
- [ ] Unit tests for document extraction fallback

**Note**: GPT-4o has native vision but more limited document support than Gemini. Fallback path extracts text when needed.

---

### Story 18.4: User Feedback and Acknowledgment Flow

**Priority**: P1
**Estimate**: 0.5 days

Implement clear user feedback when files are received and processed.

**Files**:
- `telegram_bot/bot.py`
- `backend/api/routes/stream.py`

**Acceptance Criteria**:

- [ ] Immediate acknowledgment when file(s) received:
  ```
  📎 Got it - you've shared 2 files:
  - 📷 portfolio_screenshot.png
  - 📄 investment_strategy.pdf (12 pages)

  Let me take a look...
  ```
- [ ] Show typing indicator while processing
- [ ] Include file awareness in response:
  ```
  I can see your portfolio screenshot shows holdings in AAPL, GOOGL, and NVDA...
  ```
- [ ] Handle processing errors gracefully:
  ```
  I received your file but had trouble reading it. Could you try sending it again, or describe what's in it?
  ```
- [ ] For multi-file, acknowledge each file by name
- [ ] Page count for PDFs when available
- [ ] Unit tests for acknowledgment message formatting

---

### Story 18.5: Error Handling and Edge Cases

**Priority**: P1
**Estimate**: 0.5 days

Comprehensive error handling for file processing edge cases.

**Files**:
- `telegram_bot/file_handler.py`
- `backend/api/llm_client.py`

**Acceptance Criteria**:

- [ ] Handle Telegram file download failures (network issues)
- [ ] Handle corrupted/unreadable files
- [ ] Handle password-protected PDFs: "This PDF appears to be password-protected. Could you send an unlocked version?"
- [ ] Handle empty files: "That file appears to be empty."
- [ ] Handle timeout for large file processing (30s limit)
- [ ] Handle Gemini rate limits for file processing
- [ ] Handle mixed valid/invalid files in multi-file upload:
  - Process valid files
  - Report which files couldn't be processed
- [ ] Graceful degradation: if file processing fails, continue with text-only conversation
- [ ] All errors logged with context (file type, size, error reason)
- [ ] Unit tests for each error scenario

---

### Story 18.6: Integration Testing and Documentation

**Priority**: P1
**Estimate**: 0.5 days

End-to-end testing and documentation updates.

**Files**:
- `telegram_bot/tests/test_file_handler.py`
- `backend/tests/test_multimodal.py`
- `CLAUDE.md`

**Acceptance Criteria**:

- [ ] Integration test: image upload → Gemini processing → response
- [ ] Integration test: PDF upload → Gemini processing → response
- [ ] Integration test: multi-file upload → combined analysis
- [ ] Integration test: ChatGPT fallback path
- [ ] Test with real files: screenshot, PDF, XLSX
- [ ] CLAUDE.md updated with:
  - Supported file types and limits
  - How file processing works
  - Example user flows
- [ ] Update env.example if any new config needed

---

## 4. Technical Considerations

### 4.1 Supported Formats

| Category | Formats | Max Size | Gemini Native | GPT-4o Native |
|----------|---------|----------|---------------|---------------|
| Images | JPEG, PNG, GIF, WEBP | 10MB | Yes | Yes |
| Documents | PDF | 20MB | Yes | No (extract text) |
| Documents | DOCX | 20MB | Yes | No (extract text) |
| Documents | TXT | 20MB | Yes | Yes (as text) |
| Spreadsheets | XLSX | 20MB | Yes | No (extract text) |
| Spreadsheets | CSV | 20MB | Yes | Yes (as text) |

### 4.2 MIME Type Mapping

```python
SUPPORTED_MIME_TYPES = {
    # Images
    "image/jpeg": "image",
    "image/png": "image",
    "image/gif": "image",
    "image/webp": "image",

    # Documents
    "application/pdf": "document",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "document",
    "text/plain": "document",

    # Spreadsheets
    "text/csv": "spreadsheet",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "spreadsheet",
}
```

### 4.3 Telegram Bot API File Handling

```python
# Get file info
file_info = await bot.get_file(file_id)

# Download file
file_path = file_info.file_path
file_url = f"https://api.telegram.org/file/bot{token}/{file_path}"
file_bytes = await download_file(file_url)

# Convert to base64
import base64
file_base64 = base64.b64encode(file_bytes).decode('utf-8')
```

### 4.4 Memory Considerations

- Files are held in memory only during request processing
- Base64 encoding increases size by ~33%
- 20MB file → ~27MB in memory as base64
- Multi-file (10 files × 20MB) = theoretical max ~270MB per request
- Recommend streaming large files if issues arise

---

## 5. Dependencies

### 5.1 External Services

| Service | Required | Purpose |
|---------|----------|---------|
| Gemini API | Yes | Native multimodal processing |
| ChatGPT API | Fallback | Alternative multimodal provider |
| Telegram Bot API | Yes | File reception |

### 5.2 Python Packages

```
# Potentially needed for ChatGPT fallback only
pypdf>=3.0.0        # PDF text extraction
python-docx>=0.8.0  # DOCX text extraction
openpyxl>=3.0.0     # XLSX text extraction (if needed)
```

### 5.3 Environment Variables

No new environment variables required - uses existing:
- `GEMINI_API_KEY`
- `CHATGPT_API_KEY`
- `TELEGRAM_BOT_TOKEN`

---

## 6. Risks & Mitigations

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Large files cause memory issues | High | Medium | Size limits enforced, streaming for large files |
| Gemini API rate limits for files | Medium | Low | Graceful degradation, retry with backoff |
| Sensitive data in uploaded files | High | Medium | Process-and-discard, no storage, clear privacy messaging |
| Unsupported file content | Low | Medium | Clear error messages, suggest alternatives |
| ChatGPT fallback can't handle format | Medium | Medium | Text extraction fallback, user notification |
| Base64 encoding overhead | Low | High | Accept as tradeoff for simplicity |

---

## 7. Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| File processing success rate | >95% | Logs: successful vs failed file requests |
| User acknowledgment shown | 100% | Every file upload gets acknowledgment |
| Processing time (images) | <10s p95 | Logs: duration_ms |
| Processing time (documents) | <30s p95 | Logs: duration_ms |
| Fallback activation rate | <5% | Logs: ChatGPT fallback usage |
| Error message clarity | Qualitative | User feedback |

---

## 8. Future Considerations

- **File Storage**: Optional persistent storage for "show me that document from last week"
- **Video Support**: Short video clips for context
- **Audio Support**: Voice messages transcription (may already be planned)
- **Handwriting Recognition**: Notes and whiteboard photos
- **Receipt Scanning**: Structured data extraction from receipts
- **Screenshot Annotation**: User can highlight areas of interest
- **Batch Document Processing**: Upload multiple documents for comparative analysis
- **File Summarization**: "Summarize this 50-page PDF in 3 paragraphs"
