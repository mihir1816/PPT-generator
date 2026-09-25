from io import BytesIO

import docx
from docx.document import Document as _Document
from docx.oxml.ns import qn
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph

from app.schemas.document import ContentBlock, ContentType, ProcessedDocument, SourceType
from app.services.parsers.base import BaseParser, ParseError


def _iter_block_items(parent):
    if isinstance(parent, _Document):
        parent_elm = parent.element.body
    elif isinstance(parent, _Cell):
        parent_elm = parent._tc
    else:
        raise ValueError("Unsupported parent type for block iteration")
    for child in parent_elm.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, parent)
        elif isinstance(child, CT_Tbl):
            yield Table(child, parent)


def _heading_level(style_name: str | None) -> int | None:
    if not style_name:
        return None
    name = style_name.lower()
    if name.startswith("heading"):
        digits = "".join(c for c in name if c.isdigit())
        return int(digits) if digits else 1
    if name in ("title",):
        return 1
    return None


def _is_list_paragraph(paragraph: Paragraph) -> str | None:
    numpr = paragraph._p.find(qn("w:pPr") + "/" + qn("w:numPr"))
    style_name = (paragraph.style.name or "").lower() if paragraph.style else ""
    if numpr is not None or "list" in style_name:
        if "number" in style_name or "ordered" in style_name:
            return "numbered"
        return "bullet"
    return None


def _paragraph_has_image(paragraph: Paragraph) -> bool:
    return bool(paragraph._p.findall(f".//{qn('w:drawing')}"))


def _table_to_block(table: Table) -> ContentBlock:
    rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
    headers = rows[0] if rows else []
    body = rows[1:] if len(rows) > 1 else []
    return ContentBlock(
        type=ContentType.TABLE, text="Table", table_headers=headers, table_rows=body
    )


class DocxParser(BaseParser):
    def parse(self, file_bytes: bytes, filename: str, **kwargs) -> ProcessedDocument:
        try:
            document = docx.Document(BytesIO(file_bytes))
        except Exception as exc:  # noqa: BLE001
            raise ParseError(f"Failed to open DOCX: {exc}", SourceType.DOCX.value) from exc

        blocks: list[ContentBlock] = []
        raw_parts: list[str] = []
        paragraph_count = 0
        table_count = 0
        title: str | None = None

        pending_list_items: list[str] = []
        pending_list_type: str | None = None

        def flush_list() -> None:
            nonlocal pending_list_items, pending_list_type
            if pending_list_items:
                block_type = (
                    ContentType.NUMBERED_LIST
                    if pending_list_type == "numbered"
                    else ContentType.BULLET_LIST
                )
                blocks.append(
                    ContentBlock(
                        type=block_type,
                        text=pending_list_items[0],
                        items=list(pending_list_items),
                    )
                )
            pending_list_items = []
            pending_list_type = None

        for item in _iter_block_items(document):
            if isinstance(item, Paragraph):
                text = item.text.strip()
                if _paragraph_has_image(item):
                    flush_list()
                    blocks.append(
                        ContentBlock(
                            type=ContentType.IMAGE_DESCRIPTION,
                            text=text or "Image in document",
                        )
                    )
                if not text:
                    continue
                paragraph_count += 1
                raw_parts.append(text)
                level = _heading_level(item.style.name if item.style else None)
                list_kind = _is_list_paragraph(item)
                if level:
                    flush_list()
                    blocks.append(
                        ContentBlock(type=ContentType.HEADING, text=text, level=level)
                    )
                    if title is None:
                        title = text
                elif list_kind:
                    if pending_list_type and pending_list_type != list_kind:
                        flush_list()
                    pending_list_type = list_kind
                    pending_list_items.append(text)
                else:
                    flush_list()
                    blocks.append(ContentBlock(type=ContentType.PARAGRAPH, text=text))
            elif isinstance(item, Table):
                flush_list()
                table_count += 1
                block = _table_to_block(item)
                blocks.append(block)
                raw_parts.append(block.text)

        flush_list()

        return ProcessedDocument(
            title=title or filename,
            source_type=SourceType.DOCX,
            raw_text="\n\n".join(raw_parts),
            blocks=blocks,
            metadata={"paragraph_count": paragraph_count, "table_count": table_count},
        )
