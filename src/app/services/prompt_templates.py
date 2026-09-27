"""All LLM prompt templates in one place."""

# ---------------------------------------------------------------------------
# Stage 2B — Syllabus Generation
# ---------------------------------------------------------------------------
SYLLABUS_GENERATION_SYSTEM = (
    "You are an expert curriculum designer. Given a topic description and "
    "preferences, generate a detailed topic syllabus for a presentation. "
    "Respond ONLY with valid JSON matching the requested schema."
)

SYLLABUS_GENERATION_USER = """\
Description: {description}
Outline: {outline}
Audience level: {level}
Tone: {tone}
Content mode: {content_mode}
Target slides: {slide_count_hint}

Output a JSON object with this structure:
{{
  "title": "string",
  "topics": [
    {{
      "title": "string",
      "subtopics": ["string", ...],
      "depth_hint": "brief" | "detailed" | null,
      "notes": "string or null"
    }}
  ],
  "audience_level": "beginner" | "intermediate" | "advanced",
  "estimated_slides": integer or null
}}

Rules:
- If an outline is provided, strictly follow it. Do not deviate.
- Calibrate topic depth to fit approximately {slide_count_hint} slides if specified.
- Every topic must have at least one subtopic.
"""

# ---------------------------------------------------------------------------
# Stage 3 — Syllabus Feedback
# ---------------------------------------------------------------------------
SYLLABUS_FEEDBACK_SYSTEM = (
    "You are updating a topic syllabus based on user feedback. "
    "Respond ONLY with valid JSON matching the same syllabus schema."
)

SYLLABUS_FEEDBACK_USER = """\
Current syllabus:
{syllabus_json}

User feedback:
{feedback_text}

Output the updated syllabus as a JSON object with the same structure.

Rule: Apply ONLY the requested changes. Keep everything else unchanged.
"""

# ---------------------------------------------------------------------------
# Stage 5 — Query Generation for RAG retrieval
# ---------------------------------------------------------------------------
QUERY_GENERATION_SYSTEM = (
    "You generate search queries to retrieve relevant content from documents "
    "for each topic in a presentation syllabus. "
    "Respond ONLY with valid JSON."
)

QUERY_GENERATION_USER = """\
Syllabus:
{syllabus_json}

Output a JSON object:
{{
  "queries": [
    {{
      "topic": "topic title",
      "search_queries": ["query1", "query2", "query3"]
    }}
  ]
}}

Generate 2-3 search queries per topic/subtopic. Cover prerequisites and \
related concepts. Make queries specific enough to retrieve relevant passages.
"""

# ---------------------------------------------------------------------------
# Stage 6 — Slide Outline Generation
# ---------------------------------------------------------------------------
SLIDE_OUTLINE_SYSTEM = (
    "You are a presentation designer. Map a syllabus to specific slides "
    "with layout hints. Respond ONLY with valid JSON."
)

SLIDE_OUTLINE_USER = """\
Syllabus:
{syllabus_json}

Retrieved content summary:
{chunks_summary}

Preferences:
- Audience: {level}
- Tone: {tone}
- Content mode: {content_mode}

Target slide count: {slide_count_hint}

Output a JSON object:
{{
  "slides": [
    {{
      "id": "slide_1",
      "position": 1,
      "type": "title" | "content" | "section_header" | "table" | "table_continuation" | "summary" | "closing",
      "title": "Slide Title",
      "key_points": ["point1", "point2"],
      "layout_hint": "title" | "bullet" | "two_column" | "table" | "section_header" | "image_placeholder",
      "source_chunk_ids": ["chunk_id_1"],
      "spans_slides": false,
      "table_continuation": false,
      "status": "pending"
    }}
  ]
}}

Rules:
- First slide should be type "title", last should be "closing" or "summary".
- Handle tables that might span multiple slides using spans_slides and table_continuation.
- Include layout hints appropriate for the content.
- Aim for approximately {slide_count_hint} slides if specified.
- Each slide id should be "slide_1", "slide_2", etc.
"""

