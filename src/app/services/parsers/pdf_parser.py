import logging
from io import BytesIO
from statistics import median

import pdfplumber

from app.schemas.document import ContentBlock, ContentType, ProcessedDocument, SourceType
from app.services.parsers.base import BaseParser, ParseError

logger = logging.getLogger(__name__)

MIN_TEXT_LENGTH_FOR_NON_SCANNED = 100
BROKEN_LAYOUT_SHORT_LINE_RATIO = 0.5
SHORT_LINE_WORD_THRESHOLD = 3


def _table_to_block(table_rows: list[list[str | None]]) -> ContentBlock | None:
    rows = [[c if c is not None else "" for c in row] for row in table_rows if row]
    if not rows:
        return None
    headers, *body = rows
    return ContentBlock(
        type=ContentType.TABLE, text="Table", table_headers=headers, table_rows=body
    )


def _group_lines(words: list[dict]) -> list[tuple[float, list[dict]]]:
    """Group words by their vertical position ('top') into lines."""
    lines: dict[float, list[dict]] = {}
    for word in words:
        top_key = round(word["top"] / 3) * 3  # tolerance bucket
        lines.setdefault(top_key, []).append(word)
    return sorted(lines.items(), key=lambda kv: kv[0])


def _extract_page_blocks(page, body_size: float) -> tuple[list[ContentBlock], int, int]:
    blocks: list[ContentBlock] = []
    words = page.extract_words(extra_attrs=["size"])
    short_lines = 0
    total_lines = 0

    for _top, line_words in _group_lines(words):
        line_words = sorted(line_words, key=lambda w: w["x0"])
        text = " ".join(w["text"] for w in line_words).strip()
        if not text:
            continue
        total_lines += 1
        if len(text.split()) < SHORT_LINE_WORD_THRESHOLD:
            short_lines += 1
        avg_size = sum(w.get("size", body_size) for w in line_words) / len(line_words)
        if avg_size > body_size * 1.15:
            level = 1 if avg_size > body_size * 1.4 else 2
            blocks.append(ContentBlock(type=ContentType.HEADING, text=text, level=level))
        else:
            blocks.append(ContentBlock(type=ContentType.PARAGRAPH, text=text))

    for table in page.extract_tables() or []:
        block = _table_to_block(table)
        if block:
            blocks.append(block)

    return blocks, total_lines, short_lines


def _compute_body_size(pdf: pdfplumber.PDF) -> float:
    sizes: list[float] = []
    for page in pdf.pages[:5]:
        for word in page.extract_words(extra_attrs=["size"]):
            if "size" in word:
                sizes.append(word["size"])
    return median(sizes) if sizes else 10.0


def _try_docling(file_bytes: bytes, filename: str) -> ProcessedDocument | None:
    try:
        import tempfile
        from pathlib import Path

        from docling.document_converter import DocumentConverter
    except ImportError:
        logger.warning("Docling not available; skipping fallback")
        return None

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = Path(tmp.name)
        converter = DocumentConverter()
        result = converter.convert(tmp_path)
        markdown = result.document.export_to_markdown()
        if not markdown.strip():
            return None
        blocks = [
            ContentBlock(type=ContentType.PARAGRAPH, text=p.strip())
            for p in markdown.split("\n\n")
            if p.strip()
        ]
        return ProcessedDocument(
            title=filename,
            source_type=SourceType.PDF,
            raw_text=markdown,
            blocks=blocks,
            metadata={"parser": "docling"},
        )
    except Exception:  # noqa: BLE001
        logger.exception("Docling fallback failed")
        return None
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


class PDFParser(BaseParser):
    def parse(self, file_bytes: bytes, filename: str, **kwargs) -> ProcessedDocument:
        try:
            with pdfplumber.open(BytesIO(file_bytes)) as pdf:
                page_count = len(pdf.pages)
                if page_count == 0:
                    raise ParseError("PDF has no pages", SourceType.PDF.value)

                body_size = _compute_body_size(pdf)
                all_blocks: list[ContentBlock] = []
                total_lines = 0
                total_short_lines = 0
                has_tables = False

                for page in pdf.pages:
                    blocks, lines, short_lines = _extract_page_blocks(page, body_size)
                    all_blocks.extend(blocks)
                    total_lines += lines
                    total_short_lines += short_lines
                    if any(b.type == ContentType.TABLE for b in blocks):
                        has_tables = True

                raw_text = "\n\n".join(b.text for b in all_blocks)
        except ParseError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ParseError(f"Failed to parse PDF: {exc}", SourceType.PDF.value) from exc

        # Quality check: near-empty text → likely scanned, route to OCR
        if len(raw_text.strip()) < MIN_TEXT_LENGTH_FOR_NON_SCANNED:
            from app.services.parsers.ocr_parser import OCRParser

            logger.info("PDF text too short (%d chars) — routing to OCR", len(raw_text))
            return OCRParser().parse(file_bytes, filename, **kwargs)

        # Broken layout check → try Docling fallback
        if total_lines > 0 and (total_short_lines / total_lines) > BROKEN_LAYOUT_SHORT_LINE_RATIO:
            docling_result = _try_docling(file_bytes, filename)
            if docling_result is not None:
                docling_result.metadata.update(
                    {"page_count": page_count, "has_tables": has_tables}
                )
                return docling_result

        title = filename
        for block in all_blocks:
            if block.type == ContentType.HEADING:
                title = block.text
                break

        return ProcessedDocument(
            title=title,
            source_type=SourceType.PDF,
            raw_text=raw_text,
            blocks=all_blocks,
            metadata={"page_count": page_count, "has_tables": has_tables},
        )
