# Session 03 — Input Processing Pipeline

## Goal
Build parsers for all 6 input types (PDF, text, DOCX, web URL, PPTX, images/OCR). Each returns `ProcessedDocument`. Wire into Celery task for async processing. Add basic upload API endpoint. After this session, uploading any file triggers parsing and stores the result in DB.

## Read First
- `docs/sessions/SESSION_TRACKER.md` — confirm Sessions 01-02 complete
- `src/app/schemas/document.py` — ProcessedDocument, ContentBlock, SourceType
- `src/app/models/upload.py`, `models/document.py` — DB models
- `src/app/services/storage.py` — MinIO download
- `src/app/services/crud.py` — create_upload, create_document
- `docs/INPUT_PROCESSING_RESEARCH.md` — full research

## Non-Negotiable Rules
- Every parser returns `ProcessedDocument` — no exceptions
- No PyMuPDF (AGPL) — pdfplumber + Docling only
- No Surya (GPL), No PaddleOCR (too heavy ~3GB) — Tesseract + pytesseract (Apache 2.0) for OCR
- Validate file size against `MAX_UPLOAD_SIZE_MB` before storing in MinIO
- All parsing in Celery worker (never block API)
- Each parser = its own file — easy to swap later
- Parsers must NOT import FastAPI
- Handle errors gracefully: return partial result or raise typed ParseError

## Dependencies (already in pyproject.toml from Session 01)
pdfplumber, docling, python-pptx, python-docx, trafilatura, pytesseract, Pillow, python-magic
System dep: `tesseract-ocr` (installed in Dockerfile)

## Files to Create

### `services/parsers/base.py`
```python
class ParseError(Exception):
    def __init__(self, message: str, source_type: str, partial_result: ProcessedDocument | None = None): ...

class BaseParser(ABC):
    @abstractmethod
    def parse(self, file_bytes: bytes, filename: str, **kwargs) -> ProcessedDocument: ...
```

### `services/parsers/pdf_parser.py`
Strategy: pdfplumber first → quality check → Docling fallback → OCR if scanned
```
1. pdfplumber.open(BytesIO(file_bytes))
2. Extract text page-by-page
3. Detect tables via page.extract_tables() → markdown tables
4. Detect headings via font-size heuristics (largest = h1)
5. Quality check: if text < 100 chars and pages > 0 → route to OCR
6. If broken layout (>50% lines < 3 words) → try Docling
7. Return ProcessedDocument with metadata: {page_count, has_tables}
```

### `services/parsers/text_parser.py`
Handles .txt, .md, .csv
```
1. Decode bytes (utf-8, fallback latin-1)
2. Detect format: markdown (has #/```), CSV (has commas+rows), plain
3. Markdown: split by headings → HEADING + PARAGRAPH blocks
4. CSV: parse as TABLE block
5. Plain: split by double newlines → PARAGRAPH blocks
```

### `services/parsers/docx_parser.py`
Uses python-docx
```
1. docx.Document(BytesIO(file_bytes))
2. Iterate paragraphs: detect heading styles (Heading 1/2/3) → HEADING blocks
3. Normal paragraphs → PARAGRAPH blocks
4. Detect bullet/number lists by style → BULLET_LIST / NUMBERED_LIST
5. Tables → TABLE blocks (convert to markdown)
6. Images → IMAGE_DESCRIPTION with alt text
7. Metadata: {paragraph_count, table_count}
```

### `services/parsers/web_parser.py`
Uses trafilatura
```
1. Receive URL (not file_bytes)
2. trafilatura.fetch_url(url) → HTML
3. trafilatura.extract(html, include_tables=True, include_links=True) → text
4. If None → retry with favor_recall=True
5. If still None → raise ParseError
6. Split into ContentBlocks
7. Metadata: {url, domain}
```

### `services/parsers/pptx_parser.py`
Uses python-pptx
```
1. pptx.Presentation(BytesIO(file_bytes))
2. For each slide:
   - Title shape → HEADING
   - Text frames → PARAGRAPH / BULLET_LIST
   - Tables → TABLE (markdown)
   - Images → IMAGE_DESCRIPTION (alt text or "Image on slide N")
