import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from uuid import uuid4

import httpx
from openai import AsyncOpenAI, APIError, APITimeoutError

import config

logger = logging.getLogger(__name__)

# JSONL log file for verbatim LLM request/response debugging.
LLM_LOG_FILE = os.getenv("LLM_LOG_FILE", "llm_calls.jsonl")


def _write_llm_log(entry: dict):
    """Append a single JSON object as one line to the JSONL log file."""
    if not LLM_LOG_FILE:
        return
    try:
        with open(LLM_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except Exception as e:
        logger.warning("Failed to write LLM JSONL log: %s", e)


def _openrouter_headers():
    if "openrouter.ai" in config.OPENROUTER_BASE_URL:
        return {
            "HTTP-Referer": config.SITE_URL,
            "X-Title": config.SITE_NAME,
        }
    return None


async def _log_request(request: httpx.Request):
    logger.info("LLM REQUEST -> %s %s (full payload in JSONL log)", request.method, request.url)


async def _log_response(response: httpx.Response):
    request = response.request
    logger.info(
        "LLM RESPONSE <- %s for %s %s (full payload in JSONL log)",
        response.status_code,
        request.method,
        request.url,
    )


# Optional proxy support for restricted networks.
_http_proxies = {
    "http://": os.getenv("HTTP_PROXY"),
    "https://": os.getenv("HTTPS_PROXY"),
}
_http_proxies = {k: v for k, v in _http_proxies.items() if v}

# Custom HTTP client so we can log every request/response to the LLM endpoint.
http_client = httpx.AsyncClient(
    event_hooks={
        "request": [_log_request],
        "response": [_log_response],
    },
    timeout=config.REQUEST_TIMEOUT,
    proxy=_http_proxies or None,
)

client = AsyncOpenAI(
    base_url=config.OPENROUTER_BASE_URL,
    api_key=config.OPENROUTER_API_KEY or "not-set",
    default_headers=_openrouter_headers(),
    http_client=http_client,
    max_retries=1,  # Client handles retries; we handle the final fallback.
)


async def chat_completion(
    messages: list,
    temperature: float = 0.7,
    max_tokens: int = 150,
    model: str | None = None,
) -> str:
    """Call the configured OpenAI-compatible chat endpoint.

    Args:
        messages: Conversation messages.
        temperature: Sampling temperature.
        max_tokens: Maximum tokens to generate.
        model: Model override. Defaults to config.MODEL_NAME if not provided.
    """
    request_id = str(uuid4())
    started_at = time.perf_counter()
    model = model or config.MODEL_NAME
    logger.info(
        "LLM call starting request_id=%s model=%s (full payload in JSONL log)",
        request_id,
        model,
    )

    request_payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request_id": request_id,
        "request": request_payload,
        "response": None,
        "error": None,
        "duration_ms": None,
    }

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=config.REQUEST_TIMEOUT,
            extra_headers=_openrouter_headers(),
        )
        choice = response.choices[0]
        content = choice.message.content
        finish_reason = getattr(choice, "finish_reason", "unknown")
        usage = getattr(response, "usage", None)

        log_entry["response"] = {
            "content": content,
            "finish_reason": finish_reason,
            "usage": usage.model_dump() if usage is not None else None,
        }
        log_entry["duration_ms"] = round((time.perf_counter() - started_at) * 1000, 2)
        _write_llm_log(log_entry)

        if content and content.strip():
            return content.strip()

        # Empty/null content often means a reasoning model spent its whole token budget
        # on internal reasoning and had none left for the final answer.
        reasoning = getattr(choice.message, "reasoning", None)
        logger.warning(
            "LLM returned empty content (model=%s, finish_reason=%s, has_reasoning=%s, max_tokens=%s). "
            "Reasoning models may need a larger max_tokens budget.",
            config.MODEL_NAME,
            finish_reason,
            bool(reasoning),
            max_tokens,
        )
        if reasoning:
            # Log the reasoning excerpt for debugging; don't expose raw reasoning as the reply.
            logger.debug("LLM reasoning excerpt: %s", reasoning[:500])
        return "[I'm having trouble thinking right now. Could we try again?]"
    except (APIError, APITimeoutError, asyncio.TimeoutError) as e:
        error_body = getattr(e, "body", None)
        cause = getattr(e, "__cause__", None)
        log_entry["error"] = {
            "type": type(e).__name__,
            "message": str(e),
            "body": error_body,
            "cause": str(cause) if cause else None,
        }
        log_entry["duration_ms"] = round((time.perf_counter() - started_at) * 1000, 2)
        _write_llm_log(log_entry)
        logger.error(
            "LLM call failed: %s type=%s body=%s cause=%s",
            e,
            type(e).__name__,
            error_body,
            cause,
        )
        return f"[I'm having trouble thinking right now ({type(e).__name__}).]"
    except Exception as e:
        log_entry["error"] = {
            "type": type(e).__name__,
            "message": str(e),
        }
        log_entry["duration_ms"] = round((time.perf_counter() - started_at) * 1000, 2)
        _write_llm_log(log_entry)
        logger.exception("Unexpected LLM call failure")
        return f"[I'm having trouble thinking right now ({type(e).__name__}).]"
