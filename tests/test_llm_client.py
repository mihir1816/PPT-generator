"""Unit tests for LLMClient — strip_think_blocks, streaming filter, and prompt templates."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.llm_client import LLMClient
from app.services import prompt_templates as pt


class TestStripThinkBlocks:
    def test_no_think_block(self):
        assert LLMClient.strip_think_blocks("Hello world") == "Hello world"

    def test_think_block_at_start(self):
        text = "<think>some reasoning</think>Actual response"
        assert LLMClient.strip_think_blocks(text) == "Actual response"

    def test_think_block_with_newlines(self):
        text = "<think>\nStep 1: think\nStep 2: more\n</think>\n\nFinal answer"
        assert LLMClient.strip_think_blocks(text) == "Final answer"

    def test_multiple_think_blocks(self):
        text = "<think>block1</think>Hello <think>block2</think>World"
        assert LLMClient.strip_think_blocks(text) == "Hello World"

    def test_empty_think_block(self):
        text = "<think></think>Response"
        assert LLMClient.strip_think_blocks(text) == "Response"

    def test_only_think_block(self):
        text = "<think>all reasoning, no answer</think>"
        assert LLMClient.strip_think_blocks(text) == ""

    def test_think_block_with_json(self):
        text = '<think>planning JSON</think>\n{"key": "value"}'
        result = LLMClient.strip_think_blocks(text)
        assert result == '{"key": "value"}'

    def test_nested_angle_brackets_in_think(self):
        text = "<think>if x < 5 and y > 3 then ok</think>Answer"
        assert LLMClient.strip_think_blocks(text) == "Answer"

    def test_whitespace_after_think_block(self):
        text = "<think>reason</think>   \n  Content"
        assert LLMClient.strip_think_blocks(text) == "Content"


class TestStreamingThinkFilter:
    """Test the streaming think-block filter via generate_stream."""

    @staticmethod
    def _make_client():
        with patch("app.services.llm_client.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(LLM_TIMEOUT=10, LLM_JSON_RETRIES=1)
            return LLMClient(base_url="http://fake:8000/v1", model="test")

    @staticmethod
    def _make_chunk(content):
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = content
        return chunk

    def test_stream_strips_think_block(self):
        client = self._make_client()

        async def fake_stream():
            for text in ["<think>", "reasoning here", "</think>", "\n", "Hello world"]:
                yield self._make_chunk(text)

        async def run():
            with patch.object(client.client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
                mock_create.return_value = fake_stream()
                result = []
                async for token in client.generate_stream("sys", "user"):
                    result.append(token)
                return "".join(result)

        text = asyncio.run(run())
        assert "<think>" not in text
        assert "reasoning" not in text
        assert "Hello world" in text

    def test_stream_no_think_block(self):
        client = self._make_client()

        async def fake_stream():
            for text in ["Hello ", "world"]:
                yield self._make_chunk(text)

        async def run():
            with patch.object(client.client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
                mock_create.return_value = fake_stream()
                result = []
                async for token in client.generate_stream("sys", "user"):
                    result.append(token)
                return "".join(result)

        text = asyncio.run(run())
        assert text == "Hello world"

    def test_stream_think_block_only(self):
        client = self._make_client()

        async def fake_stream():
            for text in ["<think>all reasoning</think>"]:
                yield self._make_chunk(text)

        async def run():
            with patch.object(client.client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
                mock_create.return_value = fake_stream()
                result = []
                async for token in client.generate_stream("sys", "user"):
                    result.append(token)
                return "".join(result)

        text = asyncio.run(run())
        assert text == ""


class TestPromptTemplates:
    def test_syllabus_generation_renders(self):
        rendered = pt.SYLLABUS_GENERATION_USER.format(
            description="Machine Learning basics",
            outline="Not provided — create your own",
            level="beginner",
            tone="formal",
            content_mode="grounded",
            slide_count_hint="10",
        )
        assert "Machine Learning basics" in rendered
        assert "beginner" in rendered

    def test_syllabus_feedback_renders(self):
        rendered = pt.SYLLABUS_FEEDBACK_USER.format(
            syllabus_json='{"title": "ML"}',
            feedback_text="Add more examples",
        )
        assert "ML" in rendered
        assert "Add more examples" in rendered

    def test_query_generation_renders(self):
        rendered = pt.QUERY_GENERATION_USER.format(
            syllabus_json='{"topics": []}',
        )
        assert "topics" in rendered

    def test_slide_outline_renders(self):
        rendered = pt.SLIDE_OUTLINE_USER.format(
            syllabus_json='{"topics": []}',
            chunks_summary="chunk data here",
            level="advanced",
            tone="creative",
            content_mode="mixed",
            slide_count_hint="15",
        )
        assert "advanced" in rendered
        assert "chunk data here" in rendered

    def test_slide_content_renders(self):
        rendered = pt.SLIDE_CONTENT_USER.format(
            outline_entry='{"id": "slide_1"}',
            relevant_chunks="source text here",
            prev_slide_summary="Previous slide about intro",
            level="intermediate",
            tone="formal",
            content_mode="grounded",
            slide_id="slide_1",
        )
        assert "slide_1" in rendered
        assert "source text here" in rendered

    def test_feedback_parser_renders(self):
        rendered = pt.FEEDBACK_PARSER_USER.format(
            outline_json='[{"id": "slide_1"}]',
            feedback_text="Make slide 1 more detailed",
        )
        assert "Make slide 1 more detailed" in rendered

    def test_outline_updater_renders(self):
        rendered = pt.OUTLINE_UPDATER_USER.format(
            outline_json='[{"id": "slide_1"}]',
            actions_json='[{"type": "expand"}]',
            chunk_ids_summary="chunk_1, chunk_2",
        )
        assert "expand" in rendered
        assert "chunk_1" in rendered

    def test_all_system_prompts_are_nonempty(self):
        system_prompts = [
            pt.SYLLABUS_GENERATION_SYSTEM,
            pt.SYLLABUS_FEEDBACK_SYSTEM,
            pt.QUERY_GENERATION_SYSTEM,
            pt.SLIDE_OUTLINE_SYSTEM,
            pt.SLIDE_CONTENT_SYSTEM,
            pt.FEEDBACK_PARSER_SYSTEM,
            pt.OUTLINE_UPDATER_SYSTEM,
        ]
        for prompt in system_prompts:
            assert len(prompt) > 20
            assert "JSON" in prompt
