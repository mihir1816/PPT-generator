import json
import logging
from collections.abc import AsyncGenerator
from dataclasses import asdict, dataclass

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.common import DeckStatus
from app.schemas.deck import (
    LayoutHint,
    SlideContent,
    SlideOutline,
    SlideStatus,
    SlideType,
    TeacherPreferences,
)
from app.services import crud
from app.services.llm_client import LLMClient, LLMServiceError
from app.services.prompt_templates import (
    FEEDBACK_PARSER_SYSTEM,
    FEEDBACK_PARSER_USER,
)
from app.services.slide_generator import SlideGenerator
from app.services.slide_outline import SlideOutlineService

logger = logging.getLogger(__name__)

HISTORY_WINDOW = 3


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class FeedbackAction:
    type: str
    target: str
    instruction: str
    new_position: int | None = None


@dataclass
class FeedbackResult:
    updated_outline: list[SlideOutline]
    affected_slide_ids: list[str]
    regenerated_count: int
    unchanged_count: int
    version: int


# ---------------------------------------------------------------------------
# Pydantic models for LLM responses
# ---------------------------------------------------------------------------


class ParsedAction(BaseModel):
    type: str = "modify_content"
    target_slide: str = ""
    instruction: str = ""
    new_position: int | None = None


class FeedbackParseResponse(BaseModel):
    actions: list[ParsedAction] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Conversation history helper
# ---------------------------------------------------------------------------


def build_feedback_history(
    feedback_rounds: list, window_size: int = HISTORY_WINDOW
) -> list[dict]:
    if not feedback_rounds:
        return []

    recent = feedback_rounds[-window_size:]
    older = feedback_rounds[:-window_size] if len(feedback_rounds) > window_size else []

    history: list[dict] = []
    for r in older:
        actions = r.parsed_actions_json or []
        summary = f"Round {r.round_number}: {len(actions)} action(s) — {r.raw_feedback[:80]}"
        history.append({"round": r.round_number, "summary": summary})

    for r in recent:
        history.append({
            "round": r.round_number,
            "feedback": r.raw_feedback,
            "actions": r.parsed_actions_json or [],
        })

    return history


# ---------------------------------------------------------------------------
# Feedback Service
# ---------------------------------------------------------------------------


