# Story 18.6: Integration Testing and Documentation

Status: ready-for-dev

## Story

As a **developer**,
I want **comprehensive integration tests and updated documentation for file processing**,
so that **the feature is well-tested end-to-end and future developers understand how it works**.

## Acceptance Criteria

1. **AC1**: Integration test: image upload → Gemini processing → streamed response
2. **AC2**: Integration test: PDF upload → Gemini processing → response with document understanding
3. **AC3**: Integration test: multi-file upload → combined analysis referencing all files
4. **AC4**: Integration test: ChatGPT fallback path when Gemini unavailable
5. **AC5**: Test with real files: PNG screenshot, text PDF, simple XLSX
6. **AC6**: CLAUDE.md updated with file processing documentation
7. **AC7**: env.example updated if any new configuration needed
8. **AC8**: All integration tests pass in CI environment

## Tasks / Subtasks

- [ ] **Task 1: Create test fixtures** (AC: 5)
  - [ ] 1.1 Create `backend/tests/fixtures/` directory
  - [ ] 1.2 Add small test PNG image (100KB screenshot)
  - [ ] 1.3 Add small test PDF (2-3 pages, text-based)
  - [ ] 1.4 Add small test XLSX (simple 10-row spreadsheet)
  - [ ] 1.5 Add test DOCX document
  - [ ] 1.6 Add test CSV file

- [ ] **Task 2: Write Telegram Bot integration tests** (AC: 1,2,3)
  - [ ] 2.1 Create `telegram_bot/tests/test_file_integration.py`
  - [ ] 2.2 Test full flow: file message → file_handler → backend_client
  - [ ] 2.3 Mock Telegram Bot API file download
  - [ ] 2.4 Mock backend API response
  - [ ] 2.5 Verify FileAttachment structure passed correctly

- [ ] **Task 3: Write Backend integration tests** (AC: 1,2,3,4)
  - [ ] 3.1 Create `backend/tests/test_multimodal_integration.py`
  - [ ] 3.2 Test POST /api/chat with files array
  - [ ] 3.3 Test stream endpoint receives files
  - [ ] 3.4 Test Gemini provider builds correct multimodal request (mocked API)
  - [ ] 3.5 Test ChatGPT fallback with document extraction (mocked API)
  - [ ] 3.6 Test multi-file batching in single request

- [ ] **Task 4: Write E2E test scenarios** (AC: 1,2,3,4)
  - [ ] 4.1 Document manual E2E test plan for staging environment
  - [ ] 4.2 Test: Send real screenshot to Telegram → Annie describes it
  - [ ] 4.3 Test: Send real PDF → Ask specific question about content
  - [ ] 4.4 Test: Send 3 files → Annie cross-references them
  - [ ] 4.5 Test: Simulate Gemini down → ChatGPT responds to image

- [ ] **Task 5: Update CLAUDE.md documentation** (AC: 6)
  - [ ] 5.1 Add "File Upload Support" section
  - [ ] 5.2 Document supported file types and size limits
  - [ ] 5.3 Document file processing architecture (Telegram → Backend → Gemini)
  - [ ] 5.4 Document ChatGPT fallback behavior
  - [ ] 5.5 Add example user flows
  - [ ] 5.6 Document process-and-discard privacy model

- [ ] **Task 6: Update env.example if needed** (AC: 7)
  - [ ] 6.1 Review if any new environment variables were added
  - [ ] 6.2 Add comments for any file-related configuration
  - [ ] 6.3 Verify existing GEMINI_API_KEY, CHATGPT_API_KEY documented

- [ ] **Task 7: CI pipeline verification** (AC: 8)
  - [ ] 7.1 Ensure test fixtures included in Docker build
  - [ ] 7.2 Run all new tests in CI
  - [ ] 7.3 Verify no test file size issues in CI
  - [ ] 7.4 Document any CI-specific considerations

## Dev Notes

### Test Fixture Requirements

| File | Size | Purpose |
|------|------|---------|
| test_screenshot.png | ~100KB | Basic image processing test |
| test_document.pdf | ~50KB | PDF text extraction test |
| test_spreadsheet.xlsx | ~20KB | Spreadsheet data test |
| test_document.docx | ~30KB | Word document test |
| test_data.csv | ~5KB | CSV parsing test |

### Integration Test Pattern

```python
@pytest.mark.asyncio
async def test_image_upload_to_gemini_response():
    """Test full flow: image file → Gemini multimodal → response."""
    # Load test image
    with open("tests/fixtures/test_screenshot.png", "rb") as f:
        image_bytes = f.read()

    # Create FileAttachment
    file = FileAttachment(
        filename="test_screenshot.png",
        mime_type="image/png",
        size_bytes=len(image_bytes),
        data_base64=base64.b64encode(image_bytes).decode()
    )

    # Mock Gemini API response
    with patch("google.generativeai.GenerativeModel.generate_content") as mock:
        mock.return_value = MockGeminiResponse("I can see a chart showing...")

        # Make request
        response = await client.post("/api/chat", json={
            "user_id": "test_user",
            "message": "What's in this image?",
            "files": [file.dict()]
        })

        assert response.status_code == 200
        # Verify multimodal request was built correctly
        call_args = mock.call_args
        assert "inline_data" in str(call_args)
```

### CLAUDE.md Addition

```markdown
## File Upload Support (Epic 18)

Annie supports receiving and analyzing files shared via Telegram.

### Supported File Types

| Category | Formats | Max Size |
|----------|---------|----------|
| Images | JPEG, PNG, GIF, WEBP | 10MB |
| Documents | PDF, DOCX, TXT | 20MB |
| Spreadsheets | XLSX, CSV | 20MB |

### How It Works

1. User sends file(s) via Telegram
2. Telegram Bot validates and downloads files
3. Files converted to base64 and sent to Backend
4. Backend includes files in Gemini API request (native multimodal)
5. If Gemini unavailable, ChatGPT fallback with text extraction for documents
6. Annie responds with understanding of file content
7. Files discarded after response (not stored)

### Example User Flows

**Screenshot Analysis:**
```
User: [sends portfolio screenshot]
Annie: 📷 Got it - you've shared portfolio_screenshot.png
       Let me take a look...

       I can see your portfolio shows holdings in AAPL (45 shares),
       GOOGL (12 shares), and NVDA (8 shares). Your total value
       appears to be around $52,000. Would you like me to analyze
       the allocation or suggest any changes?
```

### Privacy

- Files are processed in memory only
- No files are stored to disk or database
- File content is never logged (only metadata)
```

### Files to Create/Modify

- `backend/tests/fixtures/` - Test file directory (new)
- `backend/tests/test_multimodal_integration.py` - Backend integration tests (new)
- `telegram_bot/tests/test_file_integration.py` - Telegram integration tests (new)
- `CLAUDE.md` - Add file upload documentation
- `env.example` - Add comments if needed

### References

- [Source: .bmad-ephemeral/stories/tech-spec-epic-18.md#Test-Strategy-Summary]
- [Source: docs/epics/epic-18-file-context-sharing.md#Story-18.6]

## Dev Agent Record

### Context Reference

<!-- Path(s) to story context XML will be added here by context workflow -->

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
