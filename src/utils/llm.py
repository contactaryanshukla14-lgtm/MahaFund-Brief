import os
import time
import random
import asyncio
import json
from typing import Any, Optional, Dict
from dotenv import load_dotenv

load_dotenv()

from google import genai
from google.genai import types
from groq import Groq

from src.utils.logger import get_logger
from src.config import MAX_RETRIES, RETRY_BASE_DELAY_SECONDS

log = get_logger("llm")

# ── Key pools ───────────────────────────────────────────────────────────

def _load_keys(prefix: str) -> list[str]:
    """Collect API keys from env vars with the given prefix, deduplicated."""
    keys: list[str] = []
    # If the exact prefix without _ is set (e.g. GEMINI_API_KEY)
    main = os.getenv(prefix[:-1], "").strip() if prefix.endswith("_") else ""
    if main:
        keys.append(main)
        
    for k, v in os.environ.items():
        if k.startswith(prefix) and v and v.strip():
            keys.append(v.strip())
    return list(set(keys))

_GEMINI_POOL = _load_keys("GEMINI_API_KEY_")
_GROQ_POOL = _load_keys("GROQ_API_KEY_")


class ResponseMock:
    """Mock response object so agents don't have to change .text access."""
    def __init__(self, text: str):
        self.text = text


# ── Client Getters ──────────────────────────────────────────────────────

def get_gemini_client(exclude_key: Optional[str] = None) -> Optional[genai.Client]:
    pool = [k for k in _GEMINI_POOL if k != exclude_key] if exclude_key else _GEMINI_POOL
    if not pool:
        pool = _GEMINI_POOL
    if not pool:
        log.error("No Gemini API keys found.")
        return None
    selected = random.choice(pool)
    log.info(f"Using Gemini key: {selected[:8]}...{selected[-4:]}")
    return genai.Client(api_key=selected)


def get_groq_client(exclude_key: Optional[str] = None) -> Optional[Groq]:
    pool = [k for k in _GROQ_POOL if k != exclude_key] if exclude_key else _GROQ_POOL
    if not pool:
        pool = _GROQ_POOL
    if not pool:
        log.error("No Groq API keys found.")
        return None
    selected = random.choice(pool)
    log.info(f"Using Groq key: {selected[:8]}...{selected[-4:]}")
    return Groq(api_key=selected)


# ── Generators ──────────────────────────────────────────────────────────

async def gemini_generate_with_retry(
    *,
    contents: Any,
    config: Optional[dict] = None,
    model: Optional[str] = None,
) -> Optional[Any]:
    """Gemini generator strictly for Vision/OCR tasks."""
    from src.config import GEMINI_MODEL
    model = model or GEMINI_MODEL
    last_key: Optional[str] = None

    for attempt in range(1, MAX_RETRIES + 1):
        client = get_gemini_client(exclude_key=last_key)
        if not client:
            return None

        try:
            kwargs = {"model": model, "contents": contents}
            if config:
                kwargs["config"] = config
            response = client.models.generate_content(**kwargs)
            return response

        except Exception as e:
            err_str = str(e)
            if any(x in err_str for x in ["429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE"]):
                delay = RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1))
                log.warning(f"Gemini API Error (attempt {attempt}): {err_str[:100]}... Retrying in {delay}s...")
                last_key = client._api_key if hasattr(client, "_api_key") else None
                await asyncio.sleep(delay)
            else:
                log.error(f"Gemini call failed: {e}")
                raise

    log.error("Gemini retry attempts exhausted.")
    return None


async def groq_generate_with_retry(
    *,
    contents: str,
    response_schema: Optional[Any] = None,
    model: Optional[str] = None,
) -> Optional[ResponseMock]:
    """Groq generator strictly for massive Text/JSON extraction tasks."""
    from src.config import GROQ_MODEL
    model = model or GROQ_MODEL
    last_key: Optional[str] = None

    # Inject JSON schema into prompt to guarantee structure
    prompt = contents
    if response_schema:
        schema_dict = response_schema.model_json_schema()
        prompt += f"\n\nYou MUST return ONLY a valid JSON object adhering exactly to this schema:\n{json.dumps(schema_dict)}"

    for attempt in range(1, MAX_RETRIES + 1):
        client = get_groq_client(exclude_key=last_key)
        if not client:
            return None

        try:
            # We run the synchronous Groq client in a thread pool so it doesn't block asyncio
            def _call():
                return client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"} if response_schema else None,
                    temperature=0.0
                )
            
            response = await asyncio.to_thread(_call)
            return ResponseMock(response.choices[0].message.content)

        except Exception as e:
            err_str = str(e)
            if any(x in err_str for x in ["429", "rate limit", "503"]):
                delay = RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1))
                log.warning(f"Groq API Error (attempt {attempt}): {err_str[:100]}... Retrying in {delay}s...")
                last_key = client.api_key
                await asyncio.sleep(delay)
            else:
                log.error(f"Groq call failed: {e}")
                raise

    log.error("Groq retry attempts exhausted.")
    return None
