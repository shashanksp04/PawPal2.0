"""Tests for keyword RAG retrieval."""

from pathlib import Path

import pytest

from pawpal_rag import load_knowledge_entries, retrieve_for_schedule_context


def test_load_knowledge_entries() -> None:
    entries = load_knowledge_entries()
    assert len(entries) >= 5
    assert all("id" in e and "text" in e for e in entries)


def test_retrieve_returns_scored_chunks() -> None:
    chunks = retrieve_for_schedule_context(
        owner_name="Alex",
        slot_lines=["1. Mochi (dog) Morning walk @ 08:00 30m daily"],
        species_list=["dog"],
        top_k=3,
    )
    assert len(chunks) <= 3
    ids = [c["id"] for c in chunks]
    assert any("dog" in str(c.get("tags", [])) for c in chunks) or len(ids) >= 1


def test_retrieve_falls_back_when_no_scores(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = tmp_path / "kb.json"
    p.write_text('[{"id":"only","tags":["x"],"topic":"t","text":"zzz"}]', encoding="utf-8")
    chunks = retrieve_for_schedule_context(
        owner_name="Z",
        slot_lines=["nonsense xyz qwerty"],
        species_list=["other"],
        top_k=2,
        path=p,
    )
    assert len(chunks) >= 1
