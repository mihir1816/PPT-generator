# Session 05 — LLM Service & Inference

## Goal
Set up vLLM Docker config, build an OpenAI-compatible LLM client abstraction, create all prompt templates, and wire structured JSON output parsing. After this session, the app can call the LLM and get structured responses.

## Read First
- `docs/sessions/SESSION_TRACKER.md` — confirm Sessions 01-04 complete
- `src/app/config.py` — LLM_BASE_URL, LLM_MODEL settings
- `docs/LLM_SELECTION_AND_SEARCH_RESEARCH.md` — model details

## Non-Negotiable Rules
- Model: Qwen3-30B-A3B Q4 (AWQ) — no other model
- Use `openai` Python SDK pointed at vLLM (OpenAI-compatible API)
- All prompts in a single `prompt_templates.py` — no scattered strings
- Every LLM call must have a timeout (120s default)
- Every LLM call returns structured output (JSON) — parse with Pydantic
- Streaming support via async generator
- If vLLM is unavailable, raise clear `LLMServiceError` — never hang

## Files to Create

### `services/llm_client.py` — LLM Client
```python
from openai import AsyncOpenAI

class LLMClient:
    def __init__(self, base_url: str, model: str):
        self.client = AsyncOpenAI(base_url=base_url, api_key="not-needed")
        self.model = model

    async def generate(self, system_prompt: str, user_prompt: str,
                       temperature: float = 0.7, max_tokens: int = 4096,
                       response_format: dict | None = None) -> str:
        """Single completion. Returns content string.
        Automatically strips Qwen3 <think>...</think> blocks from response."""

    async def generate_json(self, system_prompt: str, user_prompt: str,
                            response_model: type[BaseModel], **kwargs) -> BaseModel:
        """Generate + parse into Pydantic model. Retries once on parse failure.
        Strips <think> blocks before JSON parsing."""

    async def generate_stream(self, system_prompt: str, user_prompt: str,
                              temperature: float = 0.7, max_tokens: int = 4096):
        """Async generator yielding token strings.
        Buffers and strips <think>...</think> blocks before yielding content."""
        # Uses client.chat.completions.create(stream=True)
        # Yields each chunk.choices[0].delta.content (after think block ends)

    async def health_check(self) -> bool:
        """Check if vLLM is reachable."""

    @staticmethod
    def strip_think_blocks(text: str) -> str:
        """
        Qwen3 models output <think>...</think> reasoning blocks before actual content.
        This strips them to get clean response text for JSON parsing.
        Uses regex: re.sub(r'<think>.*?</think>\s*', '', text, flags=re.DOTALL)
        MUST be called before any JSON parsing or the parse will fail.
        """
```

Key: `response_format={"type": "json_object"}` tells vLLM to enforce JSON output.

### `services/prompt_templates.py` — All Prompts

**SYLLABUS_GENERATION** (Stage 2B)
```
System: You are an expert curriculum designer. Given a topic description and preferences, generate a detailed topic syllabus for a presentation.
User: Description: {description}
      Outline: {outline or "Not provided — create your own"}
      Audience: {level}
      Tone: {tone}
      Content mode: {content_mode}
      Target slides: {slide_count_hint or "Use your best judgment"}
Output JSON: {TopicSyllabus schema}
Rules:
  - If outline is provided, strictly follow it. Do not deviate.
  - Calibrate topic depth to fit approximately {slide_count_hint} slides if specified.
```

**SYLLABUS_FEEDBACK** (Stage 3)
```
System: You are updating a topic syllabus based on user feedback.
User: Current syllabus: {syllabus_json}
      User feedback: {feedback_text}
Output JSON: {Updated TopicSyllabus}
Rule: Apply ONLY the requested changes. Keep everything else unchanged.
```

**QUERY_GENERATION** (Stage 5)
```
System: Generate search queries to retrieve content for each topic in this syllabus.
User: Syllabus: {syllabus_json}
Output JSON: {list of {topic, queries: list[str]}}
Generate 2-3 queries per topic/subtopic. Cover prerequisites.
```

**SLIDE_OUTLINE_GENERATION** (Stage 6)
```
System: You are a presentation designer. Map this syllabus to specific slides.
User: Syllabus: {syllabus_json}
      Retrieved content summary: {chunks_summary}
      Preferences: {preferences}
      Target slide count: {slide_count_hint or "Use your best judgment"}
Output JSON: {list of SlideOutline}
Rules: Handle tables spanning multiple slides. Include layout hints.
       Aim for approximately {slide_count_hint} slides if specified.
```

