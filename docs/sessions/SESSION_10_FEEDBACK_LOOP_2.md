# Session 10 — Feedback Loop #2 (Slide Content)

## Goal
Build the slide content feedback loop. User reviews generated slides, gives feedback (expand, edit, add, remove, reorder), system parses feedback → updates slide outline → regenerates ONLY affected slides. Unaffected slides stay untouched. Includes undo via outline snapshots. After this session, the full Stage 8 feedback cycle works.

## Read First
- `docs/sessions/SESSION_TRACKER.md` — confirm Sessions 01-09 complete
- `src/app/schemas/deck.py` — SlideOutline, SlideContent, SlideStatus
- `src/app/services/llm_client.py` — generate_json
- `src/app/services/prompt_templates.py` — FEEDBACK_PARSER, OUTLINE_UPDATER
- `src/app/services/slide_generator.py` — generate_single_slide
- `src/app/services/crud.py` — update_deck_outline, create_feedback_round
- `src/app/models/feedback.py` — FeedbackRound model
- `docs/FEEDBACK_LOOP_RESEARCH.md` — full feedback architecture

## Non-Negotiable Rules
- Parse feedback with LLM → structured actions (1 LLM call)
- Update outline FIRST, then regenerate affected slides
- NEVER regenerate unaffected slides — they must remain identical
- Mark affected slides: status → "needs_regeneration" or "pending" (new)
- Save outline snapshot BEFORE applying changes (for undo)
- Each feedback round saved as FeedbackRound in DB
- Support undo: restore previous outline snapshot
- Deck version increments on every feedback round
- Conversation history: include last 2-3 feedback rounds in LLM context

## Files to Create

### `services/feedback.py` — Feedback Service
```python
class FeedbackService:
    def __init__(self, llm: LLMClient, slide_generator: SlideGenerator):
        self.llm = llm
        self.generator = slide_generator

    async def process_feedback(self, deck: Deck, feedback_text: str,
                                retrieval: RetrievalResult,
                                db: AsyncSession) -> FeedbackResult:
        """
        Full Stage 8 pipeline:
        
        Step 1: SNAPSHOT — save current outline AND affected slide content for undo
          - outline_snapshot: current deck.outline_json
          - slides_snapshot: full slide data for slides that will be affected
            (loaded from DB BEFORE changes — stored in FeedbackRound.slides_snapshot_json)
        
        Step 2: PARSE FEEDBACK (1 LLM call)
          Input: current outline + feedback text + last 2-3 feedback summaries
          Output: list of FeedbackAction:
            - modify_content(target_slide, instruction)
            - delete(target_slide)
            - insert_after(target_slide, instruction)
            - reorder(target_slide, new_position)
            - expand(target_slide, instruction)
            - change_tone(target: "all" | slide_id, instruction)
            - add_table(target_slide, instruction)
            - add_image(target_slide, instruction)
        
        Step 3: UPDATE OUTLINE
          Apply each action:
          - delete → remove from outline, renumber
          - insert_after → add new entry with status="pending", renumber
          - modify_content → update key_points, status="needs_regeneration"
          - expand → update key_points (add more), maybe fetch more chunks, status="needs_regeneration"
          - reorder → change positions
          - change_tone (all) → mark ALL slides "needs_regeneration"
          - add_table/image → update layout_hint, status="needs_regeneration"
        
        Step 4: IDENTIFY AFFECTED SLIDES
          Scan outline for status != "generated"
          Build list of slides to regenerate
        
        Step 5: REGENERATE ONLY AFFECTED
          For each affected slide:
            generate_single_slide(outline_entry, chunks, prev_slide, preferences)
          Stream via SSE (same as Session 09)
          Save to DB (update existing slide or create new)
        
        Step 6: UPDATE STATE
          - All statuses → "generated"
          - Increment deck version
          - Save FeedbackRound to DB
          - Return FeedbackResult
        """

    async def parse_feedback(self, outline: list[SlideOutline],
                              feedback_text: str,
                              history: list[dict]) -> list[FeedbackAction]:
        """LLM parses feedback into structured actions."""

    def apply_actions_to_outline(self, outline: list[SlideOutline],
                                  actions: list[FeedbackAction]) -> list[SlideOutline]:
        """
        Apply actions to outline. Pure function — no DB or LLM.
        Returns new outline with statuses updated.
        """

    def get_affected_slides(self, outline: list[SlideOutline]) -> list[SlideOutline]:
        """Return slides with status pending or needs_regeneration."""

    async def undo_last_feedback(self, deck: Deck, db: AsyncSession) -> list[SlideOutline]:
        """
        Restore outline AND slides from last FeedbackRound's snapshots.
        1. Load last FeedbackRound from DB
        2. Restore Deck.outline_json from outline_snapshot_json
        3. Restore affected slides from slides_snapshot_json:
           - For each slide in snapshot: update the Slide row with snapshot data
           - For slides that were newly inserted: delete them
           - For slides that were deleted: re-create them from snapshot
        4. Decrement Deck.version
        5. Delete the FeedbackRound (so next undo goes to the round before)
        """

@dataclass
class FeedbackAction:
    type: str       # modify_content, delete, insert_after, reorder, expand, change_tone, add_table, add_image
    target: str     # slide_id or "all"
    instruction: str
    new_position: int | None = None  # for reorder

@dataclass
class FeedbackResult:
    updated_outline: list[SlideOutline]
    affected_slide_ids: list[str]
    regenerated_count: int
    unchanged_count: int
    version: int
```

