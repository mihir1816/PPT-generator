import io
import logging
from datetime import datetime, timezone

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Emu, Inches, Pt

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Theme constants
# ---------------------------------------------------------------------------

COLOR_PRIMARY = RGBColor(0x1E, 0x29, 0x3B)     # dark navy for text
COLOR_ACCENT = RGBColor(0x25, 0x63, 0xEB)       # blue accent
COLOR_LIGHT = RGBColor(0xFF, 0xFF, 0xFF)         # white
COLOR_MUTED = RGBColor(0x64, 0x74, 0x8B)         # gray for subtitles
COLOR_TABLE_HEADER = RGBColor(0x1E, 0x40, 0xAF)  # darker blue for table headers
COLOR_TABLE_ALT = RGBColor(0xF1, 0xF5, 0xF9)     # light gray alternating rows
COLOR_BORDER = RGBColor(0xCB, 0xD5, 0xE1)        # light border
COLOR_PLACEHOLDER_BG = RGBColor(0xF8, 0xFA, 0xFC) # very light bg for placeholders

FONT_TITLE = "Calibri"
FONT_BODY = "Calibri"

SLIDE_WIDTH = Inches(13.333)
SLIDE_HEIGHT = Inches(7.5)

MARGIN_LEFT = Inches(0.8)
MARGIN_TOP = Inches(0.6)
CONTENT_WIDTH = Inches(11.7)
TITLE_HEIGHT = Inches(1.0)
BODY_TOP = Inches(1.8)
BODY_HEIGHT = Inches(5.0)


LAYOUT_MAP = {
    "title": "_add_title_slide",
    "bullet": "_add_bullet_slide",
    "two_column": "_add_two_column_slide",
    "table": "_add_table_slide",
    "section_header": "_add_section_header_slide",
    "image_placeholder": "_add_image_placeholder_slide",
}


