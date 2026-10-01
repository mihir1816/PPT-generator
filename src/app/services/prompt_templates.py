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
- The presentation MUST produce exactly {slide_count_hint} slides (including title and closing). Calibrate topic depth and count to hit this number precisely.
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
- YOU MUST GENERATE EXACTLY {slide_count_hint} SLIDES TOTAL — NO MORE NO LESS. This is a strict requirement, not a suggestion. Count your slides carefully before outputting.
- First slide should be type "title", last should be "closing" or "summary".
- Handle tables that might span multiple slides using spans_slides and table_continuation.
- Include layout hints appropriate for the content.
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
- Use EXACTLY two opening brackets and two closing brackets: [[term]]. \
Never use single brackets [term], triple [[[term]]], or nested [[[[term]]]].
- Do not use any other markup (no markdown **, no HTML, no *italic*). \
[[ ]] is the only emphasis syntax the renderer understands.

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
- Keep bullet points concise and focused, but adjust their length according to the importance and complexity of the concept. Use 2-3 lines for simple or precise concepts and allow 5-6 lines when additional explanation is necessary for student understanding. Prioritize clarity and sufficient conceptual coverage over strict length limits. Typically use 5-6 meaningful bullets per slide, but allow fewer or more when the topic requires it. Since the faculty will provide further explanation, include the essential information students need to understand and revise the concept without overcrowding the slides.

- Use [[term]] markup (exactly two brackets each side) in body and bullet_points for 2-5 key terms per slide. Never use single brackets, triple brackets, or nested brackets.
- Speaker notes should add context not shown on the slide (no [[ ]] markup).
"""

# ---------------------------------------------------------------------------
# Stage 8 — Feedback Analyzer (understands intent, creates change plan)
# ---------------------------------------------------------------------------
FEEDBACK_ANALYZER_SYSTEM = """\
You analyze user feedback on presentation slides and create a precise change \
plan. You see a manifest showing what is on each slide. \
Respond ONLY with valid JSON."""

FEEDBACK_ANALYZER_USER = """\
Slide manifest (position. id [type/layout] "title" | content):
{manifest}

User feedback:
{feedback_text}
{history_section}
Output a JSON object:
{{
  "interpretation": "One sentence: what the user wants",
  "changes": [
    {{
      "action": "edit_content",
      "target": "slide_id",
      "edit_instruction": "Specific instruction",
      "new_layout": null,
      "new_position": null,
      "insert_after": null
    }}
  ]
}}

action must be one of:
- edit_content: modify bullets/body/title of an existing slide
- edit_table: modify table headers, rows, or columns
- edit_notes: modify only speaker notes
- change_layout: convert layout (set new_layout to: bullet|table|two_column|image_placeholder)
- change_tone: restyle without changing facts
- split_slide: divide one slide into two
- merge_slides: combine two adjacent slides (target = "id_1+id_2")
- add_slide: insert a new slide (set insert_after to a slide_id)
- delete_slide: remove a slide
- reorder: move a slide (set new_position to the target position number)

Rules:
- ALWAYS include at least one change in the changes array. Never return an empty changes array.
- Default to edit_content. Use split_slide ONLY if result would exceed 6 bullets.
- For "expand" requests: use edit_content to add bullets, not add_slide.
- edit_instruction must be SPECIFIC: say exactly what to add, remove, or change.
- target must be the exact slide id from the manifest (e.g. "slide_2", not "2").
- If user references a slide by topic name, match it to the closest slide title.
- For global feedback ("make all shorter"), emit one change per content slide.
- Do not touch title or closing slides unless explicitly asked.
- History of previous round is only for context about previous changes , current changes has to be made based on what is in feedback_text,so treat it as prompt and history_section as helping context
"""

# ---------------------------------------------------------------------------
# Stage 9 — Slide Editor (edits existing slide content precisely)
# ---------------------------------------------------------------------------
SLIDE_EDITOR_SYSTEM = """\
You edit a single presentation slide. Apply the requested change precisely. \
Preserve everything not asked to change. Use [[key term]] markup on 1-3 \
important terms per bullet that students should remember. \
Respond ONLY with valid JSON."""

SLIDE_EDITOR_USER = """\
Current slide:
{current_slide_json}

Edit: {edit_instruction}

Output the complete updated slide as JSON:
{{
  "title": "...",
  "body": "...",
  "bullet_points": ["..."],
  "table_data": null,
  "speaker_notes": "...",
  "layout_hint": "..."
}}

Rules:
- Apply ONLY the requested edit. Preserve unchanged content exactly.
- Keep bullet_points concise (max 2 lines each), max 5-6 per slide.
- Use [[term]] markup (exactly two brackets each side) on key terms in body and bullet_points. Never use single, triple, or nested brackets.
- Speaker notes: add presenter context, no [[ ]] markup."""

# ---------------------------------------------------------------------------
# Stage 9B — Slide Splitter (splits one slide into two)
# ---------------------------------------------------------------------------
SLIDE_SPLITTER_SYSTEM = """\
You split one presentation slide into two focused slides. Divide content \
logically. Use [[key term]] markup. Respond ONLY with valid JSON."""

SLIDE_SPLITTER_USER = """\
Slide to split:
{current_slide_json}

Split instruction: {edit_instruction}

Output JSON with two slides:
{{
  "slide_a": {{"title":"...","body":"...","bullet_points":[...],"table_data":null,"speaker_notes":"...","layout_hint":"..."}},
  "slide_b": {{"title":"...","body":"...","bullet_points":[...],"table_data":null,"speaker_notes":"...","layout_hint":"..."}}
}}

Rules:
- Each slide should have 3-4 bullets, not 1-2.
- Don't duplicate content between the two slides.
- Give each a meaningful title (not "Part 1"/"Part 2").
- Preserve [[markup]] from the original."""

# ---------------------------------------------------------------------------
# Stage 9C — Slide Merger (combines two slides into one)
# ---------------------------------------------------------------------------
SLIDE_MERGER_SYSTEM = """\
You merge two presentation slides into one. Combine essential content \
and eliminate redundancy. Use [[key term]] markup. Respond ONLY with valid JSON."""

SLIDE_MERGER_USER = """\
Slide A:
{slide_a_json}

Slide B:
{slide_b_json}

Merge instruction: {edit_instruction}

Output ONE combined slide as JSON:
{{
  "title": "...",
  "body": "...",
  "bullet_points": ["..."],
  "table_data": null,
  "speaker_notes": "...",
  "layout_hint": "..."
}}

Rules:
- Pick the better title or write a new one covering both.
- Max 5 bullets — cut redundancy, keep key facts.
- Preserve [[markup]] from originals."""

# ---------------------------------------------------------------------------
# Stage 9D — New Slide Generator (creates slide from spec + chunks)
# ---------------------------------------------------------------------------
SLIDE_NEW_SYSTEM = """\
You create a new slide for a presentation. Use source content as the basis. \
Use [[key term]] markup on important terms. Respond ONLY with valid JSON."""

SLIDE_NEW_USER = """\
New slide spec:
- Topic: {edit_instruction}
- Layout: {layout}

Source content:
{relevant_chunks}

Context:
- Previous slide: {prev_summary}
- Next slide: {next_summary}

Output the slide as JSON:
{{
  "title": "...",
  "body": "...",
  "bullet_points": ["..."],
  "table_data": null,
  "speaker_notes": "...",
  "layout_hint": "{layout}"
}}

Rules:
- 3-5 concise bullet points with [[key term]] markup.
- Speaker notes with presenter context.
- Fit naturally between the surrounding slides."""
