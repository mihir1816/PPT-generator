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
SLIDE_CONTENT_SYSTEM = (
    "You generate content for one presentation slide. "
    "Respond ONLY with valid JSON."
)

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
  "body": "Optional body text",
  "bullet_points": ["point 1", "point 2"],
  "table_data": null or {{"headers": ["col1"], "rows": [["val1"]]}},
  "speaker_notes": "Notes for the presenter",
  "layout_hint": "bullet" | "two_column" | "table" | "title" | "section_header" | "image_placeholder"
}}

Rules:
- Grounded mode: ONLY use provided source content. Do not add external info.
- Mixed mode: Use source content as primary. Add brief filler/transitions \
where needed but do not generate entire sections from scratch.
- Bullet points should be concise (max 2 lines each).
- Speaker notes should add context not shown on the slide.
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