**SLIDE_CONTENT_GENERATION** (Stage 7)
```
System: Generate content for one presentation slide.
User: Slide outline: {outline_entry}
      Source content: {relevant_chunks}
      Previous slide: {prev_slide_summary}
      Preferences: {preferences}
Output JSON: {SlideContent}
Rules:
  - Grounded mode: ONLY use provided source content. Do not add external info.
  - Mixed mode: Use source content as primary. Add brief filler/transitions where needed but do not generate entire sections from scratch.
```

**FEEDBACK_PARSER** (Stage 8)
```
System: Parse user feedback on slides into structured actions.
User: Current outline: {outline_json}
      User feedback: {feedback_text}
Output JSON: {list of FeedbackAction: {type, target_slide, instruction}}
Types: modify_content, delete, insert_after, reorder, change_tone, expand, add_table, add_image
```

**OUTLINE_UPDATER** (Stage 8)
```
System: Update the slide outline based on parsed feedback actions.
User: Current outline: {outline_json}
      Actions: {actions_json}
      Available chunks: {chunk_ids_summary}
Output JSON: {Updated list of SlideOutline with status fields set}
Rules: Mark affected slides as "needs_regeneration". Mark new slides as "pending". Leave unaffected as "generated".
```

### Update `main.py` startup
```python
# Initialize LLM client
llm_client = LLMClient(settings.LLM_BASE_URL, settings.LLM_MODEL)
# Health check (non-blocking — vLLM may not be up yet)
```

### Update `config.py`
`LLM_TIMEOUT` and `LLM_JSON_RETRIES` are already defined in Session 01's config. Verify they exist.

### Update `deps.py`
Add LLM client DI factory:
```python
def get_llm_client(request: Request) -> LLMClient:
    return request.app.state.llm_client
```

## Flow
```
1. Create services/llm_client.py
2. Create services/prompt_templates.py (all 7 prompt templates)
3. Update main.py to init LLM client
4. Update config.py with timeout/retry settings
5. Test LLM connectivity + generation
```

## Verification
```bash
# 1. Start vLLM (requires GPU)
docker compose --profile gpu up -d vllm
# Wait 2-5 min for model download + load

# 2. Check vLLM health
curl http://localhost:8100/health
# Expected: {"status":"ok"} or similar

# 3. Check model loaded
curl http://localhost:8100/v1/models
# Expected: lists Qwen/Qwen3-30B-A3B-AWQ

# 4. Test raw completion
curl http://localhost:8100/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"Qwen/Qwen3-30B-A3B-AWQ","messages":[{"role":"user","content":"Say hello in JSON: {\"greeting\":\"...\"}"}],"max_tokens":50}'
# Expected: JSON response with greeting

# 5. Test LLM client from app
docker compose exec app python -c "
import asyncio
from app.services.llm_client import LLMClient
from app.config import get_settings
async def test():
    s = get_settings()
    client = LLMClient(s.LLM_BASE_URL, s.LLM_MODEL)
    ok = await client.health_check()
    print(f'Health: {ok}')
    result = await client.generate('You are helpful.', 'Say hello briefly.')
    print(f'Response: {result[:100]}')
    print('LLM Client OK')
asyncio.run(test())
"

# 6. Test structured JSON output
docker compose exec app python -c "
import asyncio
from app.services.llm_client import LLMClient
from app.schemas.syllabus import TopicSyllabus
from app.config import get_settings
async def test():
    s = get_settings()
    client = LLMClient(s.LLM_BASE_URL, s.LLM_MODEL)
    result = await client.generate_json(
        'Generate a topic syllabus as JSON.',
        'Topic: Introduction to Machine Learning. Level: beginner. 5 topics.',
        response_model=TopicSyllabus
    )
    print(f'Syllabus topics: {len(result.topics)}')
    print(f'First topic: {result.topics[0].title}')
    print('JSON parsing OK')
asyncio.run(test())
"

# 7. Test streaming
docker compose exec app python -c "
import asyncio
from app.services.llm_client import LLMClient
from app.config import get_settings
async def test():
    s = get_settings()
    client = LLMClient(s.LLM_BASE_URL, s.LLM_MODEL)
    tokens = []
    async for token in client.generate_stream('You are helpful.', 'Count from 1 to 5.'):
        tokens.append(token)
    print(f'Streamed {len(tokens)} chunks')
    print('Streaming OK')
asyncio.run(test())
"

# If no GPU available, test with mock:
# Set LLM_BASE_URL to a mock server or skip LLM tests,
# verify all other code compiles and imports cleanly.
```

## On Completion
Update `SESSION_TRACKER.md`: mark Session 05 ✅, confirm vLLM model loaded, next → Session 06
