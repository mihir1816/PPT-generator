# Session 06 — Topic Syllabus Generation + Feedback Loop #1

## Goal
Build the topic syllabus generation flow and its feedback loop. The LLM generates a curriculum from the teacher's description (+ optional outline). User can review and iterate on the syllabus before any content generation or RAG retrieval begins. After this session, the full Stage 2B → Stage 3 flow works end-to-end.

## Read First
- `docs/sessions/SESSION_TRACKER.md` — confirm Sessions 01-05 complete
- `src/app/schemas/syllabus.py` — TopicSyllabus, SyllabusTopic, SyllabusFeedback
- `src/app/schemas/deck.py` — TeacherPreferences, DeckState
- `src/app/services/llm_client.py` — LLMClient (generate_json)
- `src/app/services/prompt_templates.py` — SYLLABUS_GENERATION, SYLLABUS_FEEDBACK
- `src/app/services/crud.py` — create_deck, update_deck_syllabus
- `docs/FEEDBACK_LOOP_RESEARCH.md` — feedback handling patterns

## Non-Negotiable Rules
- If user provides an outline → LLM STRICTLY follows it, no deviation
- If no outline → LLM generates its own syllabus freely
- Syllabus must be approved before proceeding to RAG (Stage 4 wait gate)
- Each feedback round is saved in DB (FeedbackRound with type="syllabus")
- Syllabus stored as JSON in Deck.syllabus_json
- Deck status transitions (using DeckStatus enum from schemas/common.py): pending → generating_syllabus → syllabus_review → (feedback loop) → waiting_for_indexing | ready_for_retrieval

## Files to Create

### `services/syllabus.py` — Syllabus Service
```python
class SyllabusService:
    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    async def generate_syllabus(self, description: str, outline: str | None,
                                 preferences: TeacherPreferences) -> TopicSyllabus:
        """
        Stage 2B: Generate topic syllabus from teacher input.
        1. Build prompt using SYLLABUS_GENERATION template
        2. If outline provided → inject into prompt with STRICT FOLLOW instruction
        3. If no outline → prompt says "create your own"
        4. Call LLM with generate_json → TopicSyllabus
        5. Validate: at least 1 topic, reasonable structure
        6. Return TopicSyllabus
        """

    async def apply_feedback(self, current_syllabus: TopicSyllabus,
                              feedback_text: str) -> TopicSyllabus:
        """
        Stage 3: Apply user feedback to syllabus.
        1. Build prompt using SYLLABUS_FEEDBACK template
        2. Include current syllabus JSON + user's feedback text
        3. Call LLM with generate_json → updated TopicSyllabus
        4. Validate structure
        5. Return updated TopicSyllabus
        """
```

### `api/syllabus.py` — Syllabus Endpoints

```
POST /api/decks
    Body: { document_ids: list[UUID], description: str, outline: str | None,
            preferences: {audience_level, tone, content_mode} }
    Flow:
      1. Create Deck record (status=pending)
      2. Link documents via DeckDocument
      3. Start background: check if all documents are indexed
      4. Call syllabus_service.generate_syllabus()
      5. Save syllabus to Deck.syllabus_json
      6. Update Deck status → syllabus_review
      7. Return { deck_id, syllabus: TopicSyllabus, status: "syllabus_review" }

GET /api/decks/{deck_id}
    Returns: deck status, syllabus, indexing progress

POST /api/decks/{deck_id}/syllabus-feedback
    Body: { feedback: str }
    Flow:
      1. Load current syllabus from Deck
      2. Save FeedbackRound (type=syllabus, raw_feedback, snapshot of current syllabus)
      3. Call syllabus_service.apply_feedback()
      4. Update Deck.syllabus_json with new version
      5. Increment Deck.version
      6. Return { syllabus: updated TopicSyllabus }

POST /api/decks/{deck_id}/syllabus-approve
    Flow:
      1. Mark Deck.syllabus_status → approved
      2. Attempt atomic wait gate: try_transition_to_ready()
      3. If transitioned → Return { status: "ready_for_retrieval" }
      4. If not (docs still indexing) → Update Deck status → waiting_for_indexing
      5. Return { status: "waiting_for_indexing", message: "Documents still processing" }
```

### Parallel Processing Logic

The wait gate (Stage 4) checks TWO conditions:
1. Syllabus is approved (`syllabus_status == "approved"`)
2. All linked documents have `is_indexed = True`

**Race condition risk**: This check runs from two places simultaneously (API server + Celery worker). Without atomic transitions, both could check, both see the other incomplete, and neither transitions the deck.

