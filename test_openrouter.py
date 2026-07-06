"""Standalone diagnostic script for OpenRouter connectivity."""
import asyncio
import json
import os
import traceback

import httpx
from openai import AsyncOpenAI, APIError

import config


def _proxies():
    proxies = {
        "http://": os.getenv("HTTP_PROXY"),
        "https://": os.getenv("HTTPS_PROXY"),
    }
    return {k: v for k, v in proxies.items() if v} or None


async def direct_http_test():
    """Make a direct HTTP POST to OpenRouter and print the raw response."""
    print("=" * 60)
    print("TEST 1: Direct HTTP request to OpenRouter")
    print("=" * 60)

    url = f"{config.OPENROUTER_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    if "openrouter.ai" in config.OPENROUTER_BASE_URL:
        headers["HTTP-Referer"] = config.SITE_URL
        headers["X-Title"] = config.SITE_NAME

    body = {
        "model": config.MODEL_NAME,
        "messages": [{"role": "user", "content": "Say hello in one word."}],
        "max_tokens": 10,
    }

    print(f"URL: {url}")
    print(f"Headers: {json.dumps({k: v for k, v in headers.items() if k != 'Authorization'}, indent=2)}")
    key_preview = config.OPENROUTER_API_KEY
    if len(key_preview) > 12:
        key_preview = f"{key_preview[:6]}...{key_preview[-4:]}"
    else:
        key_preview = "<not-set or short>"
    print(f"Authorization key preview: {key_preview}")
    print(f"Request body: {json.dumps(body, indent=2)}")

    try:
        async with httpx.AsyncClient(timeout=30.0, proxy=_proxies()) as client:
            response = await client.post(url, headers=headers, json=body)
            print(f"\nResponse status: {response.status_code}")
            print(f"Response headers: {dict(response.headers)}")
            print(f"Response body: {response.text}")
    except Exception as e:
        print(f"\nDirect HTTP request failed: {type(e).__name__}: {e}")
        traceback.print_exc()


async def client_test():
    """Try the same request through the OpenAI client."""
    print("\n" + "=" * 60)
    print("TEST 2: Request via OpenAI client")
    print("=" * 60)

    client = AsyncOpenAI(
        base_url=config.OPENROUTER_BASE_URL,
        api_key=config.OPENROUTER_API_KEY or "not-set",
        max_retries=0,
    )

    try:
        response = await client.chat.completions.create(
            model=config.MODEL_NAME,
            messages=[{"role": "user", "content": "Say hello in one word."}],
            max_tokens=10,
        )
        print(f"Success! Response: {response.choices[0].message.content}")
    except APIError as e:
        print(f"APIError: {e}")
        print(f"Error body: {getattr(e, 'body', None)}")
        print(f"Error cause: {getattr(e, '__cause__', None)}")
        traceback.print_exc()
    except Exception as e:
        print(f"Other error: {type(e).__name__}: {e}")
        traceback.print_exc()


async def main():
    print(f"Loaded config:")
    print(f"  OPENROUTER_BASE_URL = {config.OPENROUTER_BASE_URL}")
    print(f"  MODEL_NAME = {config.MODEL_NAME}")
    key_preview = config.OPENROUTER_API_KEY
    if len(key_preview) > 12:
        key_preview = f"{key_preview[:6]}...{key_preview[-4:]}"
    else:
        key_preview = "<not-set or short>"
    print(f"  OPENROUTER_API_KEY = {key_preview}")

    await direct_http_test()
    await client_test()


if __name__ == "__main__":
    asyncio.run(main())
