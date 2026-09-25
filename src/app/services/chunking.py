import logging
from dataclasses import dataclass, field

import tiktoken
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

logger = logging.getLogger(__name__)


@dataclass
class ChunkResult:
    content: str
    parent_content: str
    metadata: dict = field(default_factory=dict)
    token_count: int = 0


class ChunkingService:
    def __init__(
        self,
        child_chunk_size: int = 512,
        child_chunk_overlap: int = 50,
        parent_chunk_size: int = 2048,
    ):
        self._child_chunk_size = child_chunk_size
        self._child_chunk_overlap = child_chunk_overlap
        self._parent_chunk_size = parent_chunk_size
        self._encoder = tiktoken.get_encoding("cl100k_base")

        self._header_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=[
                ("#", "h1"),
                ("##", "h2"),
                ("###", "h3"),
            ],
            strip_headers=False,
        )

        self._parent_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
            encoding_name="cl100k_base",
            chunk_size=parent_chunk_size,
            chunk_overlap=100,
        )

        self._child_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
            encoding_name="cl100k_base",
            chunk_size=child_chunk_size,
            chunk_overlap=child_chunk_overlap,
        )

    def _count_tokens(self, text: str) -> int:
        return len(self._encoder.encode(text))

    def chunk_document(
        self, markdown: str, metadata: dict
    ) -> list[ChunkResult]:
        if not markdown or not markdown.strip():
            return []

        header_docs = self._header_splitter.split_text(markdown)

        if not header_docs:
            parent_docs = self._parent_splitter.create_documents([markdown])
            parents = [(doc.page_content, {}) for doc in parent_docs]
        else:
            parents = self._merge_into_parents(header_docs)

        if not parents:
            parents = [(markdown, {})]

        results: list[ChunkResult] = []
        for parent_idx, (parent_text, header_meta) in enumerate(parents):
            child_docs = self._child_splitter.create_documents([parent_text])

            if not child_docs:
                token_count = self._count_tokens(parent_text)
                if token_count == 0:
                    continue
                results.append(
                    ChunkResult(
                        content=parent_text,
                        parent_content=parent_text,
                        metadata={
                            **metadata,
                            **header_meta,
                            "parent_index": parent_idx,
                            "child_index": 0,
                        },
                        token_count=token_count,
                    )
                )
                continue

            for child_idx, child_doc in enumerate(child_docs):
                child_text = child_doc.page_content
                token_count = self._count_tokens(child_text)
                if token_count == 0:
                    continue
                results.append(
                    ChunkResult(
                        content=child_text,
                        parent_content=parent_text,
                        metadata={
                            **metadata,
                            **header_meta,
                            "parent_index": parent_idx,
                            "child_index": child_idx,
                        },
                        token_count=token_count,
                    )
                )

        logger.info(
            "Chunked document into %d chunks (parents=%d)",
            len(results),
            len(parents),
        )
        return results

    def _merge_into_parents(
        self, header_docs: list
    ) -> list[tuple[str, dict]]:
        parents: list[tuple[str, dict]] = []
        current_parts: list[str] = []
        current_meta: dict = {}
        current_tokens = 0

        for hdoc in header_docs:
            section_tokens = self._count_tokens(hdoc.page_content)

            if section_tokens > self._parent_chunk_size:
                if current_parts:
                    parents.append(("\n\n".join(current_parts), current_meta))
                    current_parts = []
                    current_meta = {}
                    current_tokens = 0
                sub_docs = self._parent_splitter.create_documents(
                    [hdoc.page_content]
                )
                for sub_doc in sub_docs:
                    parents.append((sub_doc.page_content, dict(hdoc.metadata)))

            elif current_tokens + section_tokens > self._parent_chunk_size:
                if current_parts:
                    parents.append(("\n\n".join(current_parts), current_meta))
                current_parts = [hdoc.page_content]
                current_meta = dict(hdoc.metadata)
                current_tokens = section_tokens

            else:
                current_parts.append(hdoc.page_content)
                if not current_meta:
                    current_meta = dict(hdoc.metadata)
                current_tokens += section_tokens

        if current_parts:
            parents.append(("\n\n".join(current_parts), current_meta))

        return parents
