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


def _extract_json_object(text: str) -> dict[str, Any] | None:
    """Parse model output into an object; tolerate markdown fences."""
    t = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", t, re.I)
    if fence:
        t = fence.group(1).strip()
    try:
        data = json.loads(t)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _normalize_preferences(raw: Any) -> list[dict[str, str]]:
    """Normalize arbitrary preference payload into a stable list."""
    if not isinstance(raw, list):
        return []
    normalized: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        pref_text = str(item.get("preference_text", "")).strip()
        if not pref_text:
            continue
        pref_type = str(item.get("type", "other")).strip().lower() or "other"
        confidence = str(item.get("confidence", "low")).strip().lower() or "low"
        if confidence not in {"low", "medium", "high"}:
            confidence = "low"
        hard_or_soft = str(item.get("hard_or_soft", "soft")).strip().lower() or "soft"
        if hard_or_soft not in {"hard", "soft"}:
            hard_or_soft = "soft"
        source_message = str(item.get("source_message", "")).strip()
        normalized.append(
            {
                "preference_text": pref_text,
                "type": pref_type,
                "confidence": confidence,
                "hard_or_soft": hard_or_soft,
                "source_message": source_message,
            }
        )
    return normalized


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


def chat_schedule_assistant_with_rag(
    *,
    owner_name: str,
    target_date_iso: str,
    tasks_payload: list[dict[str, Any]],
    knowledge_chunks: list[dict[str, Any]],
    chat_messages: list[dict[str, Any]],
    api_key: str | None,
    model_name: str | None = None,
    history_window: int = 10,
) -> dict[str, Any] | None:
    """
    Session chat helper for schedule Q&A + preference extraction.

    Returns:
    {
      "assistant_reply": str,
      "chat_summary": str,
      "preferences": [{preference_text, type, confidence, hard_or_soft, source_message}]
    }
    """
    key = api_key or os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not key:
        logger.info("No GOOGLE_API_KEY/GEMINI_API_KEY set; skipping schedule chat.")
        return None

    try:
        import google.generativeai as genai
    except ImportError:
        logger.warning("google-generativeai not installed; skipping Gemini schedule chat.")
        return None

    genai.configure(api_key=key)
    model_id = _normalize_model_id(model_name or DEFAULT_MODEL)
    model = genai.GenerativeModel(model_id)

    recent_messages = chat_messages[-max(1, history_window) :]
    messages_json = json.dumps(recent_messages, indent=2)
    tasks_json = json.dumps(tasks_payload, indent=2)
    kb_text = "\n".join(
        f"- [{c.get('id')}] ({', '.join(map(str, c.get('tags') or []))}) {c.get('text')}"
        for c in knowledge_chunks
    )

    prompt = f"""You are PawPal+, a scheduling assistant for pet care.

RULES:
- Output ONLY valid JSON object (no markdown fences) with this exact shape:
  {{
    "assistant_reply":"<helpful response in 2-5 sentences>",
    "chat_summary":"<1-2 short lines summarizing user preferences so far>",
    "preferences":[
      {{"preference_text":"<text>", "type":"time_window|ordering|avoidance|other", "confidence":"low|medium|high", "hard_or_soft":"soft|hard", "source_message":"<user text excerpt>"}}
    ]
  }}
- The assistant_reply must answer the most recent user question.
- Treat extracted preferences as best-effort unless user language is explicit (e.g., must/never/can't) then mark as hard.
- Keep safety scope informational only; no diagnosis or emergency medical advice.

OWNER: {owner_name}
TARGET_DATE: {target_date_iso}

TASKS:
{tasks_json}

KNOWLEDGE_SNIPPETS:
{kb_text}

RECENT_CHAT_HISTORY:
{messages_json}
"""

    try:
        response = model.generate_content(
            prompt,
            generation_config={"temperature": 0.35, "max_output_tokens": 2048},
            request_options={"timeout": 45},
        )
    except Exception as exc:
        logger.exception("Gemini schedule chat request failed: %s", exc)
        return None

    text = getattr(response, "text", None) or ""
    if not text and getattr(response, "candidates", None):
        parts = []
        for part in response.candidates[0].content.parts:
            if hasattr(part, "text") and part.text:
                parts.append(part.text)
        text = "".join(parts)

    obj = _extract_json_object(text)
    if not obj:
        logger.warning("Gemini returned unparseable schedule chat JSON; raw snippet: %s", text[:500])
        return None

    assistant_reply = str(obj.get("assistant_reply", "")).strip()
    chat_summary = str(obj.get("chat_summary", "")).strip()
    preferences = _normalize_preferences(obj.get("preferences"))
    if not assistant_reply:
        return None
    return {
        "assistant_reply": assistant_reply,
        "chat_summary": chat_summary,
        "preferences": preferences,
    }