3. Metadata: {slide_count}
```

### `services/parsers/ocr_parser.py`
Uses Tesseract via pytesseract (~50MB vs PaddleOCR's ~3GB)
```
1. If PDF → convert pages to images (pdfplumber page.to_image())
2. If image file → load with PIL
3. pytesseract.image_to_data(image, output_type=Output.DICT)
4. Filter by confidence > 50 → sort top-to-bottom by block/line
5. Group words by block_num → PARAGRAPH blocks
6. Metadata: {ocr_confidence_avg, page_count}
```
Tesseract is a system package (installed in Dockerfile). No Python model loading needed — much lighter than PaddleOCR.

### `services/parsers/router.py`
```python
PARSER_MAP = {
    SourceType.PDF: PDFParser,
    SourceType.PLAIN_TEXT: TextParser,
    SourceType.DOCX: DocxParser,
    SourceType.WEB_URL: WebParser,
    SourceType.PPTX: PPTXParser,
    SourceType.IMAGE_OCR: OCRParser,
}

def detect_source_type(filename: str, mime_type: str | None) -> SourceType:
    ext = filename.rsplit(".", 1)[-1].lower()
    # pdf→PDF, pptx→PPTX, docx→DOCX, txt/md/csv→PLAIN_TEXT
    # jpg/png/tiff/bmp/webp→IMAGE_OCR, http/https→WEB_URL

def parse_upload(file_bytes: bytes, filename: str, source_type: SourceType) -> ProcessedDocument:
    return PARSER_MAP[source_type]().parse(file_bytes, filename)
```

### `tasks/process_upload.py` — Celery task
```python
@celery_app.task(bind=True, max_retries=2)
def process_upload_task(self, upload_id: str):
    1. Fetch Upload from DB (sync session)
    2. Download file from MinIO (or use URL for web type)
    3. parse_upload(file_bytes, filename, source_type) → ProcessedDocument
    4. Create Document record (raw_text, content_blocks JSON, markdown_content)
    5. Update Upload status → "completed"
    On error: status → "failed" with error_message
```
Uses SYNC database session (Celery workers are sync).

### `api/upload.py` — Basic endpoints
```
POST /api/upload         — file upload → validate size → MinIO → Celery task → return UploadResponse
POST /api/upload-url     — URL → Celery task → return UploadResponse
GET  /api/upload/{id}    — return status + document_id if completed
GET  /api/documents/{id} — return document info (title, source_type, block count, text preview)
```
**File size validation** (in POST /api/upload):
```python
if file.size and file.size > settings.max_upload_bytes:
    raise HTTPException(413, f"File too large. Max {settings.MAX_UPLOAD_SIZE_MB}MB")
```
Register router in `main.py`. Use `Depends()` from `deps.py` for StorageService access.

## Flow
```
1. Add SourceType.DOCX to schemas/document.py if not present
2. Create services/parsers/ directory with all 7 files
3. Create tasks/process_upload.py
4. Add sync session factory to core/database.py (for Celery)
5. Create api/upload.py with 4 endpoints
6. Register router in main.py
7. Rebuild: docker compose up -d --build app celery-worker
8. Test each parser
```

## Verification
```bash
# 1. Rebuild
docker compose up -d --build app celery-worker

# 2. PDF upload
curl -X POST http://localhost:8200/api/upload -F "file=@sample.pdf"
# → {"file_id":"<uuid>","filename":"sample.pdf","status":"pending"}
# Wait 15s, then:
curl http://localhost:8200/api/upload/<file_id>
# → {"status":"completed","document_id":"<uuid>"}

# 3. DOCX upload
curl -X POST http://localhost:8200/api/upload -F "file=@sample.docx"
# → status eventually "completed"

# 4. Text upload
curl -X POST http://localhost:8200/api/upload -F "file=@sample.txt"

# 5. URL upload
curl -X POST http://localhost:8200/api/upload-url \
  -H "Content-Type: application/json" \
  -d '{"url":"https://en.wikipedia.org/wiki/Photosynthesis"}'

# 6. PPTX upload
curl -X POST http://localhost:8200/api/upload -F "file=@sample.pptx"

# 7. Verify document in DB
docker compose exec postgres psql -U tcg_user -d teacher_content_gen \
  -c "SELECT id, title, source_type, char_length(raw_text) as text_len FROM documents;"
# Expected: rows with non-zero text_len

# 8. Celery logs clean
docker compose logs celery-worker --tail=30
# Expected: task succeeded, no tracebacks

# 9. Direct parser test
docker compose exec app python -c "
from app.services.parsers.text_parser import TextParser
doc = TextParser().parse(b'# Hello\n\nThis is a test paragraph.\n\n## Section 2\n\nMore text here.', 'test.md')
print(f'Blocks: {len(doc.blocks)}, Type: {doc.blocks[0].type}')
assert len(doc.blocks) >= 3
print('Parser OK')
"
```

## On Completion
Update `SESSION_TRACKER.md`: mark Session 03 ✅, list parser files, note which parsers tested, next → Session 04
