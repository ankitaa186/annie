# Story 18.5: Error Handling and Edge Cases

Status: ready-for-dev

## Story

As a **user**,
I want **Annie to handle file processing errors gracefully and continue helping me**,
so that **a failed file upload doesn't break our conversation or leave me confused**.

## Acceptance Criteria

1. **AC1**: Handle Telegram file download failures with automatic retry (once, 2s delay)
2. **AC2**: Handle corrupted/unreadable files with clear error and retry suggestion
3. **AC3**: Handle password-protected PDFs with specific error message
4. **AC4**: Handle empty files (0 bytes) with clear error
5. **AC5**: Handle timeout for large file processing (30s download, 60s LLM)
6. **AC6**: Handle Gemini rate limits for multimodal requests (trigger ChatGPT fallback)
7. **AC7**: Handle mixed valid/invalid files: process valid ones, report failures
8. **AC8**: Graceful degradation: if all file processing fails, continue text-only
9. **AC9**: All errors logged with context (file type, size, error reason, user_id)
10. **AC10**: Unit tests for each error scenario

## Tasks / Subtasks

- [ ] **Task 1: Implement download retry logic** (AC: 1,5)
  - [ ] 1.1 Add retry decorator or loop to `download_file()` with 1 retry, 2s delay
  - [ ] 1.2 Set 30s timeout on Telegram file download
  - [ ] 1.3 Log retry attempts with context
  - [ ] 1.4 Return user-friendly error after retry exhausted

- [ ] **Task 2: Implement file validation error handling** (AC: 2,3,4)
  - [ ] 2.1 Detect corrupted files during base64 encoding or validation
  - [ ] 2.2 Use pypdf to detect password-protected PDFs before full processing
  - [ ] 2.3 Check file size > 0 before processing
  - [ ] 2.4 Create specific error messages for each case

- [ ] **Task 3: Implement timeout handling** (AC: 5)
  - [ ] 3.1 Set 60s timeout on LLM API calls with files
  - [ ] 3.2 Handle timeout exception, return partial response if available
  - [ ] 3.3 Log timeout events with file size/count for analysis

- [ ] **Task 4: Implement provider failover for multimodal** (AC: 6)
  - [ ] 4.1 Ensure existing provider failover handles multimodal requests
  - [ ] 4.2 On Gemini rate limit, pass files to ChatGPT fallback
  - [ ] 4.3 Log provider failover with multimodal context

- [ ] **Task 5: Implement partial success handling** (AC: 7)
  - [ ] 5.1 In `process_files()`, collect results and errors separately
  - [ ] 5.2 Continue processing valid files even if some fail
  - [ ] 5.3 Return both valid FileAttachments and error list
  - [ ] 5.4 Format combined acknowledgment showing successes and failures

- [ ] **Task 6: Implement graceful degradation** (AC: 8)
  - [ ] 6.1 If all files fail, still send text message to backend
  - [ ] 6.2 Include error context in message for LLM awareness
  - [ ] 6.3 User receives helpful response despite file failure

- [ ] **Task 7: Implement comprehensive logging** (AC: 9)
  - [ ] 7.1 Log all file errors with: event, error_type, mime_type, size_bytes, user_id
  - [ ] 7.2 Never log file content (data_base64)
  - [ ] 7.3 Include request_id for tracing
  - [ ] 7.4 Log error resolution (retry success, fallback used, graceful degradation)

- [ ] **Task 8: Write unit tests** (AC: 10)
  - [ ] 8.1 Test download retry on first failure, success on retry
  - [ ] 8.2 Test download retry exhausted, returns error
  - [ ] 8.3 Test corrupted file detection
  - [ ] 8.4 Test password-protected PDF detection
  - [ ] 8.5 Test empty file handling
  - [ ] 8.6 Test timeout handling
  - [ ] 8.7 Test partial success with mixed files
  - [ ] 8.8 Test graceful degradation to text-only

## Dev Notes

### Error Types and Messages

| Error Type | Detection | User Message |
|------------|-----------|--------------|
| download_failed | Telegram API error after retry | "I couldn't download your file. Could you try sending it again?" |
| corrupted | Exception during processing | "That file appears to be corrupted. Could you try sending it again?" |
| password_protected | pypdf raises PasswordNeeded | "This PDF appears to be password-protected. Could you send an unlocked version?" |
| empty_file | size_bytes == 0 | "That file appears to be empty." |
| timeout | asyncio.TimeoutError | "Processing took too long. Could you try a smaller file?" |
| rate_limited | Provider returns 429 | (silent failover to ChatGPT, or graceful error if both fail) |

### Retry Pattern

```python
async def download_file_with_retry(bot, file_id, max_retries=1, delay=2.0):
    for attempt in range(max_retries + 1):
        try:
            file = await asyncio.wait_for(
                bot.get_file(file_id),
                timeout=30.0
            )
            return await file.download_as_bytearray()
        except Exception as e:
            if attempt < max_retries:
                logger.warning("File download failed, retrying", extra={
                    "attempt": attempt + 1,
                    "file_id": file_id,
                    "error": str(e)
                })
                await asyncio.sleep(delay)
            else:
                raise FileDownloadError(f"Failed after {max_retries + 1} attempts")
```

### Password-Protected PDF Detection

```python
from pypdf import PdfReader
from pypdf.errors import FileNotDecryptedError

def check_pdf_accessible(data_base64: str) -> bool:
    try:
        pdf_bytes = base64.b64decode(data_base64)
        reader = PdfReader(BytesIO(pdf_bytes))
        # Try to access first page - will fail if encrypted
        _ = reader.pages[0].extract_text()
        return True
    except FileNotDecryptedError:
        return False  # Password protected
```

### Partial Success Response

```python
class FileProcessingResult:
    successful: List[FileAttachment]
    failed: List[FileError]  # {filename, error_type, message}

# In message handler
result = await process_files(bot, message)
if result.failed:
    # Include failure info in acknowledgment
    ack_message = format_partial_success_acknowledgment(result)
# Always continue with successful files (even if empty list)
```

### Files to Modify

- `telegram_bot/file_handler.py` - Add retry logic, validation, partial success handling
- `telegram_bot/handlers/message.py` - Handle FileProcessingResult
- `backend/api/llm_client.py` - Ensure failover works with files parameter
- `backend/api/providers/gemini_provider.py` - Handle timeout configuration
- `telegram_bot/tests/test_file_handler.py` - Error scenario tests

### References

- [Source: .bmad-ephemeral/stories/tech-spec-epic-18.md#Reliability-Availability]
- [Source: .bmad-ephemeral/stories/tech-spec-epic-18.md#Risks-Assumptions-Open-Questions]
- [Source: docs/epics/epic-18-file-context-sharing.md#Story-18.5]

## Dev Agent Record

### Context Reference

<!-- Path(s) to story context XML will be added here by context workflow -->

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