class PPTXExporter:

    def export_deck(
        self,
        slides: list,
        preferences: dict | None = None,
        title: str = "Presentation",
    ) -> bytes:
        prs = Presentation()
        prs.slide_width = SLIDE_WIDTH
        prs.slide_height = SLIDE_HEIGHT

        for slide_data in sorted(slides, key=lambda s: s.position):
            layout_hint = getattr(slide_data, "layout_hint", "bullet") or "bullet"
            method_name = LAYOUT_MAP.get(layout_hint, "_add_bullet_slide")
            method = getattr(self, method_name)
            method(prs, slide_data)

        buf = io.BytesIO()
        prs.save(buf)
        return buf.getvalue()

    @staticmethod
    def make_filename(title: str) -> str:
        safe = "".join(c if c.isalnum() or c in " _-" else "_" for c in title)
        safe = safe.strip()[:60] or "presentation"
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        return f"{safe}_{ts}.pptx"

    # ------------------------------------------------------------------
    # Layout builders
    # ------------------------------------------------------------------

    def _add_title_slide(self, prs: Presentation, data) -> None:
        slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank

        # Title
        title_box = slide.shapes.add_textbox(
            MARGIN_LEFT, Inches(2.2), CONTENT_WIDTH, Inches(1.5),
        )
        tf = title_box.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = data.title
        p.font.size = Pt(40)
        p.font.bold = True
        p.font.color.rgb = COLOR_PRIMARY
        p.font.name = FONT_TITLE
        p.alignment = PP_ALIGN.CENTER

        # Subtitle / body
        if data.body:
            sub_box = slide.shapes.add_textbox(
                MARGIN_LEFT, Inches(4.0), CONTENT_WIDTH, Inches(1.2),
            )
            tf2 = sub_box.text_frame
            tf2.word_wrap = True
            p2 = tf2.paragraphs[0]
            p2.text = data.body
            p2.font.size = Pt(20)
            p2.font.color.rgb = COLOR_MUTED
            p2.font.name = FONT_BODY
            p2.alignment = PP_ALIGN.CENTER

        self._add_speaker_notes(slide, data.speaker_notes)

    def _add_bullet_slide(self, prs: Presentation, data) -> None:
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        self._add_slide_title(slide, data.title)

        body_box = slide.shapes.add_textbox(
            MARGIN_LEFT, BODY_TOP, CONTENT_WIDTH, BODY_HEIGHT,
        )
        tf = body_box.text_frame
        tf.word_wrap = True

        first_para_used = False
        if data.body:
            p = tf.paragraphs[0]
            p.text = data.body
            self._style_body(p)
            first_para_used = True

        bullets = data.bullet_points or []
        for point in bullets:
            if first_para_used:
                p = tf.add_paragraph()
            else:
                p = tf.paragraphs[0]
                first_para_used = True
            p.text = point
            p.font.size = Pt(18)
            p.font.color.rgb = COLOR_PRIMARY
            p.font.name = FONT_BODY
            p.level = 0
            p.space_after = Pt(8)

        self._add_speaker_notes(slide, data.speaker_notes)

    def _add_two_column_slide(self, prs: Presentation, data) -> None:
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        self._add_slide_title(slide, data.title)

        col_width = Inches(5.5)
        gap = Inches(0.7)

        bullets = data.bullet_points or []
        mid = (len(bullets) + 1) // 2
        left_items = bullets[:mid]
        right_items = bullets[mid:]

        # Left column
        left_box = slide.shapes.add_textbox(MARGIN_LEFT, BODY_TOP, col_width, BODY_HEIGHT)
        self._fill_bullets(left_box.text_frame, left_items, data.body)

        # Right column
        right_left = MARGIN_LEFT + col_width + gap
        right_box = slide.shapes.add_textbox(right_left, BODY_TOP, col_width, BODY_HEIGHT)
        self._fill_bullets(right_box.text_frame, right_items)

        self._add_speaker_notes(slide, data.speaker_notes)

    def _add_table_slide(self, prs: Presentation, data) -> None:
        table_data = self._get_table_data(data)
        if not table_data:
            self._add_bullet_slide(prs, data)
            return

        slide = prs.slides.add_slide(prs.slide_layouts[6])
        self._add_slide_title(slide, data.title)

        headers = table_data.get("headers", [])
        rows = table_data.get("rows", [])

        if not headers and not rows:
            self._add_fallback_body(slide, data)
            self._add_speaker_notes(slide, data.speaker_notes)
            return

        num_rows = len(rows) + 1
        num_cols = max(len(headers), max((len(r) for r in rows), default=1))
        num_cols = max(num_cols, 1)

        col_w = min(CONTENT_WIDTH / num_cols, Inches(4.0))
        table_w = Emu(int(col_w) * num_cols)
        table_h = Inches(0.4) * num_rows

        table_shape = slide.shapes.add_table(
            num_rows, num_cols,
            MARGIN_LEFT, BODY_TOP, table_w, table_h,
        )
        table = table_shape.table

        # Header row
        for ci in range(num_cols):
            cell = table.cell(0, ci)
            cell.text = headers[ci] if ci < len(headers) else ""
            for paragraph in cell.text_frame.paragraphs:
                paragraph.font.size = Pt(14)
                paragraph.font.bold = True
                paragraph.font.color.rgb = COLOR_LIGHT
                paragraph.font.name = FONT_BODY
            cell.fill.solid()
            cell.fill.fore_color.rgb = COLOR_TABLE_HEADER

        # Data rows
        for ri, row in enumerate(rows):
            for ci in range(num_cols):
                cell = table.cell(ri + 1, ci)
                cell.text = row[ci] if ci < len(row) else ""
                for paragraph in cell.text_frame.paragraphs:
                    paragraph.font.size = Pt(13)
                    paragraph.font.color.rgb = COLOR_PRIMARY
                    paragraph.font.name = FONT_BODY
                if ri % 2 == 1:
                    cell.fill.solid()
                    cell.fill.fore_color.rgb = COLOR_TABLE_ALT

        self._add_speaker_notes(slide, data.speaker_notes)

    def _add_section_header_slide(self, prs: Presentation, data) -> None:
        slide = prs.slides.add_slide(prs.slide_layouts[6])

        # Accent bar
        bar = slide.shapes.add_shape(
            1, Inches(0), Inches(3.0), SLIDE_WIDTH, Inches(0.08),
        )
        bar.fill.solid()
        bar.fill.fore_color.rgb = COLOR_ACCENT
        bar.line.fill.background()

        title_box = slide.shapes.add_textbox(
            MARGIN_LEFT, Inches(2.5), CONTENT_WIDTH, Inches(2.0),
        )
        tf = title_box.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = data.title
        p.font.size = Pt(36)
        p.font.bold = True
        p.font.color.rgb = COLOR_PRIMARY
        p.font.name = FONT_TITLE
        p.alignment = PP_ALIGN.CENTER

        if data.body:
            p2 = tf.add_paragraph()
            p2.text = data.body
            p2.font.size = Pt(18)
            p2.font.color.rgb = COLOR_MUTED
            p2.font.name = FONT_BODY
            p2.alignment = PP_ALIGN.CENTER

        self._add_speaker_notes(slide, data.speaker_notes)

    def _add_image_placeholder_slide(self, prs: Presentation, data) -> None:
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        self._add_slide_title(slide, data.title)

        if data.body:
            body_box = slide.shapes.add_textbox(
                MARGIN_LEFT, BODY_TOP, CONTENT_WIDTH, Inches(1.2),
            )
            tf = body_box.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            p.text = data.body
            self._style_body(p)

        # Placeholder rectangle
        ph_top = Inches(3.2) if data.body else BODY_TOP
        ph_width = Inches(8.0)
        ph_height = Inches(4.0)
        ph_left = MARGIN_LEFT + (CONTENT_WIDTH - ph_width) / 2

        shape = slide.shapes.add_shape(1, ph_left, ph_top, ph_width, ph_height)
        shape.fill.solid()
        shape.fill.fore_color.rgb = COLOR_PLACEHOLDER_BG
        shape.line.color.rgb = COLOR_BORDER
        shape.line.dash_style = 4  # MSO_LINE_DASH_STYLE.DASH

        tf = shape.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = "[Insert Image Here]"
        p.font.size = Pt(18)
        p.font.color.rgb = COLOR_MUTED
        p.font.name = FONT_BODY
        p.alignment = PP_ALIGN.CENTER
        tf.paragraphs[0].space_before = Pt(60)

        self._add_speaker_notes(slide, data.speaker_notes)

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _add_slide_title(slide, text: str) -> None:
        title_box = slide.shapes.add_textbox(
            MARGIN_LEFT, MARGIN_TOP, CONTENT_WIDTH, TITLE_HEIGHT,
        )
        tf = title_box.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = text
        p.font.size = Pt(28)
        p.font.bold = True
        p.font.color.rgb = COLOR_PRIMARY
        p.font.name = FONT_TITLE

    @staticmethod
    def _add_speaker_notes(slide, notes_text: str) -> None:
        if not notes_text:
            return
        notes_slide = slide.notes_slide
        notes_slide.notes_text_frame.text = notes_text

    @staticmethod
    def _style_body(paragraph) -> None:
        paragraph.font.size = Pt(16)
        paragraph.font.color.rgb = COLOR_MUTED
        paragraph.font.name = FONT_BODY

    @staticmethod
    def _fill_bullets(text_frame, items: list[str], body: str = "") -> None:
        text_frame.word_wrap = True
        first = True
        if body:
            p = text_frame.paragraphs[0]
            p.text = body
            p.font.size = Pt(16)
            p.font.color.rgb = COLOR_MUTED
            p.font.name = FONT_BODY
            first = False

        for item in items:
            if first:
                p = text_frame.paragraphs[0]
                first = False
            else:
                p = text_frame.add_paragraph()
            p.text = item
            p.font.size = Pt(18)
            p.font.color.rgb = COLOR_PRIMARY
            p.font.name = FONT_BODY
            p.level = 0
            p.space_after = Pt(8)

    @staticmethod
    def _get_table_data(data) -> dict | None:
        td = getattr(data, "table_data", None)
        if td is None:
            return None
        if isinstance(td, dict):
            return td
        if hasattr(td, "model_dump"):
            return td.model_dump()
        return None

    @staticmethod
    def _add_fallback_body(slide, data) -> None:
        body_box = slide.shapes.add_textbox(
            MARGIN_LEFT, BODY_TOP, CONTENT_WIDTH, BODY_HEIGHT,
        )
        tf = body_box.text_frame
        tf.word_wrap = True
        if data.body:
            tf.paragraphs[0].text = data.body
        for bp in (data.bullet_points or []):
            p = tf.add_paragraph()
            p.text = bp
            p.font.size = Pt(18)
            p.font.color.rgb = COLOR_PRIMARY
            p.font.name = FONT_BODY
