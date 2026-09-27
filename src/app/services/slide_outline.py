import logging
from difflib import SequenceMatcher

from pydantic import BaseModel, Field

from app.schemas.deck import (
    LayoutHint,
    SlideOutline,
    SlideStatus,
    SlideType,
    TeacherPreferences,
)
from app.schemas.syllabus import TopicSyllabus
from app.services.llm_client import LLMClient, LLMServiceError
from app.services.prompt_templates import SLIDE_OUTLINE_SYSTEM, SLIDE_OUTLINE_USER

logger = logging.getLogger(__name__)

CHUNK_SUMMARY_SNIPPET_LEN = 120
MAX_CHUNKS_PER_TOPIC_SUMMARY = 2


class OutlineSlideItem(BaseModel):
    id: str = ""
    position: int = 0
    type: str = "content"
    title: str = ""
    key_points: list[str] = Field(default_factory=list)
    layout_hint: str = "bullet"
    source_chunk_ids: list[str] = Field(default_factory=list)
    spans_slides: bool = False
    table_continuation: bool = False
    status: str = "pending"


class OutlineGenerationResponse(BaseModel):
    slides: list[OutlineSlideItem] = Field(default_factory=list)


class SlideOutlineService:
    def __init__(self, llm_client: LLMClient):
        self._llm = llm_client

    async def generate_outline(
        self,
        syllabus: TopicSyllabus,
        retrieval: dict,
        preferences: TeacherPreferences,
    ) -> list[SlideOutline]:
        topic_chunks = retrieval.get("topic_chunks", [])
        chunks_summary = self._summarize_chunks(topic_chunks)

        syllabus_json = syllabus.model_dump_json(indent=2)
        max_summary_chars = max(500, self._llm._model_context * 2 - len(syllabus_json) - 800)
        if len(chunks_summary) > max_summary_chars:
            logger.warning(
                "Truncating chunks summary from %d to %d chars to fit context",
                len(chunks_summary), max_summary_chars,
            )
            chunks_summary = chunks_summary[:max_summary_chars] + "\n[... truncated]"

        slide_count_hint = str(preferences.slide_count_hint) if preferences.slide_count_hint else "10-15"

        try:
            result = await self._llm.generate_json(
                SLIDE_OUTLINE_SYSTEM,
                SLIDE_OUTLINE_USER.format(
                    syllabus_json=syllabus_json,
                    chunks_summary=chunks_summary,
                    level=preferences.audience_level,
                    tone=preferences.tone,
                    content_mode=preferences.content_mode,
                    slide_count_hint=slide_count_hint,
                ),
                response_model=OutlineGenerationResponse,
            )
        except LLMServiceError:
            logger.exception("LLM outline generation failed")
            raise

        all_chunk_ids = self._collect_chunk_ids(topic_chunks)

        slides: list[SlideOutline] = []
        for item in result.slides:
            try:
                slide_type = SlideType(item.type)
            except ValueError:
                slide_type = SlideType.CONTENT

            try:
                layout = LayoutHint(item.layout_hint)
            except ValueError:
                layout = _default_layout(slide_type)

            valid_ids = [cid for cid in item.source_chunk_ids if cid in all_chunk_ids]

            slides.append(
                SlideOutline(
                    id=item.id,
                    position=item.position,
                    type=slide_type,
                    title=item.title or "Untitled",
                    key_points=item.key_points,
                    layout_hint=layout,
                    source_chunk_ids=valid_ids,
                    spans_slides=item.spans_slides,
                    table_continuation=item.table_continuation,
                    status=SlideStatus.PENDING,
                )
            )

        slides = self._map_missing_chunks(slides, topic_chunks, syllabus)
        return self.validate_outline(slides)

    def validate_outline(self, outline: list[SlideOutline]) -> list[SlideOutline]:
        if not outline:
            outline = [
                SlideOutline(
                    id="slide_1",
                    position=1,
                    type=SlideType.TITLE,
                    title="Presentation",
                    layout_hint=LayoutHint.TITLE,
                    status=SlideStatus.PENDING,
                )
            ]

        for i, slide in enumerate(outline):
            slide.id = f"slide_{i + 1}"
            slide.position = i + 1
            slide.status = SlideStatus.PENDING

        if outline[0].type != SlideType.TITLE:
            title_slide = SlideOutline(
                id="slide_1",
                position=1,
                type=SlideType.TITLE,
                title=outline[0].title,
                layout_hint=LayoutHint.TITLE,
                status=SlideStatus.PENDING,
            )
            outline.insert(0, title_slide)
            for i, slide in enumerate(outline):
                slide.id = f"slide_{i + 1}"
                slide.position = i + 1

        seen_ids: set[str] = set()
        for slide in outline:
            if slide.id in seen_ids:
                slide.id = f"slide_{slide.position}_dup"
            seen_ids.add(slide.id)

        spanning_tables: set[int] = set()
        for slide in outline:
            if slide.type == SlideType.TABLE and slide.spans_slides:
                spanning_tables.add(slide.position)

        for slide in outline:
            if slide.type == SlideType.TABLE_CONTINUATION:
                prev_is_table = (slide.position - 1) in spanning_tables or any(
                    s.type in (SlideType.TABLE, SlideType.TABLE_CONTINUATION)
                    and s.position == slide.position - 1
                    for s in outline
                )
                if not prev_is_table:
                    slide.type = SlideType.CONTENT
                    slide.table_continuation = False
                    slide.layout_hint = LayoutHint.BULLET

        has_content = any(
            s.type
            in (
                SlideType.CONTENT,
                SlideType.TABLE,
                SlideType.SECTION_HEADER,
                SlideType.SUMMARY,
            )
            for s in outline
        )
        if not has_content:
            outline.append(
                SlideOutline(
                    id=f"slide_{len(outline) + 1}",
                    position=len(outline) + 1,
                    type=SlideType.CONTENT,
                    title="Content",
                    key_points=["Content to be generated"],
                    layout_hint=LayoutHint.BULLET,
                    status=SlideStatus.PENDING,
                )
            )

        return outline

    def get_chunks_for_slide(
        self, slide: SlideOutline, retrieval: dict
    ) -> list[str]:
        if not slide.source_chunk_ids:
            return []

        chunk_id_set = set(slide.source_chunk_ids)
        texts: list[str] = []
        for tc in retrieval.get("topic_chunks", []):
            for chunk in tc.get("chunks", []):
                if chunk.get("chunk_id") in chunk_id_set:
                    texts.append(
                        chunk.get("parent_content") or chunk.get("content", "")
                    )
        return texts

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _summarize_chunks(topic_chunks: list[dict]) -> str:
        lines: list[str] = []
        for tc in topic_chunks:
            title = tc.get("topic_title", "Unknown")
            chunks = tc.get("chunks", [])
            coverage = tc.get("coverage", "none")
            if not chunks:
                lines.append(f"Topic: {title} — no content retrieved")
                continue

            chunk_lines: list[str] = []
            for c in chunks[:MAX_CHUNKS_PER_TOPIC_SUMMARY]:
                cid = c.get("chunk_id", "unknown")
                text = c.get("content", "")
                snippet = text[:CHUNK_SUMMARY_SNIPPET_LEN].strip()
                if len(text) > CHUNK_SUMMARY_SNIPPET_LEN:
                    snippet += "..."
                chunk_lines.append(f"  - [{cid}] {snippet}")

            lines.append(
                f"Topic: {title} ({coverage} coverage, {len(chunks)} chunks)\n"
                + "\n".join(chunk_lines)
            )
        return "\n\n".join(lines) if lines else "No content available."

    @staticmethod
    def _collect_chunk_ids(topic_chunks: list[dict]) -> set[str]:
        ids: set[str] = set()
        for tc in topic_chunks:
            for chunk in tc.get("chunks", []):
                cid = chunk.get("chunk_id")
                if cid:
                    ids.add(cid)
        return ids

    @staticmethod
    def _map_missing_chunks(
        slides: list[SlideOutline],
        topic_chunks: list[dict],
        syllabus: TopicSyllabus,
    ) -> list[SlideOutline]:
        topic_titles = [t.title for t in syllabus.topics]
        topic_chunk_map: dict[str, list[str]] = {}
        for tc in topic_chunks:
            title = tc.get("topic_title", "")
            chunk_ids = [
                c["chunk_id"]
                for c in tc.get("chunks", [])
                if c.get("chunk_id")
            ]
            if chunk_ids:
                topic_chunk_map[title] = chunk_ids

        decorative = (SlideType.TITLE, SlideType.CLOSING, SlideType.TABLE_CONTINUATION)

        for slide in slides:
            if slide.source_chunk_ids or slide.type in decorative:
                continue

            best_topic = ""
            best_ratio = 0.0
            for tt in topic_titles:
                ratio = SequenceMatcher(None, slide.title.lower(), tt.lower()).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_topic = tt

            if best_topic and best_ratio > 0.3 and best_topic in topic_chunk_map:
                slide.source_chunk_ids = topic_chunk_map[best_topic]

        return slides


def _default_layout(slide_type: SlideType) -> LayoutHint:
    return {
        SlideType.TITLE: LayoutHint.TITLE,
        SlideType.SECTION_HEADER: LayoutHint.SECTION_HEADER,
        SlideType.TABLE: LayoutHint.TABLE,
        SlideType.TABLE_CONTINUATION: LayoutHint.TABLE,
        SlideType.SUMMARY: LayoutHint.BULLET,
        SlideType.CLOSING: LayoutHint.TITLE,
    }.get(slide_type, LayoutHint.BULLET)