### Conversation History Management
```python
def build_feedback_history(feedback_rounds: list[FeedbackRound],
                           window_size: int = 3) -> list[dict]:
    """
    Sliding window: keep last `window_size` rounds as full text.
    Older rounds: 1-line summary only.
    Returns list of {round, feedback_summary} for LLM context.
    """
```

### Update `api/feedback.py` — Feedback Endpoints
```
POST /api/decks/{deck_id}/slide-feedback
    Body: { feedback: str }
    Returns: SSE stream of regenerated slides (same format as Session 09)
    
    NOTE: This is POST returning SSE. Native EventSource cannot handle POST.
    Frontend MUST use fetch() + ReadableStream or @microsoft/fetch-event-source.
    See Session 13 for frontend implementation.
    
    Flow:
      1. Load deck + retrieval data from Deck.retrieval_json
      2. Snapshot current outline + affected slides to FeedbackRound
      3. feedback_service.process_feedback(deck, feedback_text, retrieval, db)
      4. Stream ONLY regenerated slides via SSE
      5. Return affected/unchanged counts in final event

POST /api/decks/{deck_id}/undo
    Returns: { outline: restored outline, slides: restored slides, message }
    Flow:
      1. Load last FeedbackRound
      2. Restore outline from outline_snapshot_json
      3. Restore slides from slides_snapshot_json (see undo_last_feedback)
      4. Decrement version
      5. Delete the consumed FeedbackRound
```

Register feedback router in `main.py`.

## Flow
```
1. Create services/feedback.py
2. Create api/feedback.py (feedback + undo endpoints)
3. Add conversation history builder
4. Register router in main.py
5. Test feedback → selective regeneration
6. Test undo
```

## Verification
```bash
# Prerequisites: deck with completed slides (from Session 09)

# 1. Send feedback — modify one slide
curl -N -X POST http://localhost:8200/api/decks/<deck_id>/slide-feedback \
  -H "Content-Type: application/json" \
  -d '{"feedback": "Expand slide 3 with more details about the algorithm"}'
# Expected: SSE stream with ONLY slide_3 regenerated
# Other slides NOT in the stream

# 2. Verify only affected slide changed
curl http://localhost:8200/api/decks/<deck_id>/slides
# Compare: slide_3 should have different/longer content, all others identical

# 3. Send feedback — delete a slide
curl -N -X POST http://localhost:8200/api/decks/<deck_id>/slide-feedback \
  -H "Content-Type: application/json" \
  -d '{"feedback": "Remove slide 2, it is not needed"}'
# Expected: slide count decreased by 1, positions renumbered

# 4. Send feedback — add a slide
curl -N -X POST http://localhost:8200/api/decks/<deck_id>/slide-feedback \
  -H "Content-Type: application/json" \
  -d '{"feedback": "Add a new slide after slide 1 that introduces the key terminology"}'
# Expected: new slide generated, positions adjusted

# 5. Test undo
curl -X POST http://localhost:8200/api/decks/<deck_id>/undo
# Expected: outline reverted to before last feedback

# 6. Verify feedback rounds in DB
docker compose exec postgres psql -U tcg_user -d teacher_content_gen \
  -c "SELECT round_number, feedback_type, jsonb_array_length(affected_slide_ids::jsonb) as affected FROM feedback_rounds WHERE deck_id='<deck_id>' ORDER BY round_number;"
# Expected: multiple rounds, affected counts match expectations

# 7. Verify unaffected slides unchanged
# Before feedback, note slide_1 body text
# After feedback that only affects slide_3, slide_1 body should be byte-identical
```

## On Completion
Update `SESSION_TRACKER.md`: mark Session 10 ✅, note feedback + undo working, next → Session 11
