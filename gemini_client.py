"""Gemini API wrapper for schedule explanation (RAG-grounded)."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")


def _normalize_model_id(name: str) -> str:
    if name.startswith("models/"):
        return name
    return f"models/{name}"


def _extract_json_array(text: str) -> list[dict[str, Any]] | None:
    """Parse model output into a list of objects; tolerate markdown fences."""
    t = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", t, re.I)
    if fence:
        t = fence.group(1).strip()
    try:
        data = json.loads(t)
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict) and "items" in data:
        inner = data["items"]
        return inner if isinstance(inner, list) else None
    if isinstance(data, list):
        return data
    return None


def explain_schedule_with_rag(
    *,
    owner_name: str,
    slots_payload: list[dict[str, Any]],
    knowledge_chunks: list[dict[str, Any]],
    api_key: str | None,
    model_name: str | None = None,
) -> list[dict[str, Any]] | None:
    """
    Call Gemini with retrieved snippets + deterministic slot facts.
    Returns list of {"order": int, "ai_why": str, "cited_ids": [str]} aligned by order, or None on failure/skip.
    """
    key = api_key or os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not key:
        logger.info("No GOOGLE_API_KEY/GEMINI_API_KEY set; skipping Gemini schedule explanation.")
        return None

    try:
        import google.generativeai as genai
    except ImportError:
        logger.warning("google-generativeai not installed; skipping Gemini.")
        return None

    genai.configure(api_key=key)
    model_id = _normalize_model_id(model_name or DEFAULT_MODEL)
    model = genai.GenerativeModel(model_id)
    logger.info("Calling Gemini model=%s for schedule explanation (%d slots).", model_id, len(slots_payload))

    kb_text = "\n".join(
        f"- [{c.get('id')}] ({', '.join(map(str, c.get('tags') or []))}) {c.get('text')}"
        for c in knowledge_chunks
    )
    slots_json = json.dumps(slots_payload, indent=2)

    prompt = f"""You are PawPal+, a scheduling assistant for pet care.

        RULES:
        - Output ONLY valid JSON (no markdown fences). Shape: {{"items": [{{"order": <int>, "ai_why": "<1-2 sentences>", "cited_ids": ["<id>", ...]}}]}}
        - There must be exactly one item per schedule step, same "order" values as input (1..N).
        - Do NOT contradict the given order, start times, or durations.
        - Use ONLY general care ideas supported by the KNOWLEDGE_SNIPPETS below for extra context; if none apply, keep ai_why to scheduling clarity only and cite [].
        - No medical diagnosis or emergency advice. Informational only.

        OWNER: {owner_name}

        DETERMINISTIC_SCHEDULE (do not change ordering meaning):
        {slots_json}

        KNOWLEDGE_SNIPPETS:
        {kb_text}
        """

    try:
        response = model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.35,
                "max_output_tokens": 2048,
            },
            request_options={"timeout": 45},
        )
    except Exception as exc:
        logger.exception("Gemini request failed: %s", exc)
        return None

    text = getattr(response, "text", None) or ""
    if not text and response.candidates:
        parts = []
        for part in response.candidates[0].content.parts:
            if hasattr(part, "text") and part.text:
                parts.append(part.text)
        text = "".join(parts)

    items = _extract_json_array(text)
    if not items:
        logger.warning("Gemini returned unparseable JSON; raw snippet: %s", text[:500])
        return None

    normalized: list[dict[str, Any]] = []
    for row in items:
        if not isinstance(row, dict):
            continue
        try:
            order = int(row["order"])
        except (KeyError, TypeError, ValueError):
            continue
        ai_why = str(row.get("ai_why", "")).strip()
        cited = row.get("cited_ids") or []
        if isinstance(cited, str):
            cited = [cited]
        cited_ids = [str(x) for x in cited if x]
        normalized.append({"order": order, "ai_why": ai_why, "cited_ids": cited_ids})
    return normalized or None
