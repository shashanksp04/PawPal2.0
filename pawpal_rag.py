"""Minimal keyword-based retrieval over the local pet-care knowledge base."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_TOKEN_RE = re.compile(r"[a-z0-9]+", re.I)


def default_knowledge_path() -> Path:
    return Path(__file__).resolve().parent / "data" / "knowledge_base.json"


def _tokenize(text: str) -> set[str]:
    return {m.group(0).lower() for m in _TOKEN_RE.finditer(text or "")}


def load_knowledge_entries(path: Path | None = None) -> list[dict[str, Any]]:
    p = path or default_knowledge_path()
    raw = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("knowledge_base.json must be a JSON array.")
    return list(raw)


def score_entry(entry: dict[str, Any], query_tokens: set[str]) -> int:
    tags = entry.get("tags") or []
    topic = str(entry.get("topic", ""))
    text = str(entry.get("text", ""))
    blob_tokens = _tokenize(" ".join([topic, text, *map(str, tags)]))
    overlap = len(query_tokens & blob_tokens)
    tag_hits = sum(1 for t in tags if str(t).lower() in query_tokens)
    return overlap * 3 + tag_hits * 2


def retrieve_for_schedule_context(
    *,
    owner_name: str,
    slot_lines: list[str],
    species_list: list[str],
    preference_lines: list[str] | None = None,
    top_k: int = 5,
    path: Path | None = None,
) -> list[dict[str, Any]]:
    """
    Return top_k knowledge entries as dicts with id, text, tags, topic, score.
    slot_lines: human-readable lines per plan step for keyword overlap.
    """
    entries = load_knowledge_entries(path)
    bounded_preferences = [(line or "").strip()[:120] for line in (preference_lines or []) if (line or "").strip()]
    bounded_preferences = bounded_preferences[:4]
    query = " ".join([owner_name, *species_list, *slot_lines, *bounded_preferences])
    qtok = _tokenize(query)
    scored: list[tuple[int, dict[str, Any]]] = []
    for e in entries:
        s = score_entry(e, qtok)
        scored.append((s, e))
    scored.sort(key=lambda x: (-x[0], str(x[1].get("id", ""))))
    out: list[dict[str, Any]] = []
    for s, e in scored[:top_k]:
        if s <= 0:
            continue
        out.append(
            {
                "id": e.get("id"),
                "text": e.get("text"),
                "tags": list(e.get("tags") or []),
                "topic": e.get("topic"),
                "score": s,
            }
        )
    if not out:
        for e in entries[: min(3, len(entries))]:
            out.append(
                {
                    "id": e.get("id"),
                    "text": e.get("text"),
                    "tags": list(e.get("tags") or []),
                    "topic": e.get("topic"),
                    "score": 0,
                }
            )
    return out[:top_k]