**Solution**: Use an atomic `UPDATE ... WHERE` to make the transition race-safe:
```python
# ASYNC version (API server — in syllabus-approve endpoint)
async def try_transition_to_ready(db: AsyncSession, deck_id: UUID) -> bool:
    """Atomically transition deck to ready_for_retrieval if both conditions met."""
    result = await db.execute(
        text("""
            UPDATE decks SET status = 'ready_for_retrieval'
            WHERE id = :deck_id
              AND syllabus_status = 'approved'
              AND status IN ('syllabus_review', 'waiting_for_indexing')
              AND NOT EXISTS (
                  SELECT 1 FROM deck_documents dd
                  JOIN documents d ON d.id = dd.document_id
                  WHERE dd.deck_id = :deck_id AND d.is_indexed = FALSE
              )
            RETURNING id
        """),
        {"deck_id": str(deck_id)}
    )
    await db.commit()
    return result.fetchone() is not None

# SYNC version (Celery worker — at end of index_document_task)
def try_transition_to_ready_sync(db: Session, deck_id: UUID) -> bool:
    """Same atomic check, sync version for Celery."""
    result = db.execute(
        text("""... same SQL ..."""),
        {"deck_id": str(deck_id)}
    )
    db.commit()
    return result.fetchone() is not None
```

The `UPDATE ... WHERE` with all conditions in the WHERE clause is atomic at the database level — only one process can successfully update. No advisory locks needed.

This check runs:
- When syllabus is approved (in `/syllabus-approve` endpoint) → `try_transition_to_ready()`
- When a document finishes indexing (at end of `index_document_task`) → `try_transition_to_ready_sync()`
- If the deck was in `waiting_for_indexing`, the indexing completion triggers the transition
- If the deck was in `syllabus_review`, the approval triggers the transition

### Update `tasks/indexing.py`
At the end of `index_document_task`, after marking document as indexed:
```python
# Check if any deck is waiting for this document (SYNC — Celery worker)
deck_ids = get_decks_waiting_for_document_sync(db, document_id)
for deck_id in deck_ids:
    try_transition_to_ready_sync(db, deck_id)
```

## Flow
```
1. Create services/syllabus.py
2. Create api/syllabus.py with 4 endpoints
3. Add wait gate logic (check_wait_gate function)
4. Update tasks/indexing.py to trigger wait gate check
5. Register syllabus router in main.py
6. Add crud helpers: get_deck_document_ids, get_documents_by_ids, get_decks_waiting_for_document
7. Test syllabus generation + feedback + approve flow
```

## Verification
```bash
# Prerequisites: at least 1 document uploaded and indexed from Session 03-04

# 1. Create deck + generate syllabus
curl -X POST http://localhost:8200/api/decks \
  -H "Content-Type: application/json" \
  -d '{
    "document_ids": ["<doc_uuid>"],
    "description": "Create a presentation about machine learning basics for beginners",
    "outline": null,
    "preferences": {"audience_level": "beginner", "tone": "creative", "content_mode": "mixed"}
  }'
# Expected: { "deck_id": "...", "syllabus": { "topics": [...] }, "status": "syllabus_review" }
# Verify syllabus has multiple topics with subtopics

# 2. Test with user-provided outline
curl -X POST http://localhost:8200/api/decks \
  -H "Content-Type: application/json" \
  -d '{
    "document_ids": ["<doc_uuid>"],
    "description": "Machine learning presentation",
    "outline": "1. What is ML?\n2. Types of ML\n3. Linear Regression\n4. Decision Trees\n5. Summary",
    "preferences": {"audience_level": "intermediate", "tone": "formal", "content_mode": "grounded"}
  }'
# Expected: syllabus STRICTLY follows the 5 topics from outline

# 3. Send feedback
curl -X POST http://localhost:8200/api/decks/<deck_id>/syllabus-feedback \
  -H "Content-Type: application/json" \
  -d '{"feedback": "Remove the Decision Trees topic and expand Linear Regression into two topics: theory and implementation"}'
# Expected: updated syllabus without Decision Trees, with expanded Linear Regression

# 4. Approve syllabus
curl -X POST http://localhost:8200/api/decks/<deck_id>/syllabus-approve
# Expected: {"status": "ready_for_retrieval"} if docs indexed, else "waiting_for_indexing"

# 5. Check deck status
curl http://localhost:8200/api/decks/<deck_id>
# Expected: full deck state with syllabus + status

# 6. Verify feedback saved
docker compose exec postgres psql -U tcg_user -d teacher_content_gen \
  -c "SELECT round_number, feedback_type, char_length(raw_feedback) FROM feedback_rounds WHERE deck_id='<deck_id>';"
# Expected: rows with feedback_type='syllabus'
```

## On Completion
Update `SESSION_TRACKER.md`: mark Session 06 ✅, note syllabus + feedback loop working, next → Session 07
