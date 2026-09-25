import csv
import io

from app.schemas.document import ContentBlock, ContentType, ProcessedDocument, SourceType
from app.services.parsers.base import BaseParser, ParseError


def _decode(file_bytes: bytes) -> str:
    for encoding in ("utf-8", "latin-1"):
        try:
            return file_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ParseError("Could not decode text file", SourceType.PLAIN_TEXT.value)


def _detect_format(text: str) -> str:
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return "plain"
    if "```" in text or any(line.lstrip().startswith("#") for line in lines):
        return "markdown"
    comma_lines = [line for line in lines if "," in line]
    if len(comma_lines) >= max(2, len(lines) * 0.6):
        try:
            reader = csv.reader(io.StringIO(text))
            rows = list(reader)
            widths = {len(r) for r in rows if r}
            if len(widths) == 1 and next(iter(widths)) > 1:
                return "csv"
        except csv.Error:
            pass
    return "plain"


def _parse_markdown(text: str) -> list[ContentBlock]:
    blocks: list[ContentBlock] = []
    paragraph_buffer: list[str] = []

    def flush_paragraph() -> None:
        if paragraph_buffer:
            content = "\n".join(paragraph_buffer).strip()
            if content:
                blocks.append(ContentBlock(type=ContentType.PARAGRAPH, text=content))
            paragraph_buffer.clear()

    in_code_block = False
    code_buffer: list[str] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_code_block:
                blocks.append(
                    ContentBlock(
                        type=ContentType.CODE_BLOCK, text="\n".join(code_buffer)
                    )
                )
                code_buffer = []
                in_code_block = False
            else:
                flush_paragraph()
                in_code_block = True
            continue
        if in_code_block:
            code_buffer.append(line)
            continue
        if stripped.startswith("#"):
            flush_paragraph()
            level = len(stripped) - len(stripped.lstrip("#"))
            heading_text = stripped.lstrip("#").strip()
            blocks.append(
                ContentBlock(type=ContentType.HEADING, text=heading_text, level=level)
            )
        elif stripped.startswith(("- ", "* ")):
            flush_paragraph()
            item = stripped[2:].strip()
            if blocks and blocks[-1].type == ContentType.BULLET_LIST:
                blocks[-1].items.append(item)
            else:
                blocks.append(
                    ContentBlock(
                        type=ContentType.BULLET_LIST, text=item, items=[item]
                    )
                )
        elif stripped == "":
            flush_paragraph()
        else:
            paragraph_buffer.append(line)
    flush_paragraph()
    return blocks


def _parse_csv(text: str) -> list[ContentBlock]:
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return []
    headers, *body = rows
    return [
        ContentBlock(
            type=ContentType.TABLE,
            text="CSV table",
            table_headers=headers,
            table_rows=body,
        )
    ]


def _parse_plain(text: str) -> list[ContentBlock]:
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    return [ContentBlock(type=ContentType.PARAGRAPH, text=p) for p in paragraphs]


class TextParser(BaseParser):
    def parse(self, file_bytes: bytes, filename: str, **kwargs) -> ProcessedDocument:
        text = _decode(file_bytes)
        fmt = _detect_format(text)
        if fmt == "markdown":
            blocks = _parse_markdown(text)
        elif fmt == "csv":
            blocks = _parse_csv(text)
        else:
            blocks = _parse_plain(text)

        title = None
        for block in blocks:
            if block.type == ContentType.HEADING:
                title = block.text
                break

        return ProcessedDocument(
            title=title or filename,
            source_type=SourceType.PLAIN_TEXT,
            raw_text=text,
            blocks=blocks,
            metadata={"detected_format": fmt},
        )
