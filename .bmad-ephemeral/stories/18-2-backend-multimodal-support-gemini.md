# Story 18.2: Backend Multimodal Support (Gemini)

Status: ready-for-dev

## Story

As a **user**,
I want **Annie's backend to process my uploaded files using Gemini's native multimodal capabilities**,
so that **Annie can understand and analyze images, documents, and spreadsheets I share**.

## Acceptance Criteria

1. **AC1**: Extend `ChatRequest` Pydantic model to accept optional `files: List[FileAttachment]`
2. **AC2**: Accept files array in POST /api/chat request payload
3. **AC3**: Thread files through to stream endpoint via request context or Redis
4. **AC4**: Build Gemini `contents` array with mixed text and `inline_data` file parts
5. **AC5**: Support single file requests
6. **AC6**: Support multi-file requests (up to 10 files batched in one Gemini request)
7. **AC7**: Validate MIME types supported by Gemini before building request
8. **AC8**: Files attached only to first user message in conversation (avoid duplication)
9. **AC9**: Discard file data after LLM response completes (no persistence to Redis/DB)
10. **AC10**: Handle Gemini API errors for multimodal requests gracefully
11. **AC11**: Log multimodal request metadata: file_count, total_size_bytes, mime_types
12. **AC12**: Unit tests with mocked Gemini responses for multimodal requests

## Tasks / Subtasks

- [ ] **Task 1: Extend data models** (AC: 1,2)
  - [ ] 1.1 Create `FileAttachment` Pydantic model in `backend/api/routes/chat.py` or shared models
  - [ ] 1.2 Add `files: Optional[List[FileAttachment]] = None` to `ChatRequest` model
  - [ ] 1.3 Add request validation for max 10 files

- [ ] **Task 2: Update chat route** (AC: 2,3)
  - [ ] 2.1 Parse files from incoming ChatRequest
  - [ ] 2.2 Store files in request context for stream endpoint access
  - [ ] 2.3 Log file metadata on receipt (not content)

- [ ] **Task 3: Update stream route** (AC: 3)
  - [ ] 3.1 Retrieve files from request context
  - [ ] 3.2 Pass files to LLMClient.stream_chat_completion() as new parameter
  - [ ] 3.3 Ensure files garbage collected after streaming completes

- [ ] **Task 4: Extend LLM client** (AC: 4,5,6,8,9)
  - [ ] 4.1 Add `files: Optional[List[FileAttachment]] = None` parameter to stream_chat_completion
  - [ ] 4.2 Pass files to provider's stream_chat_completion method
  - [ ] 4.3 Ensure files only passed on initial request, not retries with same context

- [ ] **Task 5: Implement Gemini multimodal in provider** (AC: 4,5,6,7,8,10)
  - [ ] 5.1 Create `_build_multimodal_contents()` method in GeminiProvider
  - [ ] 5.2 Build `parts` array: text part + inline_data parts for files
  - [ ] 5.3 Attach files only to first user message (clear files after first use)
  - [ ] 5.4 Handle Gemini-specific errors for file processing
  - [ ] 5.5 Validate MIME types against Gemini-supported list

- [ ] **Task 6: Implement logging and observability** (AC: 11)
  - [ ] 6.1 Log `event=multimodal_request` with file_count, total_size_bytes, mime_types
  - [ ] 6.2 Add Langfuse metadata for file requests
  - [ ] 6.3 Track file processing duration separately from text processing

- [ ] **Task 7: Write unit tests** (AC: 12)
  - [ ] 7.1 Test ChatRequest parsing with files
  - [ ] 7.2 Test `_build_multimodal_contents()` with single image
  - [ ] 7.3 Test `_build_multimodal_contents()` with multiple files
  - [ ] 7.4 Test `_build_multimodal_contents()` with text-only (no files)
  - [ ] 7.5 Test file attachment only on first user message
  - [ ] 7.6 Mock Gemini response for multimodal request

## Dev Notes

### Technical Approach

**Gemini Request Structure**:
```python
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
```

**Key Implementation Pattern**:
```python
def _build_multimodal_contents(
    self,
    messages: List[Dict],
    files: Optional[List[FileAttachment]] = None
) -> List[Dict]:
    contents = []
    files_attached = False

    for msg in messages:
        parts = []
        if msg.get("content"):
            parts.append({"text": msg["content"]})

        # Attach files only to first user message
        if msg["role"] == "user" and files and not files_attached:
            for file in files:
                parts.append({
                    "inline_data": {
                        "mime_type": file.mime_type,
                        "data": file.data_base64
                    }
                })
            files_attached = True

        contents.append({
            "role": "user" if msg["role"] == "user" else "model",
            "parts": parts
        })

    return contents
```

### Files to Modify

- `backend/api/routes/chat.py` - Add FileAttachment model, extend ChatRequest
- `backend/api/routes/stream.py` - Thread files to LLM client
- `backend/api/llm_client.py` - Add files parameter, pass to provider
- `backend/api/providers/gemini_provider.py` - Build multimodal contents
- `backend/tests/test_multimodal.py` - New test file

### Gemini MIME Types Supported

- Images: image/jpeg, image/png, image/gif, image/webp
- Documents: application/pdf, text/plain
- Spreadsheets: text/csv, application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
- Word: application/vnd.openxmlformats-officedocument.wordprocessingml.document

### References

- [Source: .bmad-ephemeral/stories/tech-spec-epic-18.md#Detailed-Design]
- [Source: .bmad-ephemeral/stories/tech-spec-epic-18.md#Workflows-and-Sequencing]
- [Source: docs/epics/epic-18-file-context-sharing.md#Story-18.2]

## Dev Agent Record

### Context Reference

<!-- Path(s) to story context XML will be added here by context workflow -->

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
