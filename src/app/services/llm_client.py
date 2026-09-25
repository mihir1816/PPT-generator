import logging
import re

from openai import AsyncOpenAI, APIConnectionError, APITimeoutError
from pydantic import BaseModel, ValidationError

from app.config import get_settings

logger = logging.getLogger(__name__)

_THINK_RE = re.compile(r"<think>.*?</think>\s*", flags=re.DOTALL)
_THINK_TAG = "<think>"


class LLMServiceError(Exception):
    pass


class LLMClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        timeout: int | None = None,
        json_retries: int | None = None,
    ):
        settings = get_settings()
        self._timeout = timeout or settings.LLM_TIMEOUT
        self._json_retries = json_retries if json_retries is not None else settings.LLM_JSON_RETRIES
        self.model = model
        self.client = AsyncOpenAI(
            base_url=base_url,
            api_key="not-needed",
            timeout=float(self._timeout),
        )

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: dict | None = None,
    ) -> str:
        try:
            kwargs: dict = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if response_format is not None:
                kwargs["response_format"] = response_format

            response = await self.client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content or ""
            return self.strip_think_blocks(content)
        except APIConnectionError as exc:
            raise LLMServiceError(f"Cannot connect to LLM at {self.client.base_url}: {exc}") from exc
        except APITimeoutError as exc:
            raise LLMServiceError(f"LLM request timed out after {self._timeout}s") from exc
        except Exception as exc:
            raise LLMServiceError(f"LLM generation failed: {exc}") from exc

    async def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[BaseModel],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> BaseModel:
        last_error: Exception | None = None
        for attempt in range(1 + self._json_retries):
            raw = await self.generate(
                system_prompt,
                user_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
            try:
                return response_model.model_validate_json(raw)
            except ValidationError as exc:
                last_error = exc
                logger.warning(
                    "JSON parse attempt %d/%d failed for %s: %s",
                    attempt + 1,
                    1 + self._json_retries,
                    response_model.__name__,
                    exc,
                )
        raise LLMServiceError(
            f"Failed to parse LLM response as {response_model.__name__} "
            f"after {1 + self._json_retries} attempts: {last_error}"
        )

    async def health_check(self) -> bool:
        try:
            await self.client.models.list()
            return True
        except Exception:
            return False

    @staticmethod
    def strip_think_blocks(text: str) -> str:
        return _THINK_RE.sub("", text).strip()
