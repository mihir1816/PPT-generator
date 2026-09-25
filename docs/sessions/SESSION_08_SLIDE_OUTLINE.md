# Session 08 — Slide Outline Generation

## Goal
Build the slide outline generation stage. LLM takes the approved syllabus + retrieved chunks + preferences and maps topics to specific slides (handling table splits, layout hints, slide ordering). After this session, a deck with retrieved content can produce a structured slide outline.

## Read First
- `docs/sessions/SESSION_TRACKER.md` — confirm Sessions 01-07 complete
- `src/app/schemas/deck.py` — SlideOutline, SlideType, SlideStatus
- `src/app/services/llm_client.py` — generate_json
- `src/app/services/prompt_templates.py` — SLIDE_OUTLINE_GENERATION template
- `src/app/services/rag.py` — RetrievalResult, TopicChunks
- `src/app/services/crud.py` — update_deck_outline
- `docs/FEEDBACK_LOOP_RESEARCH.md` — outline structure

## Non-Negotiable Rules
- Outline is the SINGLE SOURCE OF TRUTH for all slide content
- Each slide maps to specific source chunks (via source_chunk_ids)
- Tables that don't fit 1 slide → split with `spans_slides` + `table_continuation`
- Slide types: title, content, section_header, table, table_continuation, summary, closing
- Every slide has a layout_hint: title, bullet, two_column, table, image_placeholder
- Outline stored as JSON in Deck.outline_json
- Deck status: retrieval_complete → generating_outline → outline_ready

## Files to Create

### `services/slide_outline.py` — Slide Outline Service
```python
class SlideOutlineService:
    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    async def generate_outline(self, syllabus: TopicSyllabus,
                                retrieval: RetrievalResult,
                                preferences: TeacherPreferences) -> list[SlideOutline]:
        """
        Stage 6: Generate slide-level outline.
        
        Flow:
        1. Build chunks summary: for each topic, summarize available content
           (don't send full chunks to outline prompt — too long)
        2. Build prompt with SLIDE_OUTLINE_GENERATION template
        3. Include: syllabus, content availability per topic, preferences
        4. Call LLM generate_json → list[SlideOutline]
        5. Post-process:
           a. Assign sequential IDs (slide_1, slide_2, ...)
           b. Assign positions (1, 2, 3, ...)
           c. Validate table spans (if spans_slides, ensure continuation exists)
           d. Set all statuses to "pending"
           e. Map source_chunk_ids from retrieval results
        6. Return validated outline
        """

    def summarize_chunks_for_outline(self, topic_chunks: list[TopicChunks]) -> str:
        """
        Create a brief summary of available content per topic.
        NOT full chunk text — just: topic X has N chunks covering [brief description].
        Keeps outline prompt small.
        """

    def validate_outline(self, outline: list[SlideOutline]) -> list[SlideOutline]:
        """
        Post-validation:
        - Sequential IDs and positions
        - Table continuations reference valid parent slides
        - At least 1 content slide
        - Title slide at position 1
        - No duplicate IDs
        """

    def get_chunks_for_slide(self, slide: SlideOutline,
                              retrieval: RetrievalResult) -> list[str]:
        """
        Given a slide's source_chunk_ids, return the actual parent_content texts.
        Used by content generation in Session 09.
        """
```

### Update `api/generate.py` — Add outline endpoint
```
POST /api/decks/{deck_id}/generate-outline
    Precondition: deck status "retrieval_complete"
    Flow:
      1. Load deck (syllabus, preferences)
      2. Load retrieval result from Deck.retrieval_json (stored in DB by Session 07)
      3. Call slide_outline_service.generate_outline()
      4. Save outline to Deck.outline_json
      5. Update deck status → "outline_ready"
      6. Return { outline: list[SlideOutline], slide_count: N }
```

**Retrieval data storage**: Retrieval results are stored in `Deck.retrieval_json` (DB column, added in Session 02). NOT in Redis with TTL — retrieval data is needed throughout the entire feedback lifecycle which can span hours/days. A Redis TTL would expire mid-workflow causing silent failures.

## Flow
```
1. Create services/slide_outline.py
2. Update api/generate.py with outline endpoint
3. Add retrieval result caching in Redis
4. Add crud helper: update_deck_outline
5. Register endpoint in main.py if not already
6. Test outline generation
```

## Verification
```bash
# Prerequisites: deck with retrieval_complete status (from Session 07)

# 1. Generate outline
curl -X POST http://localhost:8200/api/decks/<deck_id>/generate-outline
# Expected: {
#   "outline": [
#     {"id": "slide_1", "type": "title", "title": "...", "position": 1, ...},
#     {"id": "slide_2", "type": "content", "title": "...", "key_points": [...], ...},
#     ...
#   ],
#   "slide_count": N
# }

# 2. Verify outline structure
# - First slide should be type "title"
# - Content slides should have key_points and source_chunk_ids
# - If table slides exist, verify spans_slides + continuation pairs
# - All statuses should be "pending"

# 3. Check outline saved in DB
docker compose exec postgres psql -U tcg_user -d teacher_content_gen \
  -c "SELECT status, version, jsonb_array_length(outline_json) as slide_count FROM decks WHERE id='<deck_id>';"
# Expected: status=outline_ready, slide_count > 0

# 4. Test validation
docker compose exec app python -c "
from app.services.slide_outline import SlideOutlineService
from app.schemas.deck import SlideOutline, SlideType, SlideStatus
test_outline = [
    SlideOutline(id='slide_1', position=1, type=SlideType.TITLE, title='Test'),
    SlideOutline(id='slide_2', position=2, type=SlideType.CONTENT, title='Topic A', key_points=['point 1']),
]
svc = SlideOutlineService(None)
validated = svc.validate_outline(test_outline)
assert validated[0].id == 'slide_1'
assert validated[1].position == 2
print('Validation OK')
"

# 5. Deck status is correct
curl http://localhost:8200/api/decks/<deck_id>
# Expected: status "outline_ready"
```

## On Completion
Update `SESSION_TRACKER.md`: mark Session 08 ✅, note outline generation working, next → Session 09
