"""Tests for Gemini schedule explanation (mocked)."""

from unittest.mock import MagicMock, patch

from gemini_client import explain_schedule_with_rag


@patch("google.generativeai.configure")
@patch("google.generativeai.GenerativeModel")
def test_explain_schedule_parses_json(mock_model_cls: MagicMock, _mock_cfg: MagicMock) -> None:
    instance = MagicMock()
    mock_model_cls.return_value = instance
    resp = MagicMock()
    resp.text = '{"items": [{"order": 1, "ai_why": "Walk first fits the routine.", "cited_ids": ["dog-walk-01"]}]}'
    instance.generate_content.return_value = resp

    slots = [
        {
            "order": 1,
            "pet": "Mochi",
            "species": "dog",
            "task": "Walk",
            "start": "08:00",
            "minutes": 30,
            "frequency": "daily",
            "code_why": "Step 1/1 ...",
        }
    ]
    kb = [{"id": "dog-walk-01", "text": "Dogs like walks.", "tags": ["dog"]}]

    out = explain_schedule_with_rag(
        owner_name="Alex",
        slots_payload=slots,
        knowledge_chunks=kb,
        api_key="fake-key-for-test",
        model_name="gemini-2.5-flash",
    )
    assert out is not None
    assert len(out) == 1
    assert out[0]["order"] == 1
    assert "walk" in out[0]["ai_why"].lower()
    assert "dog-walk-01" in out[0]["cited_ids"]


def test_explain_schedule_skips_without_key() -> None:
    import os

    for k in ("GOOGLE_API_KEY", "GEMINI_API_KEY"):
        os.environ.pop(k, None)
    out = explain_schedule_with_rag(
        owner_name="Alex",
        slots_payload=[{"order": 1, "pet": "P", "species": "dog", "task": "t", "code_why": "x"}],
        knowledge_chunks=[],
        api_key=None,
    )
    assert out is None
