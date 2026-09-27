import json
import logging
import re
from collections.abc import AsyncGenerator

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.common import DeckStatus
from app.schemas.deck import (
    LayoutHint,
    SlideContent,
    SlideOutline,
    SlideType,
    TableData,
    TeacherPreferences,
)
from app.services import crud
from app.services.llm_client import LLMClient
from app.services.prompt_templates import SLIDE_CONTENT_SYSTEM, SLIDE_CONTENT_USER
from app.services.slide_outline import SlideOutlineService

logger = logging.getLogger(__name__)


class SlideContentResponse(BaseModel):
    slide_id: str = ""
    title: str = ""
    body: str = ""
    bullet_points: list[str] = Field(default_factory=list)
    table_data: dict | None = None
    speaker_notes: str = ""
    layout_hint: str = "bullet"


class SlideGenerator:
    def __init__(self, llm: LLMClient, outline_service: SlideOutlineService):
        self._llm = llm
        self._outline_svc = outline_service

    async def generate_all_slides(
        self,
        deck,
        retrieval: dict,
        preferences: TeacherPreferences,
        db: AsyncSession,
    ) -> AsyncGenerator[dict, None]:
        outline_json = deck.outline_json or []
        outline_entries = [SlideOutline.model_validate(s) for s in outline_json]

        if not outline_entries:
            yield {
                "event": "generation_complete",
                "data": {"total_slides": 0, "deck_id": str(deck.id)},
            }
            return

        existing_slides = await crud.get_slides_by_deck(db, deck.id)
        generated_map = {s.slide_id: s for s in existing_slides}

        prev_slide: SlideContent | None = None
        generated_count = len(generated_map)
        errors = 0

        for entry in outline_entries:
            if entry.id in generated_map:
                s = generated_map[entry.id]
                try:
                    layout = LayoutHint(s.layout_hint)
                except ValueError:
                    layout = LayoutHint.BULLET
                prev_slide = SlideContent(
                    slide_id=s.slide_id,
                    title=s.title,
                    body=s.body,
                    bullet_points=s.bullet_points or [],
                    speaker_notes=s.speaker_notes,
                    layout_hint=layout,
                )
                continue

            yield {
                "event": "slide_start",
                "data": {
                    "slide_id": entry.id,
                    "position": entry.position,
                    "title": entry.title,
                    "type": entry.type.value,
                },
            }

            chunks = self._outline_svc.get_chunks_for_slide(entry, retrieval)

            try:
                content = await self.generate_single_slide(
                    entry, chunks, prev_slide, preferences,
                )
            except Exception as exc:
                logger.exception(
                    "Failed to generate slide %s for deck %s",
                    entry.id,
                    deck.id,
                )
                errors += 1
                yield {
                    "event": "generation_error",
                    "data": {"slide_id": entry.id, "error": str(exc)},
                }
                continue

            await crud.create_slide(
                db,
                deck.id,
                {
                    "slide_id": content.slide_id,
                    "position": entry.position,
                    "title": content.title,
                    "body": content.body,
                    "bullet_points": content.bullet_points,
                    "table_data": (
                        content.table_data.model_dump()
                        if content.table_data
                        else None
                    ),
                    "speaker_notes": content.speaker_notes,
                    "layout_hint": content.layout_hint.value,
                },
            )
            await db.commit()
            generated_count += 1

            yield {
                "event": "slide_content",
                "data": content.model_dump(mode="json"),
            }

            yield {"event": "slide_complete", "data": {"slide_id": entry.id}}

            prev_slide = content

        total_expected = len(outline_entries)
        if errors > 0 and generated_count < total_expected:
            if generated_count == len(generated_map):
                deck.status = DeckStatus.FAILED
            else:
                logger.warning(
                    "Deck %s: %d/%d slides generated, %d errors",
                    deck.id, generated_count, total_expected, errors,
                )
                deck.status = DeckStatus.COMPLETED
        else:
            deck.status = DeckStatus.COMPLETED
        await db.commit()

        yield {
            "event": "generation_complete",
            "data": {"total_slides": generated_count, "deck_id": str(deck.id)},
        }

    async def generate_single_slide(
        self,
        outline_entry: SlideOutline,
        chunks: list[str],
        prev_slide: SlideContent | None,
        preferences: TeacherPreferences,
    ) -> SlideContent:
        system_prompt, user_prompt = self._build_slide_prompt(
            outline_entry, chunks, prev_slide, preferences,
        )

        result = await self._llm.generate_json(
            system_prompt,
            user_prompt,
            response_model=SlideContentResponse,
        )

        return self._post_process(result, outline_entry)

    _MAX_PROMPT_CHARS = 9000

    def _build_slide_prompt(
        self,
        outline: SlideOutline,
        chunks: list[str],
        prev_slide: SlideContent | None,
        preferences: TeacherPreferences,
    ) -> tuple[str, str]:
        outline_text = json.dumps(
            {
                "id": outline.id,
                "type": outline.type.value,
                "title": outline.title,
                "key_points": outline.key_points,
                "layout_hint": outline.layout_hint.value,
            },
            indent=2,
        )

        if chunks:
            chunks_text = "\n\n---\n\n".join(chunks)
        else:
            chunks_text = "(No source content available for this slide)"

        overhead = len(SLIDE_CONTENT_SYSTEM) + len(outline_text) + 600
        budget = self._MAX_PROMPT_CHARS - overhead
        if budget > 0 and len(chunks_text) > budget:
            chunks_text = chunks_text[:budget] + "\n...(truncated)"

        if prev_slide:
            prev_summary = f'Previous slide: "{prev_slide.title}"'
            if prev_slide.bullet_points:
                prev_summary += f"\n  Key point: {prev_slide.bullet_points[0]}"
        else:
            prev_summary = "(This is the first slide)"

        if preferences.content_mode == "grounded":
            content_mode_text = (
                "Grounded: Use ONLY the provided source content below. "
                "Do not add any information not found in the sources. "
                "If sources are insufficient, note the gap."
            )
        else:
            content_mode_text = (
                "Mixed: Use the provided source content as your primary material. "
                "You may add brief transitions, examples, or clarifications, "
                "but do not generate entire sections from scratch."
            )

        user_prompt = SLIDE_CONTENT_USER.format(
            outline_entry=outline_text,
            relevant_chunks=chunks_text,
            prev_slide_summary=prev_summary,
            level=preferences.audience_level,
            tone=preferences.tone,
            content_mode=content_mode_text,
            slide_id=outline.id,
        )

        return SLIDE_CONTENT_SYSTEM, user_prompt

    @staticmethod
    def _post_process(
        result: SlideContentResponse, outline: SlideOutline,
    ) -> SlideContent:
        try:
            layout = LayoutHint(result.layout_hint)
        except ValueError:
            layout = outline.layout_hint

        table_data: TableData | None = None
        is_table_slide = outline.type in (
            SlideType.TABLE,
            SlideType.TABLE_CONTINUATION,
        )

        if result.table_data and isinstance(result.table_data, dict):
            table_data = TableData(
                headers=result.table_data.get("headers", []),
                rows=result.table_data.get("rows", []),
            )
        elif is_table_slide:
            table_data = TableData(
                headers=["Column 1", "Column 2"],
                rows=[["Data pending", ""]],
            )

        title = result.title or outline.title
        body = result.body or ""
        bullets = result.bullet_points or []

        body = SlideGenerator._fix_nested_brackets(body)
        bullets = [SlideGenerator._fix_nested_brackets(b) for b in bullets]

        all_text = body + " ".join(bullets)
        if "[[" not in all_text:
            body, bullets = SlideGenerator._inject_emphasis(
                title, body, bullets, outline,
            )

        return SlideContent(
            slide_id=outline.id,
            title=title,
            body=body,
            bullet_points=bullets,
            table_data=table_data,
            speaker_notes=(
                result.speaker_notes
                or f"Presenter notes for: {title}"
            ),
            layout_hint=layout,
        )

    @staticmethod
    def _fix_nested_brackets(text: str) -> str:
        if not text or "[[" not in text:
            return text
        while "[[[[" in text:
            text = text.replace("[[[[", "[[")
        while "]]]]" in text:
            text = text.replace("]]]]", "]]")
        if text.count("[[") != text.count("]]"):
            text = text.replace("[[", "").replace("]]", "")
        return text

    _STOP = frozenset(
        "the a an is are was were be been being have has had do does did "
        "will would shall should may might must can could and but or nor "
        "not so yet in on at to for of with by from as into through during "
        "before after above below between under over this that these those "
        "it its all each every both few many most other some such no only "
        "same than too very just about also then more here there when where "
        "why how used using use includes including various certain specific "
        "different".split()
    )

    @staticmethod
    def _inject_emphasis(
        title: str,
        body: str,
        bullets: list[str],
        outline: SlideOutline,
    ) -> tuple[str, list[str]]:
        bigrams: list[str] = []
        unigrams: list[str] = []

        sources = list(outline.key_points or []) + [title]
        for src in sources:
            words = re.findall(r"[A-Za-z]+(?:'[a-z]+)?", src)
            for w in words:
                low = w.lower()
                if low not in SlideGenerator._STOP and len(low) > 3:
                    unigrams.append(low)
            for i in range(len(words) - 1):
                a, b = words[i].lower(), words[i + 1].lower()
                if (a not in SlideGenerator._STOP
                        and b not in SlideGenerator._STOP
                        and len(a) > 2 and len(b) > 2):
                    bigrams.append(f"{a} {b}")

        seen: set[str] = set()
        ordered: list[str] = []
        for t in bigrams + unigrams:
            if t not in seen:
                seen.add(t)
                ordered.append(t)

        if not ordered:
            return body, bullets

        def wrap(text: str, limit: int = 2) -> str:
            if not text:
                return text
            n = 0
            for term in ordered:
                if n >= limit:
                    break
                pat = re.compile(
                    r"\b(" + re.escape(term) + r")\b", re.IGNORECASE,
                )
                if pat.search(text):
                    text = pat.sub(r"[[\1]]", text, count=1)
                    n += 1
            return text

        return wrap(body, 2), [wrap(b, 1) for b in bullets]
