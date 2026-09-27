import json
import logging
from collections.abc import AsyncGenerator
from dataclasses import asdict, dataclass

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.common import DeckStatus
from app.schemas.deck import (
    LayoutHint,
    SlideOutline,
    SlideStatus,
    SlideType,
    TeacherPreferences,
)
from app.services import crud
from app.services.llm_client import LLMClient, LLMServiceError
from app.services.prompt_templates import (
    FEEDBACK_ANALYZER_SYSTEM,
    FEEDBACK_ANALYZER_USER,
    SLIDE_EDITOR_SYSTEM,
    SLIDE_EDITOR_USER,
    SLIDE_MERGER_SYSTEM,
    SLIDE_MERGER_USER,
    SLIDE_NEW_SYSTEM,
    SLIDE_NEW_USER,
    SLIDE_SPLITTER_SYSTEM,
    SLIDE_SPLITTER_USER,
)
from app.services.slide_generator import SlideGenerator
from app.services.slide_outline import SlideOutlineService

logger = logging.getLogger(__name__)

HISTORY_WINDOW = 3


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class FeedbackChange:
    action: str
    target: str
    edit_instruction: str
    new_layout: str | None = None
    new_position: int | None = None
    insert_after: str | None = None


# ---------------------------------------------------------------------------
# Pydantic models for LLM responses
# ---------------------------------------------------------------------------


class AnalyzerChange(BaseModel):
    action: str = "edit_content"
    target: str = ""
    edit_instruction: str = ""
    new_layout: str | None = None
    new_position: int | None = None
    insert_after: str | None = None


class AnalyzerResponse(BaseModel):
    interpretation: str = ""
    changes: list[AnalyzerChange] = Field(default_factory=list)


class SlideEditResponse(BaseModel):
    title: str = ""
    body: str = ""
    bullet_points: list[str] = Field(default_factory=list)
    table_data: dict | None = None
    speaker_notes: str = ""
    layout_hint: str = "bullet"


class SlideSplitResponse(BaseModel):
    slide_a: SlideEditResponse = Field(default_factory=SlideEditResponse)
    slide_b: SlideEditResponse = Field(default_factory=SlideEditResponse)


# ---------------------------------------------------------------------------
# Conversation history helper
# ---------------------------------------------------------------------------


