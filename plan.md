# PawPal+ — Design plan

## Scenario (from README)

A busy pet owner needs help staying consistent with pet care. The app should:

- Track pet care tasks (walks, feeding, meds, enrichment, grooming, etc.)
- Consider constraints (time available, priority, owner preferences)
- Produce a daily plan and explain why it chose that plan

---

## Main identities (domain model)

These are the core **nouns** for UML and for splitting responsibilities.

**Scope:** Class fields align with **`app.py`** demo inputs: owner name, pet name, species, and each task’s description, time (minutes), and frequency.

| Identity | Role | Notes |
|----------|------|--------|
| **Owner** | Person using the app | **Name**; holds **pets** — matches `owner_name` and `Owner` / `add_pet` in code |
| **Pet** | Subject of care | **Name**, **species**, **tasks** — matches `pet_name`, `species`, and tasks added in `app.py` |
| **Task** (pet care task) | Unit of work to schedule | **Description**, **time (minutes)**, **frequency**, **completed** — `mark_complete()` updates status |
| **Daily plan / schedule** | Output for one day | **DailyPlan**: ordered **PlanSlots** (pet + task + explanation). **Scheduler** creates it. |
| **Scheduler** | Builds the daily plan | Takes an **Owner** (tasks live on each **Pet**), **produces** a **DailyPlan**. Explanations are generated in **`build_plan`**. |

---

## Core user actions (aligned with `app.py`)

These are the main actions the demo UI exposes. Anything not listed here (e.g. edit/delete tasks, clear list, dates, time budget) is out of scope until **`app.py`** adds controls for it.

### Inputs

1. **Set owner name** — `Owner name` text field (`owner_name`).
2. **Set pet name** — `Pet name` text field (`pet_name`).
3. **Set species** — `Species` select box (`dog` / `cat` / `other`).

### Tasks

4. **Set task fields** — `Task description`, `Time (minutes)` (1–240), `Frequency` (`daily` / `weekly` / `once`).
5. **Add task** — **`Add task`** appends one task dict `{ description, time_minutes, frequency }` to `st.session_state.tasks`.
6. **See tasks** — If the list is non-empty, **Current tasks:** plus a table; otherwise the **No tasks yet** message.

### Schedule

7. **Generate schedule** — **`Generate schedule`** builds an `Owner` → `Pet` with **`Task`** instances, then **`Scheduler.build_plan(owner)`** and displays **`DailyPlan`** slots.

### Passive (reading only)

- Open **Scenario** or **What you need to build** expanders.

### Mapping to the domain model

| User action | Domain touchpoints |
|-------------|---------------------|
| Set owner name | **`Owner`** |
| Set pet name / species | **`Pet`** |
| Add tasks / see task list | **`Task`** instances on **`Pet`** (from session task dicts) |
| Generate schedule | **`Scheduler.build_plan(owner)`** → **`DailyPlan`** (**`PlanSlot`** per row) |

---

## Classes: attributes, constructors, getters

Implementation lives in **`pawpal_system.py`**. Instance data is stored on private attributes (`_name`, etc.); **getters** are `@property` methods except **`DailyPlan.PlanSlot`**, which uses a frozen **`@dataclass`** plus **`get_order`**, **`get_pet`**, **`get_task`**, **`get_explanation`**.

### Owner

| Kind | Details |
|------|---------|
| **Constructor** | `__init__(name)` |
| **Attributes** | `name` (`str`), `pets` (`list[Pet]`) |
| **Methods** | `add_pet(pet)`, `all_tasks()` |

### Pet

| Kind | Details |
|------|---------|
| **Constructor** | `__init__(name, species)` |
| **Attributes** | `name` (`str`), `species` (`str`), `tasks` (copy via getter) |
| **Methods** | `add_task(task)` |

### Task

| Kind | Details |
|------|---------|
| **Constructor** | `__init__(description, time_minutes, frequency, completed=False)` |
| **Attributes** | `description`, `time_minutes`, `frequency`, `completed` |
| **Methods** | `mark_complete()` |

### DailyPlan

| Kind | Details |
|------|---------|
| **Constructor** | `__init__(slots)` — `slots` is a list of `DailyPlan.PlanSlot` |
| **Attributes** | `slots` (getter returns a copy) |

#### `DailyPlan.PlanSlot` (nested frozen dataclass)

| Kind | Details |
|------|---------|
| **Fields** | `order` (`int`), `pet` (`Pet`), `task` (`Task`), `explanation` (`str`) |
| **Getters** | `get_order()`, `get_pet()`, `get_task()`, `get_explanation()` |

### Scheduler

| Kind | Details |
|------|---------|
| **Constructor** | `__init__()` — no instance fields |
| **Methods** | `build_plan(owner) -> DailyPlan` — collects incomplete tasks from all pets, orders them, attaches explanations |
