# Story 18.1: Telegram Bot File Reception

Status: ready-for-dev

## Story

As a **user**,
I want **to send images, documents, and spreadsheets to Annie via Telegram**,
so that **Annie can see and analyze visual or document-based context without me typing everything**.

## Acceptance Criteria

1. **AC1**: Detect photo messages (`message.photo`) and document messages (`message.document`) in Telegram updates
2. **AC2**: Support multiple files in a single message via media groups (`media_group_id`)
3. **AC3**: Download files via Telegram Bot API `getFile` endpoint with 30s timeout
4. **AC4**: Validate file size: images ≤10MB, documents/spreadsheets ≤20MB
5. **AC5**: Validate MIME types against supported formats (JPEG, PNG, GIF, WEBP, PDF, DOCX, TXT, XLSX, CSV)
6. **AC6**: Convert downloaded files to base64 encoding
7. **AC7**: Build `FileAttachment` objects with filename, mime_type, size_bytes, data_base64
8. **AC8**: Return clear error for unsupported formats with list of supported types
9. **AC9**: Return clear error for oversized files with size limit information
10. **AC10**: Log file reception metadata (filename, mime_type, size) - NEVER log data_base64
11. **AC11**: Pass files array to backend_client for inclusion in chat request
12. **AC12**: Unit tests achieve 90%+ coverage for new file_handler module

## Tasks / Subtasks

- [ ] **Task 1: Create file_handler.py module** (AC: 1,2,3,6,7)
  - [ ] 1.1 Create `telegram_bot/file_handler.py` with SUPPORTED_MIME_TYPES and FILE_SIZE_LIMITS constants
  - [ ] 1.2 Implement `FileAttachment` Pydantic model matching backend schema
  - [ ] 1.3 Implement `detect_files(message)` → returns list of file_ids with metadata
  - [ ] 1.4 Implement `download_file(bot, file_id)` → returns bytes with retry on failure
  - [ ] 1.5 Implement `encode_file(file_bytes)` → returns base64 string
  - [ ] 1.6 Implement `process_files(bot, message)` → returns List[FileAttachment]

- [ ] **Task 2: Implement validation functions** (AC: 4,5,8,9)
  - [ ] 2.1 Implement `validate_mime_type(mime_type)` → raises ValidationError if unsupported
  - [ ] 2.2 Implement `validate_file_size(size_bytes, category)` → raises ValidationError if too large
  - [ ] 2.3 Implement `get_file_category(mime_type)` → returns "image"|"document"|"spreadsheet"
  - [ ] 2.4 Create user-friendly error messages with supported format list

- [ ] **Task 3: Integrate with message handler** (AC: 1,2,11)
  - [ ] 3.1 Modify `telegram_bot/handlers/message.py` to detect file messages
  - [ ] 3.2 Add branch: if message has photo/document → call `process_files()`
  - [ ] 3.3 Handle media groups: collect all files before processing
  - [ ] 3.4 Pass files to `backend_client.send_chat_request()` with new `files` parameter

- [ ] **Task 4: Update backend_client** (AC: 11)
  - [ ] 4.1 Extend `send_chat_request()` to accept optional `files: List[FileAttachment]`
  - [ ] 4.2 Include files in POST /api/chat request body
  - [ ] 4.3 Serialize FileAttachment objects to JSON

- [ ] **Task 5: Implement logging** (AC: 10)
  - [ ] 5.1 Log `event=file_received` with filename, mime_type, size_bytes, user_id
  - [ ] 5.2 Log `event=file_validation_failed` with reason (unsupported_format, size_exceeded)
  - [ ] 5.3 Ensure data_base64 is NEVER included in any log statement

- [ ] **Task 6: Write unit tests** (AC: 12)
  - [ ] 6.1 Create `telegram_bot/tests/test_file_handler.py`
  - [ ] 6.2 Test `detect_files()` for photo messages
  - [ ] 6.3 Test `detect_files()` for document messages
  - [ ] 6.4 Test `validate_mime_type()` with supported and unsupported types
  - [ ] 6.5 Test `validate_file_size()` within and exceeding limits
  - [ ] 6.6 Test `encode_file()` with small and large files
  - [ ] 6.7 Test media group handling
  - [ ] 6.8 Test error message formatting

## Dev Notes

### Technical Approach

**File Detection**: Use `message.photo` (list of PhotoSize, use largest) and `message.document` (single Document object). For media groups, Telegram sends multiple updates with same `media_group_id` - collect all before processing.

**Download Pattern**:
```python
file = await context.bot.get_file(file_id)
file_bytes = await file.download_as_bytearray()
```

**Validation Order**:
1. Check MIME type first (fast, no download needed if invalid)
2. Check file size from Telegram metadata (before download)
3. Download only valid files
4. Encode to base64

### MIME Type Constants

```python
SUPPORTED_MIME_TYPES = {
    "image/jpeg": "image",
    "image/png": "image",
    "image/gif": "image",
    "image/webp": "image",
    "application/pdf": "document",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "document",
    "text/plain": "document",
    "text/csv": "spreadsheet",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "spreadsheet",
}

FILE_SIZE_LIMITS = {
    "image": 10 * 1024 * 1024,      # 10MB
    "document": 20 * 1024 * 1024,   # 20MB
    "spreadsheet": 20 * 1024 * 1024, # 20MB
}
```

### Error Messages

- Unsupported format: "Sorry, I can't process .{ext} files yet. I support images (JPEG, PNG, GIF, WEBP) and documents (PDF, DOCX, TXT, XLSX, CSV)."
- Oversized: "That file is too large ({size}MB). Please send files under {limit}MB for {category}."

### Project Structure Notes

- New file: `telegram_bot/file_handler.py`
- Modified: `telegram_bot/handlers/message.py` (add file detection branch)
- Modified: `telegram_bot/backend_client.py` (add files parameter)
- New test: `telegram_bot/tests/test_file_handler.py`

### References

- [Source: .bmad-ephemeral/stories/tech-spec-epic-18.md#Data-Models-and-Contracts]
- [Source: .bmad-ephemeral/stories/tech-spec-epic-18.md#Workflows-and-Sequencing]
- [Source: docs/epics/epic-18-file-context-sharing.md#Story-18.1]

## Dev Agent Record

### Context Reference

<!-- Path(s) to story context XML will be added here by context workflow -->

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
