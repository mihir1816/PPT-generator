from urllib.parse import urlparse

import trafilatura

from app.schemas.document import ContentBlock, ContentType, ProcessedDocument, SourceType
from app.services.parsers.base import BaseParser, ParseError


class WebParser(BaseParser):
    def parse(self, file_bytes: bytes, filename: str, **kwargs) -> ProcessedDocument:
        url = kwargs.get("url") or filename
        html = trafilatura.fetch_url(url)
        if html is None:
            raise ParseError(f"Could not fetch URL: {url}", SourceType.WEB_URL.value)

        text = trafilatura.extract(
            html, include_tables=True, include_links=True, output_format="markdown"
        )
        if not text:
            text = trafilatura.extract(html, favor_recall=True, output_format="markdown")
        if not text:
            raise ParseError(f"Could not extract content from URL: {url}", SourceType.WEB_URL.value)

        metadata_obj = trafilatura.extract_metadata(html)
        title = metadata_obj.title if metadata_obj and metadata_obj.title else url

        blocks: list[ContentBlock] = []
        for para in text.split("\n\n"):
            para = para.strip()
            if not para:
                continue
            if para.startswith("#"):
                level = len(para) - len(para.lstrip("#"))
                blocks.append(
                    ContentBlock(
                        type=ContentType.HEADING, text=para.lstrip("#").strip(), level=level
                    )
                )
            else:
                blocks.append(ContentBlock(type=ContentType.PARAGRAPH, text=para))

        domain = urlparse(url).netloc

        return ProcessedDocument(
            title=title,
            source_type=SourceType.WEB_URL,
            raw_text=text,
            blocks=blocks,
            metadata={"url": url, "domain": domain},
        )