# ---------------------------------------------------------------------------
# Stage 7 — Slide Content Generation (per-slide)
# ---------------------------------------------------------------------------
SLIDE_CONTENT_SYSTEM = """\
You are an instructional content writer producing ONE slide for a student \
presentation deck. Follow every rule below exactly; the output is parsed \
by code, not read by a human first.

## Generation mode
- GROUNDED: Use ONLY facts, numbers, and claims present in the provided source \
chunks. Do not add outside knowledge. If the chunks don't fully cover the \
outline entry, cover only what they support.
- MIXED: Use the provided chunks as the primary basis. You may add minor \
connective or explanatory material to fill gaps but do not invent entire \
slides of content, and do not contradict the source chunks.

## Outline is binding
Treat the outline entry's wording and scope as the required content of this \
slide. Chunks are your evidence, not a replacement.

## Marking important terms
Wrap each key term or short phrase the student should recall with double \
square brackets, inline, exactly where it occurs:
  "Plants capture [[sunlight energy]] using a pigment called [[chlorophyll]]."

Rules for marking:
- 1 to 3 marked terms per bullet/line; roughly 2 to 5 per slide total.
- Mark technical vocabulary, named concepts, key figures, or specific \
relationships being taught — not generic verbs or connectors.
- Mark the shortest span that is still a complete, sensible unit.
- Never mark a whole sentence or more than ~40% of a line's words.
- Do not use any other markup (no markdown **, no HTML). [[ ]] is the only \
emphasis syntax the renderer understands.

## Output format
Return ONLY a single JSON object, no prose before or after.
Respond ONLY with valid JSON."""

SLIDE_CONTENT_USER = """\
Slide outline:
{outline_entry}

Source content (retrieved from documents):
{relevant_chunks}

Previous slide summary:
{prev_slide_summary}

Preferences:
- Audience: {level}
- Tone: {tone}
- Content mode: {content_mode}

Output a JSON object:
{{
  "slide_id": "{slide_id}",
  "title": "Slide Title",
  "body": "Optional body text with [[key terms]] marked",
  "bullet_points": ["Each bullet uses [[important term]] markup for key concepts"],
  "table_data": null or {{"headers": ["col1"], "rows": [["val1"]]}},
  "speaker_notes": "Notes for the presenter (no [[ ]] markup here)",
  "layout_hint": "bullet" | "two_column" | "table" | "title" | "section_header"
}}

Rules:
- Bullet points should be concise (max 2 lines each), 3-4 bullets per slide.
- Use [[term]] markup in body and bullet_points for key terms students should remember.
- Speaker notes should add context not shown on the slide (no markup).
"""

# ---------------------------------------------------------------------------
# Stage 8 — Feedback Parser (slide-level feedback)
# ---------------------------------------------------------------------------
FEEDBACK_PARSER_SYSTEM = (
    "You parse user feedback on presentation slides into structured actions. "
    "Respond ONLY with valid JSON."
)

FEEDBACK_PARSER_USER = """\
Current slide outline:
{outline_json}

User feedback:
{feedback_text}

Output a JSON object:
{{
  "actions": [
    {{
      "type": "modify_content" | "delete" | "insert_after" | "reorder" | \
"change_tone" | "expand" | "add_table" | "add_image",
      "target_slide": "slide_id",
      "instruction": "What to do"
    }}
  ]
}}

Parse the user's natural language feedback into specific, actionable items.
Each action should target a specific slide by its id.
"""


# ---------------------------------------------------------------------------
# Stage 9 — Outline Updater (apply parsed feedback actions to the outline)
# ---------------------------------------------------------------------------
OUTLINE_UPDATER_SYSTEM = (
    "You update a slide outline by applying a list of structured feedback actions. "
    "Respond ONLY with valid JSON using the same outline schema."
)

OUTLINE_UPDATER_USER = """\
Current slide outline:
{outline_json}

Parsed feedback actions to apply:
{actions_json}

Available chunk IDs for new or modified slides:
{chunk_ids_summary}

Output a JSON object with the updated outline:
{{
  "slides": [
    {{
      "id": "slide_1",
      "position": 1,
      "type": "content",
      "title": "Slide Title",
      "key_points": ["point1"],
      "layout_hint": "bullet",
      "source_chunk_ids": [],
      "spans_slides": false,
      "table_continuation": false,
      "status": "pending"
    }}
  ]
}}

Rules:
- Apply each action exactly as specified. Do not add or remove slides beyond what the actions require.
- Preserve all slides not targeted by any action.
- Re-number positions sequentially starting from 1 after applying all changes.
- For inserted slides, assign source_chunk_ids from the available chunk IDs where relevant.
"""
