import json
import re
from typing import Any

import httpx

from app.core.settings import get_settings


class LLMError(Exception):
    pass


def _extract_json(text: str) -> Any:
    raw = (text or "").strip()

    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", raw)
        if raw.endswith("```"):
            raw = raw[: -3]
        raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    start_candidates = [raw.find("["), raw.find("{"), raw.find('"')]
    start_candidates = [i for i in start_candidates if i != -1]
    if not start_candidates:
        raise LLMError("non_json_output")

    start = min(start_candidates)

    if raw[start] == "[":
        end = raw.rfind("]")
        if end == -1:
            raise LLMError("non_json_output")
        snippet = raw[start : end + 1]
    elif raw[start] == "{":
        end = raw.rfind("}")
        if end == -1:
            raise LLMError("non_json_output")
        snippet = raw[start : end + 1]
    else:
        # JSON string; parse until the last quote.
        end = raw.rfind('"')
        if end <= start:
            raise LLMError("non_json_output")
        snippet = raw[start : end + 1]

    try:
        return json.loads(snippet)
    except json.JSONDecodeError as e:
        raise LLMError("non_json_output") from e


async def _chat_completion_json(*, system: str, user: str) -> Any:
    settings = get_settings()
    if not settings.openai_api_key:
        raise LLMError("missing_api_key")

    url = settings.openai_base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.openai_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code >= 400:
            raise LLMError(f"http_{resp.status_code}")
        data = resp.json()

    try:
        content = data["choices"][0]["message"]["content"]
    except Exception as e:  # noqa: BLE001
        raise LLMError("invalid_response") from e

    return _extract_json(content)


async def generate_microsteps(task_title: str, context: str | None, previous_steps: list[str] | None = None) -> list[str]:
    from app.services.web_search import search_web

    system = (
        "You are a productivity coach. Produce embarrassingly small microsteps (1-5 minutes each). "
        "Avoid health/medical language. Output must be JSON array of strings only, max 7 items. "
        "Each step must start with a verb and be concrete (e.g. 'Open X', 'Write 2 bullets'). "
        "If web search results are provided, USE them to give specific, factual answers "
        "and incorporate real information into the steps (e.g. specific times, addresses, details)."
    )
    if previous_steps:
        system += (
            " The user already has some microsteps and wants ADDITIONAL ones. "
            "Do NOT repeat any of the previous steps. Suggest different, complementary actions "
            "that build on or go beyond what they already have."
        )

    user = f"Task title: {task_title}\n"
    if context:
        user += f"Context: {context}\n"

    # Run web search when user provides context (likely contains a question or request)
    if context and len(context.strip()) > 10:
        search_query = f"{task_title} {context}"
        search_results = await search_web(search_query, max_results=5)
        if search_results:
            snippets = "\n".join(
                f"- {r['title']}: {r['body']}" + (f" ({r['href']})" if r['href'] else "")
                for r in search_results
            )
            user += f"\nWeb search results (use these for specific facts):\n{snippets}\n"

    if previous_steps:
        user += f"Previous steps (do NOT repeat these): {json.dumps(previous_steps)}\n"
    user += "Return only a JSON array of microstep strings."

    result = await _chat_completion_json(system=system, user=user)
    if not isinstance(result, list) or not all(isinstance(x, str) for x in result):
        raise LLMError("invalid_schema")
    return [s.strip() for s in result[:7] if s.strip()]


async def generate_next_step_from_reflection(task_title: str, reflection: dict) -> str:
    system = (
        "You are a productivity coach. Suggest exactly one concrete next step that takes 1-5 minutes. "
        "Avoid health/medical language. Output must be a JSON string only. "
        "The string must start with a verb and be specific."
    )

    user = (
        f"Task title: {task_title}\n"
        f"Reflection JSON: {json.dumps(reflection)}\n"
        "Return only a JSON string with the suggested next step."
    )

    result = await _chat_completion_json(system=system, user=user)
    if not isinstance(result, str):
        raise LLMError("invalid_schema")
    return result.strip()
