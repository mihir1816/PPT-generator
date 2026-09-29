import logging
import re
from collections.abc import AsyncGenerator

from openai import AsyncOpenAI, APIConnectionError, APITimeoutError, RateLimitError
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
        self._max_tokens = settings.LLM_MAX_TOKENS
        self._model_context = settings.LLM_MODEL_CONTEXT
        self.model = model
        self._fallback_model = settings.LLM_FALLBACK_MODEL or ""
        self.client = AsyncOpenAI(
            base_url=base_url,
            api_key=settings.LLM_API_KEY,
            timeout=float(self._timeout),
        )

    def _model_chain(self) -> list[str]:
        models = [self.model]
        if self._fallback_model:
            models.append(self._fallback_model)
        return models

    def _clamp_max_tokens(self, prompt_text: str, requested: int) -> int:
        est_input = int(len(prompt_text) / 2.5) + 100
        headroom = self._model_context - est_input
        if headroom < 512:
            logger.warning(
                "Tight context: ~%d input tokens estimated, only %d headroom "
                "(model context=%d). Prompt may need trimming.",
                est_input, headroom, self._model_context,
            )
        safe = max(256, min(requested, headroom))
        return safe

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        response_format: dict | None = None,
    ) -> str:
        if max_tokens is None:
            max_tokens = self._max_tokens
        max_tokens = self._clamp_max_tokens(
            system_prompt + user_prompt, max_tokens,
        )
        for model in self._model_chain():
            try:
                kwargs: dict = {
                    "model": model,
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
            except RateLimitError as exc:
                if model != self.model:
                    raise LLMServiceError(f"Rate limited on fallback model too: {exc}") from exc
                if not self._fallback_model:
                    raise LLMServiceError(f"Rate limited and no fallback model configured: {exc}") from exc
                logger.warning("Rate limited on %s, falling back to %s", model, self._fallback_model)
                continue
            except APIConnectionError as exc:
                raise LLMServiceError(f"Cannot connect to LLM at {self.client.base_url}: {exc}") from exc
            except APITimeoutError as exc:
                raise LLMServiceError(f"LLM request timed out after {self._timeout}s") from exc
            except Exception as exc:
                raise LLMServiceError(f"LLM generation failed: {exc}") from exc
        raise LLMServiceError("All models exhausted")

    async def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[BaseModel],
        temperature: float = 0.7,
        max_tokens: int | None = None,
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

    async def generate_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[str, None]:
        """Yield decoded tokens from the LLM, stripping <think>...</think> blocks."""
        if max_tokens is None:
            max_tokens = self._max_tokens
        max_tokens = self._clamp_max_tokens(
            system_prompt + user_prompt, max_tokens,
        )
        try:
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
        except APIConnectionError as exc:
            raise LLMServiceError(
                f"Cannot connect to LLM at {self.client.base_url}: {exc}"
            ) from exc
        except APITimeoutError as exc:
            raise LLMServiceError(
                f"LLM request timed out after {self._timeout}s"
            ) from exc
        except Exception as exc:
            raise LLMServiceError(f"LLM stream failed: {exc}") from exc

        buffer = ""
        in_think = False

        async for chunk in stream:
            token = chunk.choices[0].delta.content
            if token is None:
                continue

            buffer += token

            # Process buffer, yielding only non-think content
            while buffer:
                if in_think:
                    end = buffer.find("</think>")
                    if end == -1:
                        # Still inside think block, consume entire buffer
                        buffer = ""
                        break
                    else:
                        # Found end of think block; skip up to and including </think>
                        buffer = buffer[end + len("</think>"):]
                        in_think = False
                else:
                    start = buffer.find("<think>")
                    if start == -1:
                        # No think block starting — yield everything
                        yield buffer
                        buffer = ""
                        break
                    else:
                        # Yield content before the think block
                        if start > 0:
                            yield buffer[:start]
                        buffer = buffer[start + len("<think>"):]
                        in_think = True

        # Yield any remaining non-think content
        if buffer and not in_think:
            yield buffer

    async def health_check(self) -> bool:
        try:
            await self.client.models.list()
            return True
        except Exception:
            return False

    @staticmethod
    def strip_think_blocks(text: str) -> str:
        return _THINK_RE.sub("", text).strip()
