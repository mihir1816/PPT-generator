# Session 11 — PPTX Export

## Goal
Build the PowerPoint export engine. Takes finalized slide content from DB and generates a downloadable .pptx file with proper layouts, formatting, tables, and speaker notes. After this session, clicking "Export" produces a real PowerPoint file.

## Read First
- `docs/sessions/SESSION_TRACKER.md` — confirm Sessions 01-10 complete
- `src/app/models/slide.py` — Slide model (title, body, bullet_points, table_data, speaker_notes, layout_hint)
- `src/app/schemas/deck.py` — SlideContent, TeacherPreferences
- `src/app/services/storage.py` — MinIO upload for generated file
- `src/app/services/crud.py` — get_slides_by_deck, get_deck

## Non-Negotiable Rules
- Use python-pptx (MIT) only
- Support all layout types: title, bullet, two_column, table, image_placeholder, section_header
- Tables that span multiple slides → separate table per slide with continuation header
- Speaker notes on every slide
- Export to MinIO → return presigned download URL
- Clean, professional default theme (no garish colors)
- File named: `{deck_title}_{timestamp}.pptx`

## Files to Create

### `services/exporter.py` — PPTX Export Service
```python
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.enum.text import PP_ALIGN
from pptx.dml.color import RGBColor

class PPTXExporter:
    # Slide dimensions: widescreen 16:9
    SLIDE_WIDTH = Inches(13.333)
    SLIDE_HEIGHT = Inches(7.5)

    def __init__(self):
        self.prs = Presentation()
        self.prs.slide_width = self.SLIDE_WIDTH
        self.prs.slide_height = self.SLIDE_HEIGHT

    def export_deck(self, slides: list[Slide], preferences: TeacherPreferences,
                    title: str) -> bytes:
        """
        Generate complete PPTX from slide data.
        Returns: bytes of the .pptx file
        
        Flow:
        1. Set up default theme/colors
        2. For each slide (ordered by position):
           - Route to layout builder based on layout_hint
           - Add content
           - Add speaker notes
        3. Return prs as bytes (BytesIO)
        """

    def _add_title_slide(self, slide_data: Slide):
        """
        Layout: centered title + subtitle
        - Title: large, bold, centered
        - Subtitle: smaller, below title
        """

    def _add_bullet_slide(self, slide_data: Slide):
        """
        Layout: title at top + bullet points
        - Title bar
        - Bullet points with proper indentation
        - Body text if present (below bullets)
        """

    def _add_two_column_slide(self, slide_data: Slide):
        """
        Layout: title + two content columns
        - Split bullet_points into two halves
        - Or: body on left, bullets on right
        """

    def _add_table_slide(self, slide_data: Slide):
        """
        Layout: title + table
        - Parse table_data JSON: {headers: [...], rows: [[...], ...]}
        - Create table with proper column widths
        - Style header row (bold, colored background)
        - Handle continuation: add "(continued)" to title if table_continuation
        """

    def _add_section_header_slide(self, slide_data: Slide):
        """
        Layout: large centered section title
        - Minimal text, acts as separator between topics
        """

    def _add_image_placeholder_slide(self, slide_data: Slide):
        """
        Layout: title + body text + placeholder box with "Insert Image Here"
        - Gray dashed border rectangle as placeholder
        - Text instruction below placeholder
        """

    def _add_speaker_notes(self, slide, notes_text: str):
        """Add speaker notes to slide."""
        notes_slide = slide.notes_slide
        notes_slide.notes_text_frame.text = notes_text

    def _apply_theme(self):
        """
        Set default colors and fonts:
        - Title font: Calibri, 28-36pt, dark color
        - Body font: Calibri, 18-20pt
        - Accent color: #2563EB (blue)
        - Background: white
        - Table header: accent color background, white text
        """

LAYOUT_MAP = {
    "title": "_add_title_slide",
    "bullet": "_add_bullet_slide",
    "two_column": "_add_two_column_slide",
    "table": "_add_table_slide",
    "section_header": "_add_section_header_slide",
    "image_placeholder": "_add_image_placeholder_slide",
}
```

### Update `api/export.py` — Export Endpoint
```
POST /api/decks/{deck_id}/export
    Precondition: deck has generated slides
    Flow:
      1. Load deck + all slides (ordered by position)
      2. exporter.export_deck(slides, preferences, title) → bytes
      3. Upload to MinIO: exports/{deck_id}/{filename}.pptx
      4. Get presigned URL (1 hour expiry)
      5. Return { download_url, filename, file_size }

GET /api/decks/{deck_id}/export/download
    Flow:
      1. Load export from MinIO
      2. Return FileResponse with .pptx content-type
```

Register export router in `main.py`.

## Flow
```
1. Create services/exporter.py
2. Create api/export.py
3. Register router in main.py
4. Test export with sample slides
5. Download and open in PowerPoint/LibreOffice
```

## Verification
```bash
# Prerequisites: deck with completed slides (from Session 09/10)

# 1. Export to PPTX
curl -X POST http://localhost:8200/api/decks/<deck_id>/export
# Expected: {"download_url": "http://...", "filename": "..._2026xxxx.pptx", "file_size": NNNN}

# 2. Download the file
curl -o test_output.pptx "<download_url from step 1>"
# Expected: valid .pptx file downloads

# 3. Verify file is valid PPTX
docker compose exec app python -c "
from pptx import Presentation
prs = Presentation('/path/to/test_output.pptx')
print(f'Slides: {len(prs.slides)}')
for i, slide in enumerate(prs.slides):
    title = slide.shapes.title.text if slide.shapes.title else 'No title'
    notes = slide.notes_slide.notes_text_frame.text if slide.has_notes_slide else ''
    print(f'  Slide {i+1}: {title} | Notes: {notes[:50]}...')
print('PPTX valid')
"
# Expected: correct slide count, titles match, speaker notes present

# 4. Verify table slides
# If deck has table slides, check table renders in the PPTX

# 5. Open in PowerPoint / LibreOffice Impress
# Manual check: slides render correctly, formatting looks professional

# 6. Check MinIO has the exported file
curl http://localhost:9000/tcg-uploads/exports/ 2>/dev/null || echo "Check MinIO console at :9001"
```

## On Completion
Update `SESSION_TRACKER.md`: mark Session 11 ✅, note PPTX export working, next → Session 12
