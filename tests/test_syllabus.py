"""Unit tests for SyllabusService and syllabus API request/response models."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.deck import TeacherPreferences
from app.schemas.syllabus import TopicSyllabus
from app.services.llm_client import LLMServiceError
from app.services.syllabus import SyllabusService


def _make_llm_mock():
    llm = MagicMock()
    llm.generate_json = AsyncMock()
    return llm


class TestSyllabusServiceGenerate:
    def test_generate_with_outline(self):
        llm = _make_llm_mock()
        svc = SyllabusService(llm)

        expected = TopicSyllabus(
            title="ML Basics",
            topics=[
                {"title": "Intro", "subtopics": ["What is ML"]},
                {"title": "Types", "subtopics": ["Supervised", "Unsupervised"]},
            ],
            audience_level="beginner",
            estimated_slides=5,
        )
        llm.generate_json.return_value = expected

        prefs = TeacherPreferences(
            audience_level="beginner", tone="formal", content_mode="grounded",
        )

        result = asyncio.run(svc.generate_syllabus("ML basics", "1. Intro\n2. Types", prefs))

        assert result.title == "ML Basics"
        assert len(result.topics) == 2
        call_args = llm.generate_json.call_args
        assert "ML basics" in call_args.args[1]
        assert "1. Intro" in call_args.args[1]

    def test_generate_without_outline(self):
        llm = _make_llm_mock()
        svc = SyllabusService(llm)

        expected = TopicSyllabus(
            title="Machine Learning",
            topics=[{"title": "Overview", "subtopics": ["Basics"]}],
        )
        llm.generate_json.return_value = expected

        prefs = TeacherPreferences()

        result = asyncio.run(svc.generate_syllabus("Machine learning", None, prefs))

        call_args = llm.generate_json.call_args
        assert "Not provided" in call_args.args[1]

    def test_generate_with_slide_count_hint(self):
        llm = _make_llm_mock()
        svc = SyllabusService(llm)

        expected = TopicSyllabus(
            title="Test",
            topics=[{"title": "T1", "subtopics": ["S1"]}],
            estimated_slides=10,
        )
        llm.generate_json.return_value = expected

        prefs = TeacherPreferences(slide_count_hint=10)

        result = asyncio.run(svc.generate_syllabus("Test", None, prefs))
        call_args = llm.generate_json.call_args
        assert "10" in call_args.args[1]

    def test_generate_empty_topics_raises(self):
        llm = _make_llm_mock()
        svc = SyllabusService(llm)

        bad_syllabus = TopicSyllabus(title="Empty", topics=[])
        llm.generate_json.return_value = bad_syllabus

        prefs = TeacherPreferences()

        with pytest.raises(LLMServiceError, match="empty syllabus"):
            asyncio.run(svc.generate_syllabus("Something", None, prefs))

    def test_generate_empty_title_raises(self):
        llm = _make_llm_mock()
        svc = SyllabusService(llm)

        bad_syllabus = TopicSyllabus(
            title="  ",
            topics=[{"title": "T1", "subtopics": ["S1"]}],
        )
        llm.generate_json.return_value = bad_syllabus

        prefs = TeacherPreferences()

        with pytest.raises(LLMServiceError, match="no title"):
            asyncio.run(svc.generate_syllabus("Something", None, prefs))

    def test_generate_llm_failure_propagates(self):
        llm = _make_llm_mock()
        svc = SyllabusService(llm)
        llm.generate_json.side_effect = LLMServiceError("Connection refused")

        prefs = TeacherPreferences()

        with pytest.raises(LLMServiceError, match="Connection refused"):
            asyncio.run(svc.generate_syllabus("Test", None, prefs))


class TestSyllabusServiceFeedback:
    def test_apply_feedback(self):
        llm = _make_llm_mock()
        svc = SyllabusService(llm)

        current = TopicSyllabus(
            title="ML Basics",
            topics=[
                {"title": "Intro", "subtopics": ["What is ML"]},
                {"title": "Trees", "subtopics": ["Decision Trees"]},
            ],
        )
        updated = TopicSyllabus(
            title="ML Basics",
            topics=[
                {"title": "Intro", "subtopics": ["What is ML"]},
                {"title": "Regression", "subtopics": ["Linear", "Logistic"]},
            ],
        )
        llm.generate_json.return_value = updated

        result = asyncio.run(svc.apply_feedback(current, "Replace Trees with Regression"))

        assert len(result.topics) == 2
        assert result.topics[1].title == "Regression"
        call_args = llm.generate_json.call_args
        assert "Replace Trees with Regression" in call_args.args[1]
        assert "ML Basics" in call_args.args[1]

    def test_apply_feedback_validates_result(self):
        llm = _make_llm_mock()
        svc = SyllabusService(llm)

        current = TopicSyllabus(
            title="Test",
            topics=[{"title": "T1", "subtopics": ["S1"]}],
        )
        bad_result = TopicSyllabus(title="Test", topics=[])
        llm.generate_json.return_value = bad_result

        with pytest.raises(LLMServiceError, match="empty syllabus"):
            asyncio.run(svc.apply_feedback(current, "Remove everything"))


class TestSchemas:
    def test_teacher_preferences_defaults(self):
        prefs = TeacherPreferences()
        assert prefs.audience_level == "intermediate"
        assert prefs.tone == "formal"
        assert prefs.content_mode == "grounded"
        assert prefs.slide_count_hint is None

    def test_topic_syllabus_roundtrip(self):
        syllabus = TopicSyllabus(
            title="Test",
            topics=[{"title": "T1", "subtopics": ["S1", "S2"]}],
            audience_level="beginner",
            estimated_slides=5,
        )
        dumped = syllabus.model_dump_json()
        restored = TopicSyllabus.model_validate_json(dumped)
        assert restored.title == "Test"
        assert len(restored.topics) == 1
        assert restored.topics[0].subtopics == ["S1", "S2"]

    def test_syllabus_with_all_fields(self):
        syllabus = TopicSyllabus(
            title="Full",
            topics=[{
                "title": "Advanced Topic",
                "subtopics": ["Sub1"],
                "depth_hint": "detailed",
                "notes": "Important topic",
            }],
            audience_level="advanced",
            estimated_slides=20,
        )
        assert syllabus.topics[0].depth_hint == "detailed"
        assert syllabus.topics[0].notes == "Important topic"


class TestTransitionSQL:
    def test_transition_sql_is_defined(self):
        from app.services.crud import _TRANSITION_SQL
        sql_text = str(_TRANSITION_SQL)
        assert "UPDATE decks" in sql_text
        assert "syllabus_status = 'approved'" in sql_text
        assert "is_indexed = FALSE" in sql_text
        assert "RETURNING id" in sql_text