class FeedbackService:
    def __init__(self, llm: LLMClient, slide_generator: SlideGenerator,
                 outline_service: SlideOutlineService):
        self._llm = llm
        self._generator = slide_generator
        self._outline_svc = outline_service

    # ------------------------------------------------------------------
    # Public: full feedback pipeline (SSE generator)
    # ------------------------------------------------------------------

    async def process_feedback(
        self,
        deck,
        feedback_text: str,
        retrieval: dict,
        preferences: TeacherPreferences,
        db: AsyncSession,
    ) -> AsyncGenerator[dict, None]:
        outline_json = deck.outline_json or []
        outline = [SlideOutline.model_validate(s) for s in outline_json]

        if not outline:
            yield {
                "event": "generation_complete",
                "data": {"total_slides": 0, "deck_id": str(deck.id), "regenerated": 0, "unchanged": 0},
            }
            return

        # Step 1: Snapshot current state
        existing_slides = await crud.get_slides_by_deck(db, deck.id)
        slides_snapshot = [s.to_dict() for s in existing_slides]

        # Step 2: Parse feedback
        past_rounds = await crud.get_feedback_rounds_by_deck(db, deck.id)
        slide_rounds = [r for r in past_rounds if r.feedback_type == "slide"]
        history = build_feedback_history(slide_rounds)

        try:
            actions = await self.parse_feedback(outline, feedback_text, history)
        except LLMServiceError:
            logger.exception("Failed to parse feedback for deck %s", deck.id)
            yield {"event": "generation_error", "data": {"slide_id": "", "error": "Failed to parse feedback"}}
            return

        if not actions:
            yield {
                "event": "generation_complete",
                "data": {"total_slides": len(outline), "deck_id": str(deck.id), "regenerated": 0, "unchanged": len(outline)},
            }
            return

        # Step 3: Apply actions to outline (no validate_outline — it resets statuses
        # and renumbers IDs, which would break selective regeneration and DB mapping)
        updated_outline = self.apply_actions_to_outline(outline, actions)

        # Step 4: Identify affected slides
        affected = self.get_affected_slides(updated_outline)
        affected_ids = [s.id for s in affected]

        # Save feedback round with snapshots
        round_number = len(slide_rounds) + 1
        await crud.create_feedback_round(db, deck.id, {
            "round_number": round_number,
            "feedback_type": "slide",
            "raw_feedback": feedback_text,
            "parsed_actions_json": [asdict(a) for a in actions],
            "affected_slide_ids": affected_ids,
            "outline_snapshot_json": outline_json,
            "slides_snapshot_json": slides_snapshot,
        })

        # Save updated outline
        deck.outline_json = [s.model_dump(mode="json") for s in updated_outline]
        deck.version = (deck.version or 0) + 1
        await db.commit()

        # Step 5: Delete slides that were removed from outline
        current_slide_ids = {s.id for s in updated_outline}
        deleted_ids = set()
        for slide_row in existing_slides:
            if slide_row.slide_id not in current_slide_ids:
                await db.delete(slide_row)
                deleted_ids.add(slide_row.slide_id)
        if deleted_ids:
            await db.commit()
            logger.info("Deleted %d slides removed by feedback", len(deleted_ids))

        # Step 6: Regenerate only affected slides
        generated_map = {}
        for s in await crud.get_slides_by_deck(db, deck.id):
            generated_map[s.slide_id] = s

        prev_slide: SlideContent | None = None
        regenerated = 0

        affected_id_set = {a.id for a in affected}

        for entry in updated_outline:
            if entry.id not in affected_id_set:
                if entry.id in generated_map:
                    s = generated_map[entry.id]
                    if s.position != entry.position:
                        s.position = entry.position
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
                content = await self._generator.generate_single_slide(
                    entry, chunks, prev_slide, preferences,
                )
            except Exception as exc:
                logger.exception("Failed to regenerate slide %s", entry.id)
                yield {"event": "generation_error", "data": {"slide_id": entry.id, "error": str(exc)}}
                continue

            # Upsert: update existing or create new
            if entry.id in generated_map:
                existing = generated_map[entry.id]
                existing.title = content.title
                existing.body = content.body
                existing.bullet_points = content.bullet_points
                existing.table_data = content.table_data.model_dump() if content.table_data else None
                existing.speaker_notes = content.speaker_notes
                existing.layout_hint = content.layout_hint.value
                existing.position = entry.position
            else:
                await crud.create_slide(db, deck.id, {
                    "slide_id": content.slide_id,
                    "position": entry.position,
                    "title": content.title,
                    "body": content.body,
                    "bullet_points": content.bullet_points,
                    "table_data": content.table_data.model_dump() if content.table_data else None,
                    "speaker_notes": content.speaker_notes,
                    "layout_hint": content.layout_hint.value,
                })
            await db.commit()
            regenerated += 1

            yield {"event": "slide_content", "data": content.model_dump(mode="json")}
            yield {"event": "slide_complete", "data": {"slide_id": entry.id}}
            prev_slide = content

        # Step 7: Mark all outline statuses as generated
        for s in updated_outline:
            s.status = SlideStatus.GENERATED
        deck.outline_json = [s.model_dump(mode="json") for s in updated_outline]
        deck.status = DeckStatus.COMPLETED
        await db.commit()

        unchanged = len(updated_outline) - regenerated
        yield {
            "event": "generation_complete",
            "data": {
                "total_slides": len(updated_outline),
                "deck_id": str(deck.id),
                "regenerated": regenerated,
                "unchanged": unchanged,
                "version": deck.version,
            },
        }

    # ------------------------------------------------------------------
    # Parse feedback → structured actions
    # ------------------------------------------------------------------

    async def parse_feedback(
        self,
        outline: list[SlideOutline],
        feedback_text: str,
        history: list[dict],
    ) -> list[FeedbackAction]:
        outline_json = json.dumps(
            [s.model_dump(mode="json") for s in outline], indent=2,
        )
        history_text = json.dumps(history, indent=2) if history else "No previous feedback."

        prompt = FEEDBACK_PARSER_USER.format(
            outline_json=outline_json,
            feedback_text=feedback_text,
        )
        if history:
            prompt += f"\n\nPrevious feedback rounds:\n{history_text}"

        result = await self._llm.generate_json(
            FEEDBACK_PARSER_SYSTEM,
            prompt,
            response_model=FeedbackParseResponse,
        )

        actions: list[FeedbackAction] = []
        valid_ids = {s.id for s in outline} | {"all"}
        for a in result.actions:
            if not a.target_slide or not a.instruction:
                continue
            if a.target_slide not in valid_ids:
                logger.warning("Feedback action targets unknown slide: %s", a.target_slide)
                continue
            actions.append(FeedbackAction(
                type=a.type,
                target=a.target_slide,
                instruction=a.instruction,
                new_position=a.new_position,
            ))

        logger.info("Parsed %d feedback actions from: %s", len(actions), feedback_text[:100])
        return actions

    # ------------------------------------------------------------------
    # Apply actions to outline (pure logic, no I/O)
    # ------------------------------------------------------------------

    def apply_actions_to_outline(
        self,
        outline: list[SlideOutline],
        actions: list[FeedbackAction],
    ) -> list[SlideOutline]:
        outline = [s.model_copy(deep=True) for s in outline]
        id_map = {s.id: s for s in outline}
        new_slide_counter = 0

        for action in actions:
            if action.type == "delete":
                outline = [s for s in outline if s.id != action.target]
                id_map = {s.id: s for s in outline}

            elif action.type == "insert_after":
                idx = next(
                    (i for i, s in enumerate(outline) if s.id == action.target),
                    len(outline) - 1,
                )
                new_slide_counter += 1
                new_slide = SlideOutline(
                    id=f"slide_new_{new_slide_counter}",
                    position=0,
                    type=SlideType.CONTENT,
                    title=action.instruction[:60],
                    key_points=[action.instruction],
                    layout_hint=LayoutHint.BULLET,
                    status=SlideStatus.PENDING,
                )
                outline.insert(idx + 1, new_slide)
                id_map = {s.id: s for s in outline}

            elif action.type == "reorder" and action.new_position is not None:
                slide = id_map.get(action.target)
                if slide and slide in outline:
                    outline.remove(slide)
                    new_pos = max(0, min(action.new_position - 1, len(outline)))
                    outline.insert(new_pos, slide)

            elif action.type == "change_tone":
                if action.target == "all":
                    for s in outline:
                        s.status = SlideStatus.NEEDS_REGENERATION
                elif action.target in id_map:
                    id_map[action.target].status = SlideStatus.NEEDS_REGENERATION

            elif action.type in ("modify_content", "expand"):
                slide = id_map.get(action.target)
                if slide:
                    slide.key_points = slide.key_points + [action.instruction]
                    slide.status = SlideStatus.NEEDS_REGENERATION

            elif action.type == "add_table":
                slide = id_map.get(action.target)
                if slide:
                    slide.layout_hint = LayoutHint.TABLE
                    slide.type = SlideType.TABLE
                    slide.key_points = slide.key_points + [action.instruction]
                    slide.status = SlideStatus.NEEDS_REGENERATION

            elif action.type == "add_image":
                slide = id_map.get(action.target)
                if slide:
                    slide.layout_hint = LayoutHint.IMAGE_PLACEHOLDER
                    slide.key_points = slide.key_points + [action.instruction]
                    slide.status = SlideStatus.NEEDS_REGENERATION

        # Only renumber positions — preserve original IDs so DB mapping stays intact
        for i, s in enumerate(outline):
            s.position = i + 1

        return outline

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def get_affected_slides(outline: list[SlideOutline]) -> list[SlideOutline]:
        return [
            s for s in outline
            if s.status in (SlideStatus.PENDING, SlideStatus.NEEDS_REGENERATION)
        ]

    # ------------------------------------------------------------------
    # Undo
    # ------------------------------------------------------------------

    async def undo_last_feedback(self, deck, db: AsyncSession) -> dict:
        last_round = await crud.get_last_feedback_round(db, deck.id, feedback_type="slide")
        if last_round is None:
            return {"success": False, "message": "No feedback round to undo"}

        # Restore outline
        if last_round.outline_snapshot_json is not None:
            deck.outline_json = last_round.outline_snapshot_json

        # Restore slides
        if last_round.slides_snapshot_json:
            existing_slides = await crud.get_slides_by_deck(db, deck.id)
            existing_map = {s.slide_id: s for s in existing_slides}
            snapshot_ids = set()

            for snap in last_round.slides_snapshot_json:
                sid = snap.get("slide_id")
                if not sid:
                    continue
                snapshot_ids.add(sid)
                if sid in existing_map:
                    row = existing_map[sid]
                    row.title = snap.get("title", "")
                    row.body = snap.get("body", "")
                    row.bullet_points = snap.get("bullet_points")
                    row.table_data = snap.get("table_data")
                    row.speaker_notes = snap.get("speaker_notes", "")
                    row.layout_hint = snap.get("layout_hint", "bullet")
                    row.position = snap.get("position", row.position)
                else:
                    await crud.create_slide(db, deck.id, snap)

            # Delete slides that were inserted by the undone feedback
            for s in existing_slides:
                if s.slide_id not in snapshot_ids:
                    outline_ids = {
                        entry.get("id") for entry in (deck.outline_json or [])
                    }
                    if s.slide_id not in outline_ids:
                        await db.delete(s)

        deck.version = max((deck.version or 1) - 1, 0)
        deck.status = DeckStatus.COMPLETED
        await db.delete(last_round)
        await db.commit()

        slides = await crud.get_slides_by_deck(db, deck.id)
        return {
            "success": True,
            "message": f"Reverted to version {deck.version}",
            "outline": deck.outline_json,
            "slides": [s.to_dict() for s in slides],
            "version": deck.version,
        }
