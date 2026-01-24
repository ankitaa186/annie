# Story 18.4: User Feedback and Acknowledgment Flow

Status: ready-for-dev

## Story

As a **user**,
I want **Annie to immediately acknowledge when I send files and show processing status**,
so that **I know my files were received and understand what Annie is doing with them**.

## Acceptance Criteria

1. **AC1**: Immediate acknowledgment message when file(s) received (before LLM processing starts)
2. **AC2**: Acknowledgment includes itemized list of received files with icons
3. **AC3**: Show file type indicator: 📷 for images, 📄 for documents, 📊 for spreadsheets
4. **AC4**: Show page count for PDF files when available
5. **AC5**: Show typing indicator during LLM processing
6. **AC6**: LLM response naturally references file content ("I can see your portfolio shows...")
7. **AC7**: Graceful error messages for processing failures with actionable suggestions
8. **AC8**: Unit tests for acknowledgment message formatting

## Tasks / Subtasks

- [ ] **Task 1: Implement acknowledgment message builder** (AC: 1,2,3,4)
  - [ ] 1.1 Create `format_file_acknowledgment(files: List[FileAttachment])` function
  - [ ] 1.2 Map MIME types to emoji icons (📷, 📄, 📊)
  - [ ] 1.3 Extract page count from PDF metadata if available
  - [ ] 1.4 Format multi-file list with bullet points
  - [ ] 1.5 Add "Let me take a look..." suffix

- [ ] **Task 2: Send acknowledgment before backend call** (AC: 1,5)
  - [ ] 2.1 In message handler, send acknowledgment immediately after file validation
  - [ ] 2.2 Send acknowledgment BEFORE calling backend API
  - [ ] 2.3 Show typing indicator after acknowledgment, during backend processing
  - [ ] 2.4 Handle acknowledgment send failure gracefully (don't block file processing)

- [ ] **Task 3: Enhance system prompt for file awareness** (AC: 6)
  - [ ] 3.1 Add instruction to system prompt when files are present
  - [ ] 3.2 Instruct LLM to reference file content naturally
  - [ ] 3.3 Include file metadata (names, types) in context for LLM

- [ ] **Task 4: Implement error message formatting** (AC: 7)
  - [ ] 4.1 Create `format_file_error(error_type, context)` function
  - [ ] 4.2 Handle: unsupported_format, size_exceeded, download_failed, processing_failed
  - [ ] 4.3 Include actionable suggestions in error messages
  - [ ] 4.4 For partial failures in multi-file, report which files succeeded/failed

- [ ] **Task 5: Write unit tests** (AC: 8)
  - [ ] 5.1 Test `format_file_acknowledgment()` with single image
  - [ ] 5.2 Test `format_file_acknowledgment()` with multiple files
  - [ ] 5.3 Test `format_file_acknowledgment()` with PDF page count
  - [ ] 5.4 Test `format_file_error()` for each error type
  - [ ] 5.5 Test emoji mapping for all file categories

## Dev Notes

### Acknowledgment Message Format

**Single file:**
```
📷 Got it - you've shared:
• portfolio_screenshot.png

Let me take a look...
```

**Multiple files:**
```
📎 Got it - you've shared 3 files:
• 📷 portfolio_screenshot.png
• 📄 investment_strategy.pdf (12 pages)
• 📊 transactions.xlsx

Let me take a look...
```

### File Type Icons

```python
FILE_TYPE_ICONS = {
    "image": "📷",
    "document": "📄",
    "spreadsheet": "📊",
}

# For multi-file header
MULTI_FILE_ICON = "📎"
```

### Error Message Examples

**Unsupported format:**
```
Sorry, I can't process .zip files yet. I support:
• Images: JPEG, PNG, GIF, WEBP
• Documents: PDF, DOCX, TXT
• Spreadsheets: XLSX, CSV

Could you send the file in one of these formats?
```

**File too large:**
```
That file is too large (25MB). Please send:
• Images under 10MB
• Documents under 20MB
```

**Processing failed:**
```
I received your file but had trouble reading it. Could you:
• Try sending it again
• Or describe what's in it

I'll do my best to help either way!
```

**Partial multi-file failure:**
```
📎 I received 3 files but couldn't process one:
• ✅ portfolio.png - ready
• ✅ report.pdf - ready
• ❌ data.zip - unsupported format

I'll analyze the files I can read. Let me take a look...
```

### System Prompt Addition

When files are present, append to system prompt:
```
The user has shared the following files with you:
- portfolio_screenshot.png (image/png)
- investment_report.pdf (application/pdf)

Reference these files naturally in your response. For example, say "I can see in your portfolio screenshot that..." rather than "The file you uploaded shows..."
```

### Files to Modify

- `telegram_bot/file_handler.py` - Add formatting functions
- `telegram_bot/handlers/message.py` - Send acknowledgment before backend call
- `backend/api/prompts.py` - Add file-aware system prompt section
- `telegram_bot/tests/test_file_handler.py` - Add formatting tests

### References

- [Source: .bmad-ephemeral/stories/tech-spec-epic-18.md#Non-Functional-Requirements]
- [Source: docs/epics/epic-18-file-context-sharing.md#Story-18.4]

## Dev Agent Record

### Context Reference

<!-- Path(s) to story context XML will be added here by context workflow -->

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
