# Session 09 — Slide Content Generation + SSE Streaming

## Goal
Build per-slide content generation from the outline, with SSE streaming to the frontend. Each slide's content is generated individually by the LLM using its outline entry + retrieved chunks. Tokens stream in real-time. After this session, a deck with an outline can generate full slide content with live streaming.

## Read First
- `docs/sessions/SESSION_TRACKER.md` — confirm Sessions 01-08 complete
- `src/app/schemas/deck.py` — SlideContent, SlideOutline, DeckState
- `src/app/services/llm_client.py` — generate_stream, generate_json
- `src/app/services/prompt_templates.py` — SLIDE_CONTENT_GENERATION template
- `src/app/services/slide_outline.py` — get_chunks_for_slide
- `src/app/services/crud.py` — create_slide, create_slides_bulk
- `docs/FEEDBACK_LOOP_RESEARCH.md` — streaming architecture

## Non-Negotiable Rules
- Generate slides ONE BY ONE in outline order
- Stream tokens via SSE (Server-Sent Events) — user sees content appearing live
- Each slide = 1 LLM call with structured JSON output
- Grounded mode: ONLY use retrieved chunks, no LLM fabrication
- Mixed mode: retrieved chunks as primary, LLM fills small gaps only (not entire sections)
- Previous slide's title/summary passed as context for flow continuity
- Save each slide to DB immediately after generation
- Deck status: outline_ready → generating_slides → completed

## Files to Create

### `services/slide_generator.py` — Slide Generator
```python
class SlideGenerator:
    def __init__(self, llm: LLMClient, outline_service: SlideOutlineService):
        self.llm = llm
        self.outline_svc = outline_service

    async def generate_all_slides(self, deck: Deck,
                                   retrieval: RetrievalResult) -> AsyncGenerator:
        """
        Stage 7: Generate content for all slides, yielding SSE events.
        
        For each slide in outline (ordered by position):
          1. Get outline entry
          2. Get relevant chunks (parent_content) via source_chunk_ids
          3. Get previous slide summary (for flow)
          4. Build prompt with SLIDE_CONTENT_GENERATION template
          5. Include content_mode (grounded/mixed) in prompt
          6. Call LLM → SlideContent (JSON)
          7. Save to DB (Slide model)
          8. Yield SSE events:
             - {"event": "slide_start", "data": {"slide_id": "slide_1", "position": 1}}
             - {"event": "slide_content", "data": {SlideContent JSON}}
             - {"event": "slide_complete", "data": {"slide_id": "slide_1"}}
        
        After all slides:
          9. Update deck status → completed
          10. Yield {"event": "generation_complete", "data": {"total_slides": N}}
        """

    async def generate_single_slide(self, outline_entry: SlideOutline,
                                     chunks: list[str],
                                     prev_slide: SlideContent | None,
                                     preferences: TeacherPreferences) -> SlideContent:
        """
        Generate content for ONE slide.
        1. Build prompt:
           - Slide outline (title, key_points, type, layout_hint)
           - Source chunks (parent_content texts)
           - Previous slide title + key point (for transition)
           - Preferences (tone, level, content_mode)
        2. Call LLM generate_json → SlideContent
        3. Post-process:
           - Ensure bullet_points is a list
           - Ensure speaker_notes is non-empty
           - If table slide → validate table_data structure
        4. Return SlideContent
        """

    def build_slide_prompt(self, outline: SlideOutline, chunks: list[str],
                           prev_slide: SlideContent | None,
                           preferences: TeacherPreferences) -> tuple[str, str]:
        """Build system + user prompt for slide generation."""
        # Content mode instruction:
        # Grounded: "Use ONLY the provided source content below. Do not add any information
        #            not found in the sources. If sources are insufficient, note the gap."
        # Mixed: "Use the provided source content as your primary material. You may add brief
        #         transitions, examples, or clarifications, but do not generate entire sections
        #         from scratch."
```

### SSE Event Types
```
slide_start       → {slide_id, position, title, type}
slide_content     → {slide_id, SlideContent full JSON}
slide_complete    → {slide_id}
generation_error  → {slide_id, error}
generation_complete → {total_slides, deck_id}
```

