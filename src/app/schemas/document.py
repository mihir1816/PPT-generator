from enum import StrEnum

from pydantic import BaseModel, Field


class SourceType(StrEnum):
    PDF = "pdf"
    PLAIN_TEXT = "plain_text"
    WEB_URL = "web_url"
    PPTX = "pptx"
    DOCX = "docx"
    IMAGE_OCR = "image_ocr"


class ContentType(StrEnum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    BULLET_LIST = "bullet_list"
    NUMBERED_LIST = "numbered_list"
    TABLE = "table"
    IMAGE_DESCRIPTION = "image_description"
    CODE_BLOCK = "code_block"
    QUOTE = "quote"


class ContentBlock(BaseModel):
    type: ContentType
    text: str
    level: int | None = None  # heading level (1-6) or list nesting depth
    items: list[str] | None = None  # for bullet/numbered lists
    table_headers: list[str] | None = None
    table_rows: list[list[str]] | None = None
    metadata: dict = Field(default_factory=dict)


class ProcessedDocument(BaseModel):
    title: str | None = None
    source_type: SourceType
    raw_text: str
    blocks: list[ContentBlock] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)

    def to_markdown(self) -> str:
        parts: list[str] = []
        for block in self.blocks:
            if block.type == ContentType.HEADING:
                level = block.level or 1
                parts.append(f"{'#' * min(level, 6)} {block.text}")
            elif block.type == ContentType.PARAGRAPH:
                parts.append(block.text)
            elif block.type == ContentType.BULLET_LIST:
                items = block.items or [block.text]
                parts.append("\n".join(f"- {item}" for item in items))
            elif block.type == ContentType.NUMBERED_LIST:
                items = block.items or [block.text]
                parts.append(
                    "\n".join(f"{i + 1}. {item}" for i, item in enumerate(items))
                )
            elif block.type == ContentType.TABLE:
                parts.append(_table_to_markdown(block.table_headers, block.table_rows))
            elif block.type == ContentType.IMAGE_DESCRIPTION:
                parts.append(f"*[Image: {block.text}]*")
            elif block.type == ContentType.CODE_BLOCK:
                parts.append(f"```\n{block.text}\n```")
            elif block.type == ContentType.QUOTE:
                parts.append(f"> {block.text}")
        return "\n\n".join(p for p in parts if p)


def _table_to_markdown(
    headers: list[str] | None, rows: list[list[str]] | None
) -> str:
    if not headers and not rows:
        return ""
    headers = headers or []
    rows = rows or []
    lines = []
    if headers:
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)
