from app.schemas.document import ProcessedDocument, SourceType
from app.services.parsers.base import BaseParser, ParseError
from app.services.parsers.docx_parser import DocxParser
from app.services.parsers.ocr_parser import IMAGE_EXTENSIONS, OCRParser
from app.services.parsers.pdf_parser import PDFParser
from app.services.parsers.pptx_parser import PPTXParser
from app.services.parsers.text_parser import TextParser
from app.services.parsers.web_parser import WebParser

PARSER_MAP: dict[SourceType, type[BaseParser]] = {
    SourceType.PDF: PDFParser,
    SourceType.PLAIN_TEXT: TextParser,
    SourceType.DOCX: DocxParser,
    SourceType.WEB_URL: WebParser,
    SourceType.PPTX: PPTXParser,
    SourceType.IMAGE_OCR: OCRParser,
}

_TEXT_EXTENSIONS = {"txt", "md", "csv"}


def detect_source_type(filename: str, mime_type: str | None) -> SourceType:
    if filename.startswith("http://") or filename.startswith("https://"):
        return SourceType.WEB_URL

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext == "pdf":
        return SourceType.PDF
    if ext == "pptx":
        return SourceType.PPTX
    if ext == "docx":
        return SourceType.DOCX
    if ext in _TEXT_EXTENSIONS:
        return SourceType.PLAIN_TEXT
    if ext in IMAGE_EXTENSIONS:
        return SourceType.IMAGE_OCR

    if mime_type:
        if mime_type == "application/pdf":
            return SourceType.PDF
        if "wordprocessingml" in mime_type:
            return SourceType.DOCX
        if "presentationml" in mime_type:
            return SourceType.PPTX
        if mime_type.startswith("text/"):
            return SourceType.PLAIN_TEXT
        if mime_type.startswith("image/"):
            return SourceType.IMAGE_OCR

    raise ParseError(f"Could not detect source type for '{filename}'", "unknown")


def parse_upload(
    file_bytes: bytes, filename: str, source_type: SourceType, **kwargs
) -> ProcessedDocument:
    parser_cls = PARSER_MAP[source_type]
    return parser_cls().parse(file_bytes, filename, **kwargs)
