import re
import json
import time
import asyncio
from typing import Type, TypeVar, Optional, Tuple, Any, Dict, List

import httpx
from pydantic import BaseModel, ValidationError

from app.llm.base import LLMProvider
from app.llm.errors import (
    LLMError,
    LLMConnectionError,
    LLMModelMissingError,
    LLMTimeoutError,
    LLMInvalidJSONError,
    LLMSchemaValidationError,
    LLMProviderError,
)

T = TypeVar("T", bound=BaseModel)


class OllamaProvider(LLMProvider):
    """
    Ollama provider for Relay.

    Supports:
    - Local Ollama
    - Ollama Cloud
    - API-key authentication
    - Streaming responses
    - Structured JSON generation
    - Pydantic validation
    - Bounded corrective retries
    - Health checks
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen3:4b",
        num_ctx: int = 4096,
        timeout: float = 300.0,
        max_retries: int = 3,
        api_key: Optional[str] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.num_ctx = num_ctx
        self.timeout = timeout
        self.max_retries = max_retries
        self.api_key = api_key

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def _get_headers(self) -> Dict[str, str]:
        """
        Build HTTP headers.

        Local Ollama does not require an API key.

        Ollama Cloud requires:
            Authorization: Bearer <OLLAMA_API_KEY>
        """
        headers: Dict[str, str] = {}

        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        return headers

    # ------------------------------------------------------------------
    # Text cleanup
    # ------------------------------------------------------------------

    def _strip_thinking(self, text: str) -> str:
        """Strips <think>...</think> tags if they appear in text."""

        if not text:
            return ""

        cleaned = re.sub(
            r"<think>[\s\S]*?</think>",
            "",
            text,
            flags=re.DOTALL,
        )

        if "</think>" in cleaned:
            cleaned = cleaned.split("</think>")[-1]

        return cleaned.strip()

    def _clean_json_text(self, text: str) -> str:
        """
        Strips markdown code blocks and extracts raw JSON.
        """

        cleaned = self._strip_thinking(text).strip()

        json_match = re.search(
            r"```(?:json)?\s*(\{[\s\S]*\}|\[[\s\S]*\])\s*```",
            cleaned,
            re.DOTALL,
        )

        if json_match:
            return json_match.group(1).strip()

        start = cleaned.find("{")
        end = cleaned.rfind("}")

        if start != -1 and end != -1 and end > start:
            return cleaned[start : end + 1].strip()

        return cleaned

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    async def health_check(self) -> Dict[str, Any]:
        """
        Checks whether Ollama is reachable and whether the configured
        model is available.

        Works with both local Ollama and authenticated Ollama Cloud.
        """

        tags_url = f"{self.base_url}/api/tags"
        headers = self._get_headers()

        try:
            async with httpx.AsyncClient(
                timeout=5.0,
                headers=headers,
            ) as client:

                response = await client.get(tags_url)

                if response.status_code == 401:
                    return {
                        "provider": "ollama",
                        "model": self.model,
                        "reachable": True,
                        "available": False,
                        "status": "authentication_error",
                        "error": "Ollama authentication failed. Check OLLAMA_API_KEY.",
                        "details": {
                            "status_code": response.status_code,
                        },
                    }

                if response.status_code != 200:
                    return {
                        "provider": "ollama",
                        "model": self.model,
                        "reachable": True,
                        "available": False,
                        "status": "error",
                        "error": (
                            f"Ollama returned HTTP "
                            f"{response.status_code}"
                        ),
                        "details": {
                            "status_code": response.status_code,
                        },
                    }

                data = response.json()

                models: List[str] = [
                    m.get("name", "")
                    for m in data.get("models", [])
                ]

                model_found = False
                matched_name = None

                for installed_model in models:

                    if (
                        installed_model == self.model
                        or installed_model == f"{self.model}:latest"
                        or installed_model.startswith(f"{self.model}:")
                    ):
                        model_found = True
                        matched_name = installed_model
                        break

                    if (
                        ":" in self.model
                        and installed_model == self.model.split(":")[0]
                    ):
                        model_found = True
                        matched_name = installed_model
                        break

                if not model_found:
                    return {
                        "provider": "ollama",
                        "model": self.model,
                        "reachable": True,
                        "available": False,
                        "status": "model_missing",
                        "error": (
                            f"Model '{self.model}' is not available."
                        ),
                        "details": {
                            "installed_models": models,
                        },
                    }

                return {
                    "provider": "ollama",
                    "model": matched_name or self.model,
                    "reachable": True,
                    "available": True,
                    "status": "ready",
                    "error": None,
                    "details": {
                        "installed_models": models,
                    },
                }

        except httpx.ConnectError:
            return {
                "provider": "ollama",
                "model": self.model,
                "reachable": False,
                "available": False,
                "status": "unavailable",
                "error": (
                    f"Ollama is not reachable at "
                    f"{self.base_url}."
                ),
                "details": {},
            }

        except httpx.TimeoutException:
            return {
                "provider": "ollama",
                "model": self.model,
                "reachable": False,
                "available": False,
                "status": "unavailable",
                "error": (
                    f"Timeout connecting to Ollama at "
                    f"{self.base_url}"
                ),
                "details": {},
            }

        except Exception as exc:
            return {
                "provider": "ollama",
                "model": self.model,
                "reachable": False,
                "available": False,
                "status": "error",
                "error": str(exc),
                "details": {},
            }

    # ------------------------------------------------------------------
    # Streaming chat
    # ------------------------------------------------------------------

    async def _stream_chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.1,
        format_type: str = "json",
    ) -> Tuple[str, str, int]:
        """
        Streams a response from Ollama.

        Returns:
            (
                content_string,
                thinking_string,
                token_count
            )
        """

        payload = {
            "model": self.model,
            "messages": messages,
            "format": format_type,
            "stream": True,
            "think": False,
            "options": {
                "temperature": temperature,
                "num_ctx": self.num_ctx,
            },
        }

        content_parts: List[str] = []
        thinking_parts: List[str] = []
        token_count = 0

        headers = self._get_headers()

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                headers=headers,
            ) as client:

                async with client.stream(
                    "POST",
                    f"{self.base_url}/api/chat",
                    json=payload,
                ) as response:

                    if response.status_code == 401:
                        body = await response.aread()

                        raise LLMProviderError(
                            "Ollama authentication failed. "
                            "Check OLLAMA_API_KEY. "
                            f"Response: {body.decode(errors='replace')}"
                        )

                    if response.status_code == 404:
                        raise LLMModelMissingError(self.model)

                    if response.status_code != 200:
                        body = await response.aread()

                        raise LLMProviderError(
                            f"Ollama returned HTTP "
                            f"{response.status_code}: "
                            f"{body.decode(errors='replace')}"
                        )

                    async for line in response.aiter_lines():

                        if not line:
                            continue

                        try:
                            chunk = json.loads(line)

                            message = chunk.get(
                                "message",
                                {},
                            )

                            thinking = message.get("thinking")
                            content = message.get("content")

                            if thinking:
                                thinking_parts.append(
                                    thinking
                                )

                            if content:
                                content_parts.append(
                                    content
                                )

                            token_count += 1

                            if token_count % 50 == 0:
                                print(
                                    "[Ollama stream] "
                                    f"Tokens generated: {token_count} "
                                    f"(thinking: "
                                    f"{len(''.join(thinking_parts))}, "
                                    f"content: "
                                    f"{len(''.join(content_parts))})",
                                    flush=True,
                                )

                        except json.JSONDecodeError:
                            continue

        except httpx.ConnectError:
            raise LLMConnectionError(
                f"Cannot reach Ollama at {self.base_url}"
            )

        except httpx.TimeoutException:
            raise LLMTimeoutError(
                f"Ollama generation timed out "
                f"after {self.timeout}s"
            )

        full_content = "".join(content_parts).strip()
        full_thinking = "".join(thinking_parts).strip()

        return (
            full_content,
            full_thinking,
            token_count,
        )

    # ------------------------------------------------------------------
    # Structured generation
    # ------------------------------------------------------------------

    async def generate_structured(
        self,
        schema: Type[T],
        prompt: str,
        system_prompt: Optional[str] = None,
        language: str = "en",
        max_retries: Optional[int] = None,
        temperature: float = 0.1,
        prompt_version: str = "1.0",
    ) -> Tuple[T, Dict[str, Any]]:
        """
        Generates structured JSON using Ollama and validates it
        using the supplied Pydantic schema.
        """

        retries = (
            max_retries
            if max_retries is not None
            else self.max_retries
        )

        lang_note = (
            f"\nYou must generate any natural language "
            f"descriptions or user-facing text in: "
            f"'{language}'."
            if language != "en"
            else ""
        )

        if system_prompt:

            sys_content = (
                system_prompt + lang_note
            )

        else:

            schema_json_str = json.dumps(
                schema.model_json_schema(),
                indent=2,
            )

            sys_content = (
                "You are Relay, an autonomous work agent. "
                "You must respond with strictly valid JSON "
                "matching this schema:\n"
                f"{schema_json_str}\n"
                f"{lang_note}"
            )

        messages = [
            {
                "role": "system",
                "content": sys_content,
            },
            {
                "role": "user",
                "content": prompt,
            },
        ]

        start_time = time.time()
        last_error = None

        for attempt in range(1, retries + 1):

            try:

                (
                    full_content,
                    full_thinking,
                    tokens,
                ) = await self._stream_chat(
                    messages=messages,
                    temperature=temperature,
                    format_type="json",
                )

                cleaned = self._clean_json_text(
                    full_content
                )

                if not cleaned:

                    raise LLMInvalidJSONError(
                        full_content,
                        "Ollama returned empty response content",
                    )

                try:

                    parsed_json = json.loads(cleaned)

                except json.JSONDecodeError as exc:

                    raise LLMInvalidJSONError(
                        cleaned,
                        f"Invalid JSON returned: {str(exc)}",
                    )

                try:

                    validated_instance = (
                        schema.model_validate(
                            parsed_json
                        )
                    )

                    duration_ms = int(
                        (time.time() - start_time) * 1000
                    )

                    meta = {
                        "provider": "ollama",
                        "model": self.model,
                        "prompt_version": prompt_version,
                        "attempts": attempt,
                        "tokens_generated": tokens,
                        "duration_ms": duration_ms,
                        "thinking_length": len(
                            full_thinking
                        ),
                        "raw_output": full_content,
                    }

                    return (
                        validated_instance,
                        meta,
                    )

                except ValidationError as exc:

                    raise LLMSchemaValidationError(
                        schema.__name__,
                        exc.errors(),
                        raw_json=parsed_json,
                    )

            except (
                LLMInvalidJSONError,
                LLMSchemaValidationError,
            ) as parse_val_err:

                last_error = parse_val_err

                if attempt < retries:

                    err_details = ""

                    if isinstance(
                        parse_val_err,
                        LLMSchemaValidationError,
                    ):

                        err_lines = []

                        for err in parse_val_err.details.get(
                            "validation_errors",
                            [],
                        ):

                            loc = " -> ".join(
                                str(location)
                                for location in err.get(
                                    "loc",
                                    [],
                                )
                            )

                            message = err.get(
                                "msg",
                                "",
                            )

                            err_lines.append(
                                f"- Field '{loc}': {message}"
                            )

                        err_details = (
                            "\nValidation errors:\n"
                            + "\n".join(err_lines)
                        )

                    elif isinstance(
                        parse_val_err,
                        LLMInvalidJSONError,
                    ):

                        err_details = (
                            "\nJSON syntax error: "
                            f"{parse_val_err.message}"
                        )

                    error_message = (
                        "Your previous JSON response was "
                        "rejected because:"
                        f"{err_details}\n"
                        "Please correct these errors and "
                        "return ONLY a valid JSON object "
                        "matching the requested schema. "
                        "Do NOT include explanatory text, "
                        "markdown quotes, or thoughts "
                        "outside the JSON."
                    )

                    messages.append(
                        {
                            "role": "assistant",
                            "content": full_content,
                        }
                    )

                    messages.append(
                        {
                            "role": "user",
                            "content": error_message,
                        }
                    )

                    await asyncio.sleep(
                        0.5 * attempt
                    )

                    continue

                raise parse_val_err

            except httpx.ConnectError:

                raise LLMConnectionError(
                    f"Cannot reach Ollama at {self.base_url}"
                )

            except httpx.TimeoutException:

                raise LLMTimeoutError(
                    f"Ollama generation timed out "
                    f"after {self.timeout}s"
                )

            except (
                LLMModelMissingError,
                LLMConnectionError,
                LLMTimeoutError,
            ):

                raise

            except Exception as exc:

                last_error = exc

                if attempt < retries:

                    await asyncio.sleep(
                        0.5 * attempt
                    )

                    continue

                raise LLMProviderError(
                    "Ollama structured generation "
                    f"failed: {str(exc)}"
                )

        raise (
            last_error
            or LLMProviderError(
                "All structured generation retry "
                "attempts exhausted"
            )
        )

    # ------------------------------------------------------------------
    # Plain text generation
    # ------------------------------------------------------------------

    async def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        language: str = "en",
        max_retries: Optional[int] = None,
        temperature: float = 0.7,
        prompt_version: str = "1.0",
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Generates plain text using Ollama streaming.
        """

        retries = (
            max_retries
            if max_retries is not None
            else self.max_retries
        )

        lang_note = (
            f"\nRespond in: '{language}'."
            if language != "en"
            else ""
        )

        sys_content = (
            system_prompt
            or "You are Relay, an autonomous work agent."
        ) + lang_note

        messages = [
            {
                "role": "system",
                "content": sys_content,
            },
            {
                "role": "user",
                "content": prompt,
            },
        ]

        start_time = time.time()

        for attempt in range(1, retries + 1):

            try:

                (
                    full_content,
                    full_thinking,
                    tokens,
                ) = await self._stream_chat(
                    messages=messages,
                    temperature=temperature,
                    format_type="",
                )

                cleaned = self._strip_thinking(
                    full_content
                )

                duration_ms = int(
                    (time.time() - start_time) * 1000
                )

                return (
                    cleaned,
                    {
                        "provider": "ollama",
                        "model": self.model,
                        "prompt_version": prompt_version,
                        "attempts": attempt,
                        "tokens": tokens,
                        "duration_ms": duration_ms,
                    },
                )

            except httpx.ConnectError:

                raise LLMConnectionError(
                    f"Cannot reach Ollama at {self.base_url}"
                )

            except httpx.TimeoutException:

                raise LLMTimeoutError(
                    f"Ollama text generation timed out "
                    f"after {self.timeout}s"
                )

            except (
                LLMModelMissingError,
                LLMConnectionError,
                LLMTimeoutError,
            ):

                raise

            except Exception as exc:

                if attempt < retries:

                    await asyncio.sleep(
                        0.5 * attempt
                    )

                    continue

                raise LLMProviderError(
                    "Ollama text generation failed: "
                    f"{str(exc)}"
                )

        raise LLMProviderError(
            "All text generation retry attempts exhausted"
        )