# Story 18.3: Backend Multimodal Support (ChatGPT Fallback)

Status: ready-for-dev

## Story

As a **user**,
I want **Annie to fall back to ChatGPT/GPT-4o for file processing when Gemini is unavailable**,
so that **I can still share files even during Gemini outages or rate limits**.

## Acceptance Criteria

1. **AC1**: Build GPT-4o `content` array with mixed text and `image_url` parts for images
2. **AC2**: Convert image files to data URLs: `data:image/png;base64,{data}`
3. **AC3**: Support image formats natively: JPEG, PNG, GIF, WEBP
4. **AC4**: For PDFs, extract text using `pypdf` and include as text content
5. **AC5**: For DOCX, extract text using `python-docx` and include as text content
6. **AC6**: For XLSX, extract data using `openpyxl` and include as formatted text
7. **AC7**: Log when document extraction fallback is used (event=fallback_extraction)
8. **AC8**: Return clear error if fallback cannot process a format
9. **AC9**: Add required packages to backend/requirements.txt: pypdf, python-docx, openpyxl
10. **AC10**: Unit tests for image multimodal format
11. **AC11**: Unit tests for document text extraction

## Tasks / Subtasks

- [ ] **Task 1: Add dependencies** (AC: 9)
  - [ ] 1.1 Add `pypdf>=4.0.0` to backend/requirements.txt
  - [ ] 1.2 Add `python-docx>=1.1.0` to backend/requirements.txt
  - [ ] 1.3 Add `openpyxl>=3.1.0` to backend/requirements.txt
  - [ ] 1.4 Rebuild Docker container to install new packages

- [ ] **Task 2: Implement image multimodal for ChatGPT** (AC: 1,2,3)
  - [ ] 2.1 Create `_build_multimodal_messages()` method in ChatGPTProvider
  - [ ] 2.2 Build content array with text and image_url parts
  - [ ] 2.3 Convert base64 to data URL format
  - [ ] 2.4 Handle multiple images in single request

- [ ] **Task 3: Implement PDF text extraction** (AC: 4)
  - [ ] 3.1 Create `_extract_pdf_text(data_base64)` method
  - [ ] 3.2 Decode base64, create BytesIO, extract with pypdf
  - [ ] 3.3 Handle password-protected PDFs with clear error
  - [ ] 3.4 Handle corrupted PDFs gracefully

- [ ] **Task 4: Implement DOCX text extraction** (AC: 5)
  - [ ] 4.1 Create `_extract_docx_text(data_base64)` method
  - [ ] 4.2 Decode base64, create BytesIO, extract with python-docx
  - [ ] 4.3 Preserve paragraph structure in extracted text

- [ ] **Task 5: Implement XLSX text extraction** (AC: 6)
  - [ ] 5.1 Create `_extract_xlsx_text(data_base64)` method
  - [ ] 5.2 Decode base64, create BytesIO, extract with openpyxl
  - [ ] 5.3 Format as markdown table or structured text
  - [ ] 5.4 Handle multi-sheet workbooks

- [ ] **Task 6: Integrate extraction into multimodal flow** (AC: 1,4,5,6,8)
  - [ ] 6.1 In `_build_multimodal_messages()`, detect non-image files
  - [ ] 6.2 Route to appropriate extraction method based on MIME type
  - [ ] 6.3 Include extracted text with filename context: "[Content from {filename}]:\n{text}"
  - [ ] 6.4 Handle unsupported formats with clear error message

- [ ] **Task 7: Implement logging** (AC: 7)
  - [ ] 7.1 Log `event=fallback_extraction` with mime_type, filename
  - [ ] 7.2 Log extraction duration for performance monitoring
  - [ ] 7.3 Log extraction failures with error context

- [ ] **Task 8: Write unit tests** (AC: 10,11)
  - [ ] 8.1 Test `_build_multimodal_messages()` with single image
  - [ ] 8.2 Test `_build_multimodal_messages()` with multiple images
  - [ ] 8.3 Test `_extract_pdf_text()` with sample PDF
  - [ ] 8.4 Test `_extract_docx_text()` with sample DOCX
  - [ ] 8.5 Test `_extract_xlsx_text()` with sample XLSX
  - [ ] 8.6 Test fallback for unsupported format

## Dev Notes

### Technical Approach

**ChatGPT Image Format**:
```python
{
    "messages": [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "What's in this image?"},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "data:image/png;base64,{base64_data}"
                    }
                }
            ]
        }
    ]
}
```

**Document Extraction Pattern**:
```python
async def _build_multimodal_messages(
    self,
    messages: List[Dict],
    files: Optional[List[FileAttachment]] = None
) -> List[Dict]:
    result = []
    files_attached = False

    for msg in messages:
        if msg["role"] == "user" and files and not files_attached:
            content = [{"type": "text", "text": msg.get("content", "")}]

            for file in files:
                if file.mime_type.startswith("image/"):
                    content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{file.mime_type};base64,{file.data_base64}"
                        }
                    })
                elif file.mime_type == "application/pdf":
                    text = await self._extract_pdf_text(file.data_base64)
                    content.append({
                        "type": "text",
                        "text": f"[Content from {file.filename}]:\n{text}"
                    })
                # ... similar for DOCX, XLSX

            result.append({"role": "user", "content": content})
            files_attached = True
        else:
            result.append(msg)

    return result
```

### PDF Extraction

```python
import base64
from io import BytesIO
from pypdf import PdfReader

def _extract_pdf_text(self, data_base64: str) -> str:
    pdf_bytes = base64.b64decode(data_base64)
    reader = PdfReader(BytesIO(pdf_bytes))
    text_parts = []
    for page in reader.pages:
        text_parts.append(page.extract_text())
    return "\n\n".join(text_parts)
```

### Error Message for Unsupported Format

"I'm using a backup system that can't read {format} files right now. Could you copy the key text instead, or try again in a moment?"

### Files to Modify

- `backend/requirements.txt` - Add pypdf, python-docx, openpyxl
- `backend/api/providers/chatgpt_provider.py` - Add multimodal and extraction methods
- `backend/tests/test_chatgpt_multimodal.py` - New test file

### Dependencies on Previous Stories

- Depends on 18.2: Uses same FileAttachment model and files parameter in LLM client

### References

- [Source: .bmad-ephemeral/stories/tech-spec-epic-18.md#Workflows-and-Sequencing]
- [Source: .bmad-ephemeral/stories/tech-spec-epic-18.md#Dependencies-and-Integrations]
- [Source: docs/epics/epic-18-file-context-sharing.md#Story-18.3]

## Dev Agent Record

### Context Reference

<!-- Path(s) to story context XML will be added here by context workflow -->

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
