# PawPal+

**PawPal+** is a Streamlit app that helps pet owners plan care tasks across one or more pets. You define tasks with duration, frequency, and start times; the app surfaces scheduling conflicts, lists pending work in time order, and builds an ordered daily plan with short explanations for each step.

---

## Features

The scheduling layer lives in `pawpal_system.py` (`Owner`, `Pet`, `Task`, `Scheduler`, `DailyPlan`). The UI in `app.py` calls into that logic.

- **Sorting by start time** — Tasks are ordered by normalized **HH:MM** clock times (earliest first). The scheduler uses a dedicated sort key on hour and minute so lists stay consistent regardless of input order.

- **Conflict warnings (same start time)** — For **incomplete** tasks only, the app groups by identical start time across all pets. If two or more tasks share the same clock time, you get a warning listing which pets and tasks collide. This is an exact-time check (not duration overlap).

- **Filtering** — Pending tasks can be filtered by completion state and optionally by **pet name**, producing `(pet, task)` pairs for display and further sorting.

- **Daily / weekly / once recurrence** — Tasks support **daily**, **weekly**, and **once** frequencies. `Pet.complete_task` marks work done and, for daily or weekly tasks, appends the next occurrence with an updated **due date** (next day or next week), preserving duration and start time. **Once** tasks do not repeat. The CLI demo in `main.py` exercises this flow.

- **Plan generation with priority rules** — `build_plan` orders pending tasks by: **recurrence importance** (daily before weekly before once), then **shorter duration**, then **pet name**, then **task description** (tie-breakers). Each slot includes a **“Why”** explanation describing that ordering.

- **Normalized times** — Start times are validated and normalized to zero-padded **HH:MM** for comparisons and sorting.

---

## 📸 Demo

Replace the path below with your screenshot file (or drop the image next to this README and adjust the relative path).

![PawPal+ Streamlit app](pictures/Demo.png)

---

## Requirements

- Python 3.10+ (uses modern typing such as `list[str]`, `date | None`)

Dependencies are listed in `requirements.txt` (Streamlit for the UI, pytest for tests).

---

## Installation

```bash
python -m venv .venv
```

**Activate the virtual environment**

- **Windows:** `.venv\Scripts\activate`
- **macOS / Linux:** `source .venv/bin/activate`

```bash
pip install -r requirements.txt
```

---

## Run the app

From the project root (with the venv activated):

```bash
streamlit run app.py
```

The app opens in your browser. Owner data is kept in Streamlit session state so it persists across interactions in a session.

---

## CLI demo (optional)

A small terminal script exercises sorting, filtering, conflicts, completion/recurrence, and `build_plan`:

```bash
python main.py
```

---

## Tests

```bash
pytest tests/ -v
```

---

## Project layout

| Path | Role |
|------|------|
| `app.py` | Streamlit UI |
| `pawpal_system.py` | Domain model and scheduling algorithms |
| `main.py` | Command-line demo |
| `tests/test_pawpal.py` | Pytest coverage for core behaviors |