### Update `api/generate.py` — SSE Streaming Endpoints
```python
from sse_starlette.sse import EventSourceResponse

@router.post("/api/decks/{deck_id}/generate-slides")
async def generate_slides(deck_id: UUID, db = Depends(get_db)):
    """
    Precondition: deck status "outline_ready"
    Returns: SSE stream of slide generation events.
    
    NOTE: This is POST returning SSE. The browser's native EventSource API only
    supports GET. The frontend MUST use fetch() + ReadableStream or a library
    like @microsoft/fetch-event-source to consume this. See Session 13.
    
    Resume support: If the connection drops mid-generation, the frontend can:
    1. GET /slides to see which slides already generated
    2. POST /generate-slides again — it skips slides with status="generated"
       and only generates remaining "pending" slides.
    """
    deck = await get_deck(db, deck_id)
    # Validate status
    retrieval_data = deck.retrieval_json  # loaded from DB, NOT Redis
    
    async def event_generator():
        generator = slide_generator.generate_all_slides(deck, retrieval_data)
        async for event in generator:
            yield {"event": event["event"], "data": json.dumps(event["data"])}
    
    return EventSourceResponse(event_generator())

@router.get("/api/decks/{deck_id}/slides")
async def get_slides(deck_id: UUID, db = Depends(get_db)):
    """Get all generated slides (non-streaming, for page reload or SSE reconnect)."""
    slides = await get_slides_by_deck(db, deck_id)
    return {"slides": [slide.to_dict() for slide in slides]}

@router.get("/api/decks/{deck_id}/generation-status")
async def generation_status(deck_id: UUID, db = Depends(get_db)):
    """
    Returns which slides are generated vs pending.
    Used by frontend to resume after SSE disconnection.
    """
    deck = await get_deck(db, deck_id)
    outline = deck.outline_json or []
    slides = await get_slides_by_deck(db, deck_id)
    generated_ids = {s.slide_id for s in slides}
    return {
        "status": deck.status,
        "total": len(outline),
        "generated": len(generated_ids),
        "pending": [s["id"] for s in outline if s["id"] not in generated_ids]
    }
```

### Resume logic in `generate_all_slides()`
```python
# Skip slides that already have status="generated" in the outline
# This enables resume after SSE disconnect — only pending slides regenerate
for entry in outline:
    if entry.status == "generated":
        continue  # already done, skip
    # generate this slide...
```

### Dependency: `sse-starlette`
Already in pyproject.toml from Session 01.

## Flow
```
1. Create services/slide_generator.py
2. Update api/generate.py with SSE streaming endpoint + GET slides endpoint
3. Add slide saving logic in crud.py if not complete
4. Test SSE streaming with curl
5. Test grounded vs mixed mode
```

## Verification
```bash
# Prerequisites: deck with outline_ready status (from Session 08)

# 1. Generate slides with SSE streaming
curl -N http://localhost:8200/api/decks/<deck_id>/generate-slides -X POST
# Expected: SSE events streaming:
# event: slide_start
# data: {"slide_id":"slide_1","position":1,"title":"..."}
#
# event: slide_content
# data: {"slide_id":"slide_1","title":"...","body":"...","bullet_points":[...]}
#
# event: slide_complete
# data: {"slide_id":"slide_1"}
#
# ... more slides ...
#
# event: generation_complete
# data: {"total_slides":N}

# 2. Get all slides (non-streaming)
curl http://localhost:8200/api/decks/<deck_id>/slides
# Expected: {"slides": [{slide_1 data}, {slide_2 data}, ...]}
# Each slide has: title, body, bullet_points, speaker_notes, layout_hint

# 3. Verify slides in DB
docker compose exec postgres psql -U tcg_user -d teacher_content_gen \
  -c "SELECT slide_id, position, title, layout_hint, char_length(body) FROM slides WHERE deck_id='<deck_id>' ORDER BY position;"
# Expected: all slides with non-empty body

# 4. Check deck status
curl http://localhost:8200/api/decks/<deck_id>
# Expected: status "completed"

# 5. Test grounded mode
# Create a new deck with content_mode "grounded", generate slides
# Verify slide content only references source material

# 6. Test that table slides have table_data
# If outline has table slides, verify table_data is populated JSON
docker compose exec postgres psql -U tcg_user -d teacher_content_gen \
  -c "SELECT slide_id, table_data IS NOT NULL as has_table FROM slides WHERE deck_id='<deck_id>' AND layout_hint='table';"
```

## On Completion
Update `SESSION_TRACKER.md`: mark Session 09 ✅, note SSE streaming working, next → Session 10