def build_feedback_history(
    feedback_rounds: list, window_size: int = HISTORY_WINDOW
) -> str:
    if not feedback_rounds:
        return ""

    recent = feedback_rounds[-window_size:]
    lines = []
    for r in recent:
        actions = r.parsed_actions_json or []
        action_summary = ", ".join(
            f"{a.get('action', '?')} on {a.get('target', '?')}"
            for a in actions[:3]
        )
        lines.append(f"Round {r.round_number}: \"{r.raw_feedback[:80]}\" → {action_summary}")

    return "\nPrevious feedback:\n" + "\n".join(lines)


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
            yield self._complete_event(deck, 0, 0)
            return

        # Step 1: Load current slides and build manifest
        existing_slides = await crud.get_slides_by_deck(db, deck.id)
        slides_map = {s.slide_id: s for s in existing_slides}
        manifest = self._build_manifest(outline, existing_slides)

        # Step 2: Snapshot for undo
        slides_snapshot = [s.to_dict() for s in existing_slides]

        # Step 3: Analyze feedback with LLM
        past_rounds = await crud.get_feedback_rounds_by_deck(db, deck.id)
        slide_rounds = [r for r in past_rounds if r.feedback_type == "slide"]
        history_text = build_feedback_history(slide_rounds)

        try:
            changes = await self._analyze_feedback(manifest, feedback_text, history_text)
        except LLMServiceError:
            logger.exception("Failed to analyze feedback for deck %s", deck.id)
            yield {"event": "generation_error", "data": {"slide_id": "", "error": "Failed to analyze feedback"}}
            return

        if not changes:
            logger.info("Analyzer returned no changes for feedback: %s", feedback_text[:100])
            yield self._complete_event(deck, len(outline), 0)
            return

        logger.info(
            "Analyzer produced %d changes for deck %s: %s",
            len(changes), deck.id,
            ", ".join(f"{c.action}→{c.target}" for c in changes),
        )

        # Step 4: Validate plan
        changes = self._validate_plan(changes, outline, slides_map)
        if not changes:
            yield self._complete_event(deck, len(outline), 0)
            return

        # Step 5: Save feedback round with snapshot
        round_number = len(slide_rounds) + 1
        await crud.create_feedback_round(db, deck.id, {
            "round_number": round_number,
            "feedback_type": "slide",
            "raw_feedback": feedback_text,
            "parsed_actions_json": [asdict(c) for c in changes],
            "affected_slide_ids": [c.target for c in changes],
            "outline_snapshot_json": outline_json,
            "slides_snapshot_json": slides_snapshot,
        })
        await db.commit()

        # Step 6: Execute each change
        regenerated = 0

        for change in changes:
            try:
                result = await self._execute_change(
                    change, outline, slides_map, retrieval, preferences, db, deck,
                )
                if result:
                    for event in result:
                        yield event
                    regenerated += 1
            except Exception as exc:
                logger.exception("Failed to execute %s on %s", change.action, change.target)
                yield {"event": "generation_error", "data": {
                    "slide_id": change.target, "error": str(exc),
                }}

        # Step 7: Renumber positions, save outline, mark complete
        for i, s in enumerate(outline):
            s.position = i + 1

        deck.outline_json = [s.model_dump(mode="json") for s in outline]
        deck.version = (deck.version or 0) + 1
        deck.status = DeckStatus.COMPLETED

        # Update positions in DB for untouched slides
        for entry in outline:
            if entry.id in slides_map:
                row = slides_map[entry.id]
                if row.position != entry.position:
                    row.position = entry.position

        await db.commit()

        yield self._complete_event(deck, len(outline), regenerated)

    # ------------------------------------------------------------------
    # Step 3: Analyze feedback → structured change plan
    # ------------------------------------------------------------------

    async def _analyze_feedback(
        self, manifest: str, feedback_text: str, history_text: str,
    ) -> list[FeedbackChange]:
        prompt = FEEDBACK_ANALYZER_USER.format(
            manifest=manifest,
            feedback_text=feedback_text,
            history_section=history_text,
        )

        result = await self._llm.generate_json(
            FEEDBACK_ANALYZER_SYSTEM, prompt, response_model=AnalyzerResponse,
        )

        logger.info("Feedback interpretation: %s", result.interpretation)
        logger.info(
            "Analyzer raw changes: %s",
            [c.model_dump() for c in result.changes],
        )

        changes: list[FeedbackChange] = []
        for c in result.changes:
            target = c.target.strip() if c.target else ""
            instruction = c.edit_instruction.strip() if c.edit_instruction else ""
            if not target or target in ("slide_id", "id"):
                continue
            placeholder_phrases = {"specific instruction", "instruction", "edit instruction"}
            if not instruction or instruction.lower() in placeholder_phrases:
                instruction = result.interpretation or feedback_text
            changes.append(FeedbackChange(
                action=c.action,
                target=target,
                edit_instruction=instruction,
                new_layout=c.new_layout,
                new_position=c.new_position,
                insert_after=c.insert_after,
            ))

        return changes

    # ------------------------------------------------------------------
    # Step 4: Validate plan
    # ------------------------------------------------------------------

    def _validate_plan(
        self,
        changes: list[FeedbackChange],
        outline: list[SlideOutline],
        slides_map: dict,
    ) -> list[FeedbackChange]:
        valid_ids = {s.id for s in outline}
        validated: list[FeedbackChange] = []
        targets_seen: set[str] = set()

        for change in changes:
            # Handle merge target format "id_1+id_2"
            if change.action == "merge_slides" and "+" in change.target:
                parts = change.target.split("+")
                if all(p.strip() in valid_ids for p in parts):
                    change.target = "+".join(p.strip() for p in parts)
                    validated.append(change)
                else:
                    logger.warning("Merge target has invalid IDs: %s", change.target)
                continue

            # Fuzzy match target if not an exact ID
            if change.target not in valid_ids:
                matched = self._fuzzy_match_slide(change.target, outline)
                if matched:
                    logger.info("Fuzzy matched '%s' → '%s'", change.target, matched)
                    change.target = matched
                else:
                    logger.warning("Skipping change: target '%s' not found", change.target)
                    continue

            # Don't apply conflicting actions to the same slide
            if change.action == "delete_slide" and change.target in targets_seen:
                continue
            if change.target in targets_seen and change.action == "delete_slide":
                continue

            # Validate reorder position
            if change.action == "reorder" and change.new_position is not None:
                change.new_position = max(1, min(change.new_position, len(outline)))

            # Validate insert_after for add_slide
            if change.action == "add_slide":
                if change.insert_after and change.insert_after not in valid_ids:
                    change.insert_after = outline[-1].id

            targets_seen.add(change.target)
            validated.append(change)

        return validated

    # ------------------------------------------------------------------
    # Step 6: Execute a single change
    # ------------------------------------------------------------------

    async def _execute_change(
        self,
        change: FeedbackChange,
        outline: list[SlideOutline],
        slides_map: dict,
        retrieval: dict,
        preferences: TeacherPreferences,
        db: AsyncSession,
        deck,
    ) -> list[dict] | None:
        action = change.action

        # --- Structural: no LLM needed ---

        if action == "delete_slide":
            return await self._execute_delete(change, outline, slides_map, db)

        if action == "reorder":
            return self._execute_reorder(change, outline)

        # --- Content edits: LLM edits existing slide ---

        if action in ("edit_content", "edit_table", "edit_notes", "change_tone", "change_layout"):
            return await self._execute_edit(change, outline, slides_map, db, deck)

        # --- Structural + content ---

        if action == "split_slide":
            return await self._execute_split(change, outline, slides_map, db, deck)

        if action == "merge_slides":
            return await self._execute_merge(change, outline, slides_map, db, deck)

        if action == "add_slide":
            return await self._execute_add(change, outline, slides_map, retrieval, preferences, db, deck)

        logger.warning("Unknown action type: %s", action)
        return None

    # ------------------------------------------------------------------
    # Executors
    # ------------------------------------------------------------------

    async def _execute_delete(self, change, outline, slides_map, db) -> list[dict]:
        target = change.target
        outline[:] = [s for s in outline if s.id != target]
        if target in slides_map:
            row = slides_map.pop(target)
            await db.delete(row)
        logger.info("Deleted slide %s", target)
        return []

    def _execute_reorder(self, change, outline) -> list[dict]:
        target = change.target
        new_pos = change.new_position or 1
        idx = next((i for i, s in enumerate(outline) if s.id == target), None)
        if idx is not None:
            slide = outline.pop(idx)
            insert_at = max(0, min(new_pos - 1, len(outline)))
            outline.insert(insert_at, slide)
            logger.info("Reordered slide %s to position %d", target, new_pos)
        return []

    async def _execute_edit(self, change, outline, slides_map, db, deck) -> list[dict]:
        target = change.target
        slide_row = slides_map.get(target)
        if not slide_row:
            logger.warning("Cannot edit %s: not found in DB", target)
            return []

        current_json = json.dumps({
            "title": slide_row.title,
            "body": slide_row.body or "",
            "bullet_points": slide_row.bullet_points or [],
            "table_data": slide_row.table_data,
            "speaker_notes": slide_row.speaker_notes or "",
            "layout_hint": slide_row.layout_hint or "bullet",
        }, indent=2)

        instruction = change.edit_instruction
        if change.action == "change_layout" and change.new_layout:
            instruction += f"\nConvert layout to: {change.new_layout}."
            if change.new_layout == "table":
                instruction += " Include table_data with headers and rows."
        elif change.action == "edit_notes":
            instruction += "\nOnly modify speaker_notes. Keep all other fields exactly the same."
        elif change.action == "edit_table":
            instruction += "\nOnly modify table_data. Keep all other fields exactly the same."
        elif change.action == "change_tone":
            instruction += "\nRestyle the language but keep all facts and structure the same."

        prompt = SLIDE_EDITOR_USER.format(
            current_slide_json=current_json,
            edit_instruction=instruction,
        )

        result = await self._llm.generate_json(
            SLIDE_EDITOR_SYSTEM, prompt, response_model=SlideEditResponse,
        )

        # Apply edits based on action type
        if change.action == "edit_notes":
            slide_row.speaker_notes = result.speaker_notes or slide_row.speaker_notes
        elif change.action == "edit_table":
            slide_row.table_data = result.table_data
            if result.speaker_notes:
                slide_row.speaker_notes = result.speaker_notes
        else:
            slide_row.title = result.title or slide_row.title
            slide_row.body = self._fix_brackets(result.body)
            clean_bps = self._clean_bullet_points(result.bullet_points)
            slide_row.bullet_points = [self._fix_brackets(b) for b in clean_bps]
            slide_row.speaker_notes = result.speaker_notes or slide_row.speaker_notes
            if change.action == "change_layout" and change.new_layout:
                slide_row.layout_hint = change.new_layout
                slide_row.table_data = result.table_data
            elif result.table_data:
                slide_row.table_data = result.table_data
            if result.layout_hint and change.action != "change_layout":
                slide_row.layout_hint = result.layout_hint

        # Sync outline entry
        self._sync_outline_entry(outline, target, slide_row, change)
        await db.commit()

        events = self._emit_slide_events(target, slide_row)
        logger.info("Edited slide %s (%s)", target, change.action)
        return events

    async def _execute_split(self, change, outline, slides_map, db, deck) -> list[dict]:
        target = change.target
        slide_row = slides_map.get(target)
        if not slide_row:
            return []

        current_json = json.dumps({
            "title": slide_row.title,
            "body": slide_row.body or "",
            "bullet_points": slide_row.bullet_points or [],
            "table_data": slide_row.table_data,
            "speaker_notes": slide_row.speaker_notes or "",
            "layout_hint": slide_row.layout_hint or "bullet",
        }, indent=2)

        prompt = SLIDE_SPLITTER_USER.format(
            current_slide_json=current_json,
            edit_instruction=change.edit_instruction,
        )

        result = await self._llm.generate_json(
            SLIDE_SPLITTER_SYSTEM, prompt, response_model=SlideSplitResponse,
        )

        # Update original slide with slide_a content
        a = result.slide_a
        slide_row.title = a.title or slide_row.title
        slide_row.body = self._fix_brackets(a.body)
        slide_row.bullet_points = [self._fix_brackets(b) for b in a.bullet_points]
        slide_row.speaker_notes = a.speaker_notes or slide_row.speaker_notes
        slide_row.layout_hint = a.layout_hint or slide_row.layout_hint

        # Create new slide for slide_b
        idx = next((i for i, s in enumerate(outline) if s.id == target), len(outline) - 1)
        existing_ids = {s.id for s in outline}
        new_id = self._next_slide_id(existing_ids)
        b = result.slide_b

        new_outline_entry = SlideOutline(
            id=new_id,
            position=0,
            type=SlideType.CONTENT,
            title=b.title or "Continued",
            key_points=[bp[:60] for bp in b.bullet_points[:3]],
            layout_hint=LayoutHint(b.layout_hint) if b.layout_hint in LayoutHint.__members__.values() else LayoutHint.BULLET,
            status=SlideStatus.GENERATED,
        )
        outline.insert(idx + 1, new_outline_entry)

        new_slide = await crud.create_slide(db, deck.id, {
            "slide_id": new_id,
            "position": 0,
            "title": b.title or "Continued",
            "body": self._fix_brackets(b.body),
            "bullet_points": [self._fix_brackets(bp) for bp in b.bullet_points],
            "table_data": b.table_data,
            "speaker_notes": b.speaker_notes or "",
            "layout_hint": b.layout_hint or "bullet",
        })
        slides_map[new_id] = new_slide

        # Sync outline for original slide
        self._sync_outline_entry(outline, target, slide_row, change)
        await db.commit()

        events = self._emit_slide_events(target, slide_row)
        events += self._emit_slide_events(new_id, new_slide)
        logger.info("Split slide %s into %s + %s", target, target, new_id)
        return events

    async def _execute_merge(self, change, outline, slides_map, db, deck) -> list[dict]:
        parts = change.target.split("+")
        if len(parts) != 2:
            logger.warning("Merge requires exactly 2 targets, got: %s", change.target)
            return []

        id_a, id_b = parts[0].strip(), parts[1].strip()
        row_a = slides_map.get(id_a)
        row_b = slides_map.get(id_b)
        if not row_a or not row_b:
            logger.warning("Merge targets not found: %s, %s", id_a, id_b)
            return []

        slide_a_json = json.dumps({
            "title": row_a.title, "body": row_a.body or "",
            "bullet_points": row_a.bullet_points or [],
            "table_data": row_a.table_data,
            "speaker_notes": row_a.speaker_notes or "",
            "layout_hint": row_a.layout_hint or "bullet",
        }, indent=2)
        slide_b_json = json.dumps({
            "title": row_b.title, "body": row_b.body or "",
            "bullet_points": row_b.bullet_points or [],
            "table_data": row_b.table_data,
            "speaker_notes": row_b.speaker_notes or "",
            "layout_hint": row_b.layout_hint or "bullet",
        }, indent=2)

        prompt = SLIDE_MERGER_USER.format(
            slide_a_json=slide_a_json,
            slide_b_json=slide_b_json,
            edit_instruction=change.edit_instruction,
        )

        result = await self._llm.generate_json(
            SLIDE_MERGER_SYSTEM, prompt, response_model=SlideEditResponse,
        )

        # Update slide_a with merged content
        row_a.title = result.title or row_a.title
        row_a.body = self._fix_brackets(result.body)
        row_a.bullet_points = [self._fix_brackets(b) for b in result.bullet_points]
        row_a.table_data = result.table_data
        row_a.speaker_notes = result.speaker_notes or row_a.speaker_notes
        row_a.layout_hint = result.layout_hint or row_a.layout_hint

        # Remove slide_b from outline and DB
        outline[:] = [s for s in outline if s.id != id_b]
        await db.delete(row_b)
        slides_map.pop(id_b, None)

        self._sync_outline_entry(outline, id_a, row_a, change)
        await db.commit()

        events = self._emit_slide_events(id_a, row_a)
        logger.info("Merged slides %s + %s into %s", id_a, id_b, id_a)
        return events

    async def _execute_add(self, change, outline, slides_map, retrieval, preferences, db, deck) -> list[dict]:
        # Find insertion point
        insert_after = change.insert_after
        if insert_after:
            idx = next((i for i, s in enumerate(outline) if s.id == insert_after), len(outline) - 1)
        else:
            idx = len(outline) - 1

        # Find relevant chunks from retrieval
        chunks_text = self._find_chunks_for_topic(change.edit_instruction, retrieval)

        # Context from surrounding slides
        prev_summary = "(start of deck)"
        next_summary = "(end of deck)"
        if idx >= 0 and idx < len(outline):
            prev_id = outline[idx].id
            if prev_id in slides_map:
                r = slides_map[prev_id]
                prev_summary = f'"{r.title}" — {(r.bullet_points or [""])[0][:50]}'
        if idx + 1 < len(outline):
            next_id = outline[idx + 1].id
            if next_id in slides_map:
                r = slides_map[next_id]
                next_summary = f'"{r.title}" — {(r.bullet_points or [""])[0][:50]}'

        layout = "bullet"
        if change.new_layout:
            layout = change.new_layout

        prompt = SLIDE_NEW_USER.format(
            edit_instruction=change.edit_instruction,
            layout=layout,
            relevant_chunks=chunks_text or "(No source content available)",
            prev_summary=prev_summary,
            next_summary=next_summary,
        )

        result = await self._llm.generate_json(
            SLIDE_NEW_SYSTEM, prompt, response_model=SlideEditResponse,
        )

        existing_ids = {s.id for s in outline}
        new_id = self._next_slide_id(existing_ids)

        try:
            lh = LayoutHint(result.layout_hint) if result.layout_hint else LayoutHint.BULLET
        except ValueError:
            lh = LayoutHint.BULLET

        new_entry = SlideOutline(
            id=new_id, position=0, type=SlideType.CONTENT,
            title=result.title or change.edit_instruction[:50],
            key_points=[bp[:60] for bp in result.bullet_points[:3]],
            layout_hint=lh, status=SlideStatus.GENERATED,
        )
        outline.insert(idx + 1, new_entry)

        new_slide = await crud.create_slide(db, deck.id, {
            "slide_id": new_id, "position": 0,
            "title": result.title or change.edit_instruction[:50],
            "body": self._fix_brackets(result.body),
            "bullet_points": [self._fix_brackets(b) for b in result.bullet_points],
            "table_data": result.table_data,
            "speaker_notes": result.speaker_notes or "",
            "layout_hint": lh.value,
        })
        slides_map[new_id] = new_slide
        await db.commit()

        events = self._emit_slide_events(new_id, new_slide)
        logger.info("Added new slide %s after %s", new_id, insert_after)
        return events

    # ------------------------------------------------------------------
    # Undo (unchanged logic)
    # ------------------------------------------------------------------

    async def undo_last_feedback(self, deck, db: AsyncSession) -> dict:
        last_round = await crud.get_last_feedback_round(db, deck.id, feedback_type="slide")
        if last_round is None:
            return {"success": False, "message": "No feedback round to undo"}

        if last_round.outline_snapshot_json is not None:
            deck.outline_json = last_round.outline_snapshot_json

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

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_manifest(outline: list[SlideOutline], slides: list) -> str:
        slide_map = {s.slide_id: s for s in slides}
        lines = []
        for entry in outline:
            db_slide = slide_map.get(entry.id)
            if db_slide:
                if db_slide.table_data and isinstance(db_slide.table_data, dict):
                    headers = db_slide.table_data.get("headers", [])
                    rows = db_slide.table_data.get("rows", [])
                    content_str = f"TABLE headers=[{', '.join(headers)}] {len(rows)} rows"
                else:
                    bps = db_slide.bullet_points or []
                    bp_strs = [f'"{bp[:50]}"' for bp in bps[:5]]
                    content_str = "; ".join(bp_strs) if bp_strs else "(empty)"
                    if db_slide.body:
                        content_str = f'body="{db_slide.body[:40]}" | {content_str}'
            else:
                kps = entry.key_points[:3]
                content_str = "; ".join(f'"{kp[:50]}"' for kp in kps) if kps else "(pending)"

            lines.append(
                f'{entry.position}. {entry.id} [{entry.type.value}/{entry.layout_hint.value}] '
                f'"{entry.title}" | {content_str}'
            )
        return "\n".join(lines)

    @staticmethod
    def _sync_outline_entry(outline, slide_id, slide_row, change):
        for entry in outline:
            if entry.id == slide_id:
                entry.title = slide_row.title
                entry.key_points = [
                    bp[:60] for bp in (slide_row.bullet_points or [])[:4]
                ]
                if change.action == "change_layout" and change.new_layout:
                    try:
                        entry.layout_hint = LayoutHint(change.new_layout)
                    except ValueError:
                        pass
                    if change.new_layout == "table":
                        entry.type = SlideType.TABLE
                entry.status = SlideStatus.GENERATED
                break

    @staticmethod
    def _fuzzy_match_slide(target: str, outline: list[SlideOutline]) -> str | None:
        target_lower = target.lower()
        best_id = None
        best_score = 0
        for entry in outline:
            title_lower = entry.title.lower()
            if target_lower in title_lower or title_lower in target_lower:
                score = len(set(target_lower.split()) & set(title_lower.split()))
                if score > best_score:
                    best_score = score
                    best_id = entry.id
        return best_id

    @staticmethod
    def _next_slide_id(existing_ids: set[str]) -> str:
        counter = 1
        while True:
            candidate = f"slide_new_{counter}"
            if candidate not in existing_ids:
                return candidate
            counter += 1

    @staticmethod
    def _find_chunks_for_topic(instruction: str, retrieval: dict) -> str:
        topic_chunks = retrieval.get("topic_chunks", [])
        if not topic_chunks:
            return ""
        instruction_lower = instruction.lower()
        best_chunks: list[str] = []
        for tc in topic_chunks:
            title = tc.get("topic_title", "").lower()
            if any(word in title for word in instruction_lower.split() if len(word) > 3):
                for chunk in tc.get("chunks", [])[:2]:
                    text = chunk.get("parent_content") or chunk.get("content", "")
                    best_chunks.append(text[:200])
        if not best_chunks and topic_chunks:
            for chunk in topic_chunks[0].get("chunks", [])[:2]:
                text = chunk.get("parent_content") or chunk.get("content", "")
                best_chunks.append(text[:200])
        return "\n---\n".join(best_chunks[:3])

    @staticmethod
    def _clean_bullet_points(bps: list[str]) -> list[str]:
        contaminated_prefixes = (
            "speaker_notes:", "layout_hint:", "table_data:", "slide_id:",
            "body:", "title:",
        )
        return [
            bp for bp in bps
            if not bp.strip().lower().startswith(contaminated_prefixes)
        ]

    @staticmethod
    def _fix_brackets(text: str) -> str:
        if not text or "[[" not in text:
            return text
        while "[[[[" in text:
            text = text.replace("[[[[", "[[")
        while "]]]]" in text:
            text = text.replace("]]]]", "]]")
        if text.count("[[") != text.count("]]"):
            text = text.replace("[[", "").replace("]]", "")
        return text

    @staticmethod
    def _emit_slide_events(slide_id: str, slide_row) -> list[dict]:
        position = slide_row.position if hasattr(slide_row, 'position') else 0
        return [
            {"event": "slide_start", "data": {
                "slide_id": slide_id, "position": position,
                "title": slide_row.title, "type": "content",
            }},
            {"event": "slide_content", "data": {
                "slide_id": slide_id, "position": position,
                "title": slide_row.title,
                "body": slide_row.body or "",
                "bullet_points": slide_row.bullet_points or [],
                "table_data": slide_row.table_data,
                "speaker_notes": slide_row.speaker_notes or "",
                "layout_hint": slide_row.layout_hint or "bullet",
            }},
            {"event": "slide_complete", "data": {"slide_id": slide_id}},
        ]

    @staticmethod
    def _complete_event(deck, total, regenerated) -> dict:
        return {
            "event": "generation_complete",
            "data": {
                "total_slides": total,
                "deck_id": str(deck.id),
                "regenerated": regenerated,
                "unchanged": total - regenerated,
                "version": deck.version or 0,
            },
        }
