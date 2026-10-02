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
    Real local Ollama provider for Relay.
    Communicates with Ollama API via HTTP. Supports streaming collection to prevent
    socket timeouts during CPU inference, isolates qwen3 reasoning tokens,
    and performs strict Pydantic validation with bounded corrective retries.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen3:4b",
        num_ctx: int = 4096,
        timeout: float = 300.0,
        max_retries: int = 3,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.num_ctx = num_ctx
        self.timeout = timeout
        self.max_retries = max_retries

    def _strip_thinking(self, text: str) -> str:
        """Strips <think>...</think> tags if they appear in text."""
        if not text:
            return ""
        cleaned = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.DOTALL)
        if "</think>" in cleaned:
            cleaned = cleaned.split("</think>")[-1]
        return cleaned.strip()

    def _clean_json_text(self, text: str) -> str:
        """Strips markdown code blocks (```json ... ```) and extracts raw JSON string."""
        cleaned = self._strip_thinking(text).strip()
        json_match = re.search(r"```(?:json)?\s*(\{[\s\S]*\}|\[[\s\S]*\])\s*```", cleaned, re.DOTALL)
        if json_match:
            return json_match.group(1).strip()
        
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            return cleaned[start:end + 1].strip()

        return cleaned

    async def health_check(self) -> Dict[str, Any]:
        """Checks if Ollama is reachable and configured model is installed."""
        tags_url = f"{self.base_url}/api/tags"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(tags_url)
                if res.status_code != 200:
                    return {
                        "provider": "ollama",
                        "model": self.model,
                        "reachable": True,
                        "available": False,
                        "status": "error",
                        "error": f"Ollama returned HTTP {res.status_code}",
                        "details": {"status_code": res.status_code}
                    }
                data = res.json()
                models: List[str] = [m.get("name", "") for m in data.get("models", [])]
                
                model_found = False
                matched_name = None
                for m in models:
                    if m == self.model or m == f"{self.model}:latest" or m.startswith(f"{self.model}:"):
                        model_found = True
                        matched_name = m
                        break
                    if ":" in self.model and m == self.model.split(":")[0]:
                        model_found = True
                        matched_name = m
                        break

                if not model_found:
                    return {
                        "provider": "ollama",
                        "model": self.model,
                        "reachable": True,
                        "available": False,
                        "status": "model_missing",
                        "error": f"Model '{self.model}' is not pulled. Run: ollama pull {self.model}",
                        "details": {"installed_models": models}
                    }

                return {
                    "provider": "ollama",
                    "model": matched_name or self.model,
                    "reachable": True,
                    "available": True,
                    "status": "ready",
                    "error": None,
                    "details": {"installed_models": models}
                }
        except httpx.ConnectError:
            return {
                "provider": "ollama",
                "model": self.model,
                "reachable": False,
                "available": False,
                "status": "unavailable",
                "error": f"Ollama is not running at {self.base_url}. Please start Ollama.",
                "details": {}
            }
        except httpx.TimeoutException:
            return {
                "provider": "ollama",
                "model": self.model,
                "reachable": False,
                "available": False,
                "status": "unavailable",
                "error": f"Timeout connecting to Ollama at {self.base_url}",
                "details": {}
            }
        except Exception as e:
            return {
                "provider": "ollama",
                "model": self.model,
                "reachable": False,
                "available": False,
                "status": "error",
                "error": str(e),
                "details": {}
            }

    async def _stream_chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.1,
        format_type: str = "json"
    ) -> Tuple[str, str, int]:
        """
        Streams from Ollama to avoid socket timeouts during CPU inference.
        Returns: (content_string, thinking_string, token_count)
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
            }
        }

        content_parts: List[str] = []
        thinking_parts: List[str] = []
        token_count = 0

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream("POST", f"{self.base_url}/api/chat", json=payload) as response:
                if response.status_code == 404:
                    raise LLMModelMissingError(self.model)
                elif response.status_code != 200:
                    body = await response.aread()
                    raise LLMProviderError(f"Ollama returned HTTP {response.status_code}: {body.decode(errors='replace')}")

                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                        msg = chunk.get("message", {})
                        think = msg.get("thinking")
                        content = msg.get("content")
                        if think:
                            thinking_parts.append(think)
                        if content:
                            content_parts.append(content)
                        token_count += 1
                        if token_count % 50 == 0:
                            print(f"[Ollama stream] Tokens generated: {token_count} (thinking: {len(''.join(thinking_parts))}, content: {len(''.join(content_parts))})", flush=True)
                    except json.JSONDecodeError:
                        continue

        full_content = "".join(content_parts).strip()
        full_thinking = "".join(thinking_parts).strip()
        return full_content, full_thinking, token_count

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
        Executes real structured generation with Ollama using stream-based collection,
        Pydantic validation, and bounded corrective retries.
        """
        retries = max_retries if max_retries is not None else self.max_retries
        
        # Build language instruction
        lang_note = f"\nYou must generate any natural language descriptions or user-facing text in: '{language}'." if language != "en" else ""
        if system_prompt:
            sys_content = system_prompt + lang_note
        else:
            schema_json_str = json.dumps(schema.model_json_schema(), indent=2)
            sys_content = (
                "You are Relay, an autonomous work agent. "
                f"You must respond with strictly valid JSON matching this schema:\n{schema_json_str}\n" +
                lang_note
            )
        
        messages = [
            {"role": "system", "content": sys_content},
            {"role": "user", "content": prompt}
        ]

        start_time = time.time()
        last_error = None

        for attempt in range(1, retries + 1):
            try:
                full_content, full_thinking, tokens = await self._stream_chat(
                    messages=messages,
                    temperature=temperature,
                    format_type="json"
                )

                # Clean thinking tokens if any got into content
                cleaned = self._clean_json_text(full_content)
                if not cleaned:
                    raise LLMInvalidJSONError(full_content, "Ollama returned empty response content")

                # Parse JSON
                try:
                    parsed_json = json.loads(cleaned)
                except json.JSONDecodeError as jde:
                    raise LLMInvalidJSONError(cleaned, f"Invalid JSON returned: {str(jde)}")

                # Validate with Pydantic
                try:
                    validated_instance = schema.model_validate(parsed_json)
                    duration_ms = int((time.time() - start_time) * 1000)
                    meta = {
                        "provider": "ollama",
                        "model": self.model,
                        "prompt_version": prompt_version,
                        "attempts": attempt,
                        "tokens_generated": tokens,
                        "duration_ms": duration_ms,
                        "thinking_length": len(full_thinking),
                        "raw_output": full_content,
                    }
                    return validated_instance, meta
                except ValidationError as ve:
                    raise LLMSchemaValidationError(schema.__name__, ve.errors(), raw_json=parsed_json)

            except (LLMInvalidJSONError, LLMSchemaValidationError) as parse_val_err:
                last_error = parse_val_err
                if attempt < retries:
                    err_details = ""
                    if isinstance(parse_val_err, LLMSchemaValidationError):
                        # Format specific validation error messages for the LLM
                        err_lines = []
                        for err in parse_val_err.details.get("validation_errors", []):
                            loc = " -> ".join(str(l) for l in err.get("loc", []))
                            msg = err.get("msg", "")
                            err_lines.append(f"- Field '{loc}': {msg}")
                        err_details = "\nValidation errors:\n" + "\n".join(err_lines)
                    elif isinstance(parse_val_err, LLMInvalidJSONError):
                        err_details = f"\nJSON syntax error: {parse_val_err.message}"

                    err_msg = (
                        f"Your previous JSON response was rejected because:{err_details}\n"
                        f"Please correct these errors and return ONLY a valid JSON object matching the requested schema. "
                        f"Do NOT include any explanatory text, markdown quotes, or thoughts outside the JSON."
                    )
                    messages.append({"role": "assistant", "content": full_content})
                    messages.append({"role": "user", "content": err_msg})
                    await asyncio.sleep(0.5 * attempt)
                    continue
                else:
                    raise parse_val_err

            except httpx.ConnectError:
                raise LLMConnectionError(f"Cannot reach Ollama at {self.base_url}")
            except httpx.TimeoutException:
                raise LLMTimeoutError(f"Ollama generation timed out after {self.timeout}s")
            except (LLMModelMissingError, LLMConnectionError, LLMTimeoutError):
                raise
            except Exception as e:
                last_error = e
                if attempt < retries:
                    await asyncio.sleep(0.5 * attempt)
                    continue
                raise LLMProviderError(f"Ollama structured generation failed: {str(e)}")

        raise last_error or LLMProviderError("All structured generation retry attempts exhausted")

    async def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        language: str = "en",
        max_retries: Optional[int] = None,
        temperature: float = 0.7,
        prompt_version: str = "1.0",
    ) -> Tuple[str, Dict[str, Any]]:
        """Generates plain text with Ollama via streaming collection."""
        retries = max_retries if max_retries is not None else self.max_retries
        lang_note = f"\nRespond in: '{language}'." if language != "en" else ""
        sys_content = (system_prompt or "You are Relay, an autonomous work agent.") + lang_note
        
        messages = [
            {"role": "system", "content": sys_content},
            {"role": "user", "content": prompt}
        ]

        start_time = time.time()
        for attempt in range(1, retries + 1):
            try:
                full_content, full_thinking, tokens = await self._stream_chat(
                    messages=messages,
                    temperature=temperature,
                    format_type=""
                )
                cleaned = self._strip_thinking(full_content)
                duration_ms = int((time.time() - start_time) * 1000)

                return cleaned, {
                    "provider": "ollama",
                    "model": self.model,
                    "prompt_version": prompt_version,
                    "attempts": attempt,
                    "tokens": tokens,
                    "duration_ms": duration_ms,
                }
            except httpx.ConnectError:
                raise LLMConnectionError(f"Cannot reach Ollama at {self.base_url}")
            except httpx.TimeoutException:
                raise LLMTimeoutError(f"Ollama text generation timed out after {self.timeout}s")
            except (LLMModelMissingError, LLMConnectionError, LLMTimeoutError):
                raise
            except Exception as e:
                if attempt < retries:
                    await asyncio.sleep(0.5 * attempt)
                    continue
                raise LLMProviderError(f"Ollama text generation failed: {str(e)}")

        raise LLMProviderError("All text generation retry attempts exhausted")
