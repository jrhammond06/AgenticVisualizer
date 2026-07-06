import json
import re


def extract_json(text: str) -> dict | None:
    """Try to extract a JSON object from LLM output that may be wrapped in markdown fences or mixed with extra text."""
    text = text.strip()

    # If the response starts with a markdown fence, grab only the fenced block.
    if text.startswith("```"):
        match = re.search(r"^```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            text = match.group(1).strip()

    # Try parsing the extracted/normalized text directly.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Fallback: find the first {...} object anywhere in the text.
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return None