def propose_daily_schedule_with_rag(
    *,
    owner_name: str,
    target_date_iso: str,
    tasks_payload: list[dict[str, Any]],
    knowledge_chunks: list[dict[str, Any]],
    api_key: str | None,
    model_name: str | None = None,
    repair_feedback: str | None = None,
    user_preferences: list[dict[str, Any]] | None = None,
    chat_summary: str | None = None,
) -> dict[str, Any] | None:
    """
    Ask Gemini for proposed daily times/order/reasons.

    Returns shape:
    {
      "items": [{"task_id","start_time","order","reason","cited_ids"}],
      "plan_summary": "..."
    }
    """
    key = api_key or os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not key:
        logger.info("No GOOGLE_API_KEY/GEMINI_API_KEY set; skipping Gemini schedule proposal.")
        return None

    try:
        import google.generativeai as genai
    except ImportError:
        logger.warning("google-generativeai not installed; skipping Gemini.")
        return None

    genai.configure(api_key=key)
    model_id = _normalize_model_id(model_name or DEFAULT_MODEL)
    model = genai.GenerativeModel(model_id)
    logger.info("Calling Gemini model=%s for schedule proposal (%d tasks).", model_id, len(tasks_payload))

    kb_text = "\n".join(
        f"- [{c.get('id')}] ({', '.join(map(str, c.get('tags') or []))}) {c.get('text')}"
        for c in knowledge_chunks
    )
    tasks_json = json.dumps(tasks_payload, indent=2)
    preferences_json = json.dumps(_normalize_preferences(user_preferences or []), indent=2)
    summary_note = str(chat_summary or "").strip()
    repair_note = (
        f"\nREPAIR_NOTES_FROM_PREVIOUS_ATTEMPT:\n{repair_feedback}\n"
        if repair_feedback
        else ""
    )

    prompt = f"""You are PawPal+, a scheduling assistant for pet care.

RULES:
- Output ONLY valid JSON object with this exact shape:
  {{
    "items": [
      {{"task_id":"<id>", "start_time":"HH:MM", "order":<int>, "reason":"<short text>", "cited_ids":["<kb_id>", ...]}}
    ],
    "plan_summary":"<1-2 lines>",
    "applied_preferences":["<preference text>", "..."],
    "unapplied_preferences":[{{"preference_text":"<text>", "why":"<brief reason>"}}]
  }}
- Include every task_id exactly once. No extra or missing tasks.
- start_time MUST be 24h HH:MM.
- Durations are fixed from input and must not overlap when combined with your chosen start_time values.
- Keep all windows within the same day (do not extend beyond 23:59).
- Use only provided knowledge snippets for care claims and cite ids used.
- No medical diagnosis or emergency advice; informational only.
- Soft preference: daily tasks often morning/evening, weekly tasks often later half of day, unless constraints suggest otherwise.
- You should attempt to satisfy USER_PREFERENCES when feasible, but task coverage and no-overlap are higher priority.
- If a preference cannot be met, include it in unapplied_preferences with a short reason.
{repair_note}
OWNER: {owner_name}
TARGET_DATE: {target_date_iso}

TASKS_TO_SCHEDULE:
{tasks_json}

USER_CHAT_SUMMARY:
{summary_note if summary_note else "None"}

USER_PREFERENCES:
{preferences_json}

KNOWLEDGE_SNIPPETS:
{kb_text}
"""

    try:
        response = model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.2 if repair_feedback is None else 0.1,
                "max_output_tokens": 4096,
            },
            request_options={"timeout": 60},
        )
    except Exception as exc:
        logger.exception("Gemini request failed: %s", exc)
        return None

    text = getattr(response, "text", None) or ""
    if not text and getattr(response, "candidates", None):
        parts = []
        for part in response.candidates[0].content.parts:
            if hasattr(part, "text") and part.text:
                parts.append(part.text)
        text = "".join(parts)

    obj = _extract_json_object(text)
    if not obj:
        logger.warning("Gemini returned unparseable proposal JSON; raw snippet: %s", text[:500])
        return None
    if not isinstance(obj.get("items"), list):
        logger.warning("Gemini proposal JSON missing items list.")
        return None
    if "plan_summary" not in obj:
        obj["plan_summary"] = ""
    if not isinstance(obj.get("applied_preferences"), list):
        obj["applied_preferences"] = []
    obj["applied_preferences"] = [str(x).strip() for x in obj["applied_preferences"] if str(x).strip()]
    if not isinstance(obj.get("unapplied_preferences"), list):
        obj["unapplied_preferences"] = []
    normalized_unapplied: list[dict[str, str]] = []
    for item in obj["unapplied_preferences"]:
        if isinstance(item, dict):
            pref_text = str(item.get("preference_text", "")).strip()
            why = str(item.get("why", "")).strip()
            if pref_text:
                normalized_unapplied.append({"preference_text": pref_text, "why": why})
        else:
            pref_text = str(item).strip()
            if pref_text:
                normalized_unapplied.append({"preference_text": pref_text, "why": ""})
    obj["unapplied_preferences"] = normalized_unapplied
    return obj
