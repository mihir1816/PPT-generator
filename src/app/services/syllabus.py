import logging

from app.schemas.deck import TeacherPreferences
from app.schemas.syllabus import TopicSyllabus
from app.services.llm_client import LLMClient, LLMServiceError
from app.services.prompt_templates import (
    SYLLABUS_FEEDBACK_SYSTEM,
    SYLLABUS_FEEDBACK_USER,
    SYLLABUS_GENERATION_SYSTEM,
    SYLLABUS_GENERATION_USER,
)

logger = logging.getLogger(__name__)


class SyllabusService:
    def __init__(self, llm_client: LLMClient):
        self._llm = llm_client

    async def generate_syllabus(
        self,
        description: str,
        outline: str | None,
        preferences: TeacherPreferences,
    ) -> TopicSyllabus:
        user_prompt = SYLLABUS_GENERATION_USER.format(
            description=description,
            outline=outline or "Not provided — create your own",
            level=preferences.audience_level,
            tone=preferences.tone,
            content_mode=preferences.content_mode,
            slide_count_hint=(
                str(preferences.slide_count_hint)
                if preferences.slide_count_hint
                else "Use your best judgment"
            ),
        )

        syllabus = await self._llm.generate_json(
            SYLLABUS_GENERATION_SYSTEM,
            user_prompt,
            response_model=TopicSyllabus,
        )

        self._validate(syllabus)
        return syllabus

    async def apply_feedback(
        self,
        current_syllabus: TopicSyllabus,
        feedback_text: str,
    ) -> TopicSyllabus:
        user_prompt = SYLLABUS_FEEDBACK_USER.format(
            syllabus_json=current_syllabus.model_dump_json(indent=2),
            feedback_text=feedback_text,
        )

        updated = await self._llm.generate_json(
            SYLLABUS_FEEDBACK_SYSTEM,
            user_prompt,
            response_model=TopicSyllabus,
        )

        self._validate(updated)
        return updated

    @staticmethod
    def _validate(syllabus: TopicSyllabus) -> None:
        if not syllabus.topics:
            raise LLMServiceError(
                "LLM produced an empty syllabus with no topics"
            )
        if not syllabus.title or not syllabus.title.strip():
            raise LLMServiceError("LLM produced a syllabus with no title")
