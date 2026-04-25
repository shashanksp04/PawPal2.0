# PawPal+

PawPal+ is a Streamlit app for a single owner to manage pet-care tasks and generate a **daily AI schedule**. Users enter pet/task details without start times, then Gemini + RAG proposes task times, order, and reasoning. The proposal is validated in code (no overlaps, full task coverage), and **Save schedule** writes approved times into JSON.

## What changed

- Task creation no longer asks for `HH:MM`.
- AI proposes `start_time` for each pending task.
- Validation enforces:
  - every pending `task_id` appears exactly once,
  - all times are valid `HH:MM`,
  - intervals `[start, start + duration)` do not overlap,
  - no task extends past midnight.
- UI shows model reasoning and cited knowledge-base ids.
- `Save schedule` persists proposed times to `data/pawpal_store.json`.

## Data model and storage

- JSON store: `data/pawpal_store.json` (auto-created if missing).
- Example schema: `data/pawpal_store.example.json`.
- Current schema version is `2`.
- `start_time` can be `null` for unscheduled tasks.

## AI and RAG

- Retriever: `pawpal_rag.py` over `data/knowledge_base.json`.
- Model client: `gemini_client.py`.
- Main generation API: `propose_daily_schedule_with_rag(...)`.
- Prompt guardrails require JSON-only output, no diagnosis advice, no overlap in proposed windows, and citation ids from provided snippets.

## Setup

```bash
python -m venv .venv
```

Activate venv:

- Windows: `.venv\Scripts\activate`
- macOS/Linux: `source .venv/bin/activate`

Install deps:

```bash
pip install -r requirements.txt
```

Set API key (examples):

```powershell
$env:GOOGLE_API_KEY = "your-key"
```

```bash
export GOOGLE_API_KEY="your-key"
```

Optional:

```bash
export GEMINI_MODEL="gemini-2.5-flash"
```

## Run

```bash
streamlit run app.py
```

Flow:

1. Add pets and tasks (no start time).
2. Click **Generate schedule**.
3. Review AI plan + reasoning.
4. Click **Save schedule** to persist times.

## Tests

```bash
pytest tests/ -v
```

Tests include:

- core scheduling and overlap helpers,
- JSON round-trip including `start_time: null`,
- AI proposal validation (`validate_proposed_schedule`),
- mocked Gemini responses and JSON parsing,
- RAG retrieval behavior.
