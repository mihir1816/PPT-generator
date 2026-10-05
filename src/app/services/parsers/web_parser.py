import logging
from urllib.parse import urlparse

import requests
import trafilatura

from app.schemas.document import ContentBlock, ContentType, ProcessedDocument, SourceType
from app.services.parsers.base import BaseParser, ParseError

logger = logging.getLogger(__name__)

_JINA_READER_PREFIX = "https://r.jina.ai/"
_JINA_TIMEOUT = 30


def _fetch_via_jina(url: str) -> tuple[str, str | None]:
    """Fallback fetcher using Jina AI Reader. Returns (markdown_text, title)."""
    resp = requests.get(
        f"{_JINA_READER_PREFIX}{url}",
        headers={"Accept": "text/markdown"},
        timeout=_JINA_TIMEOUT,
    )
    resp.raise_for_status()
    text = resp.text
    title = None
    for line in text.splitlines():
        if line.startswith("Title: "):
            title = line[7:].strip()
        if line.startswith("Markdown Content:"):
            text = text[text.index("Markdown Content:") + len("Markdown Content:") :].strip()
            break
    # Strip Jina metadata lines (author images, read time, date) before first heading
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("#"):
            text = "\n".join(lines[i:])
            break
    return text, title


def _markdown_to_blocks(text: str) -> list[ContentBlock]:
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
    return blocks


class WebParser(BaseParser):
    def parse(self, file_bytes: bytes, filename: str, **kwargs) -> ProcessedDocument:
        url = kwargs.get("url") or filename
        domain = urlparse(url).netloc

        text: str | None = None
        title: str | None = None

        # Primary: trafilatura
        html = trafilatura.fetch_url(url)
        if html is not None:
            text = trafilatura.extract(
                html, include_tables=True, include_links=True, output_format="markdown"
            )
            if not text:
                text = trafilatura.extract(html, favor_recall=True, output_format="markdown")
            if text:
                metadata_obj = trafilatura.extract_metadata(html)
                title = metadata_obj.title if metadata_obj and metadata_obj.title else None

        # Fallback: Jina AI Reader (handles Cloudflare-protected sites)
        if not text:
            logger.info("trafilatura failed for %s, falling back to Jina Reader", url)
            try:
                text, title = _fetch_via_jina(url)
            except Exception as exc:
                logger.warning("Jina Reader also failed for %s: %s", url, exc)
                raise ParseError(
                    f"Could not fetch URL: {url}", SourceType.WEB_URL.value
                ) from exc

        if not text:
            raise ParseError(f"Could not extract content from URL: {url}", SourceType.WEB_URL.value)

        title = title or url
        blocks = _markdown_to_blocks(text)

        return ProcessedDocument(
            title=title,
            source_type=SourceType.WEB_URL,
            raw_text=text,
            blocks=blocks,
            metadata={"url": url, "domain": domain},
        )
