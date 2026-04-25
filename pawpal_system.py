from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

logger = logging.getLogger(__name__)


def _normalize_hhmm(value: str) -> str:
    """Normalize a clock time to zero-padded HH:MM for sorting and comparisons."""
    parts = value.strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"start_time must be HH:MM, got {value!r}")
    hour, minute = int(parts[0]), int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"Invalid clock time: {value!r}")
    return f"{hour:02d}:{minute:02d}"


def start_time_to_minutes(hhmm: str) -> int:
    """Return minutes from midnight for a normalized HH:MM string."""
    normalized = _normalize_hhmm(hhmm)
    h, m = normalized.split(":")
    return int(h) * 60 + int(m)


def intervals_overlap_half_open(a0: int, a1: int, b0: int, b1: int) -> bool:
    """True iff [a0, a1) and [b0, b1) overlap (half-open intervals)."""
    return a0 < b1 and b0 < a1


class Task:
    """A single care activity for a pet."""

    def __init__(
        self,
        description: str,
        time_minutes: int,
        frequency: str,
        completed: bool = False,
        due_date: date | None = None,
        start_time: str | None = None,
        task_id: str | None = None,
    ) -> None:
        """Create a task with description, duration, frequency, optional due date and start time."""
        self._description = description
        self._time_minutes = time_minutes
        self._frequency = frequency.strip().lower()
        self._completed = completed
        self._due_date = due_date
        self._start_time = _normalize_hhmm(start_time) if start_time is not None else None
        self._task_id = task_id if task_id is not None else str(uuid.uuid4())

    @property
    def description(self) -> str:
        """Return the task description."""
        return self._description

    @property
    def time_minutes(self) -> int:
        """Return how long the task takes in minutes."""
        return self._time_minutes

    @property
    def frequency(self) -> str:
        """Return how often the task should happen (e.g. daily, weekly)."""
        return self._frequency

    @property
    def completed(self) -> bool:
        """Return whether the task is marked done."""
        return self._completed

    @property
    def due_date(self) -> date | None:
        """Return the calendar day this task is due, if set."""
        return self._due_date

    @property
    def start_time(self) -> str | None:
        """Return scheduled start as HH:MM, or None if not yet placed on a clock."""
        return self._start_time

    @property
    def task_id(self) -> str:
        """Stable id for persistence (UUID string)."""
        return self._task_id

    def mark_complete(self) -> None:
        """Mark this task as completed."""
        self._completed = True

    def set_start_time(self, value: str | None) -> None:
        """Set/clear start time with HH:MM normalization when provided."""
        self._start_time = _normalize_hhmm(value) if value is not None else None


def task_day_interval_minutes(task: Task) -> tuple[int, int]:
    """
    Return [start, end) in minutes from midnight for the task's clock window.
    Raises ValueError if the window extends past 24:00 (not supported for overlap checks).
    """
    if task.start_time is None:
        raise ValueError("Task has no start_time.")
    start_m = start_time_to_minutes(task.start_time)
    end_m = start_m + int(task.time_minutes)
    if end_m > 24 * 60:
        raise ValueError(
            "Task start time plus duration extends past midnight; shorten the task or start earlier."
        )
    return start_m, end_m


class Pet:
    """A pet and the tasks that belong to it."""

    def __init__(self, name: str, species: str) -> None:
        """Create a pet with a name, species, and an empty task list."""
        self._name = name
        self._species = species
        self._tasks: list[Task] = []

    @property
    def name(self) -> str:
        """Return the pet's name."""
        return self._name

    @property
    def species(self) -> str:
        """Return the pet's species."""
        return self._species

    @property
    def tasks(self) -> list[Task]:
        """Return a shallow copy of this pet's tasks."""
        return list(self._tasks)

    def add_task(self, task: Task) -> None:
        """Append a task to this pet's list."""
        self._tasks.append(task)

    def complete_task(self, task: Task, *, owner: Owner | None = None) -> None:
        """
        Mark a task done; for daily/weekly, append the next occurrence with an updated due date.
        If owner is provided, skip appending the next occurrence when it would overlap another
        pending task on that owner (same clock-day window).
        """
        if task not in self._tasks:
            return
        freq = task.frequency
        new_task: Task | None = None
        if freq == "daily":
            base = task.due_date if task.due_date is not None else date.today()
            new_due = base + timedelta(days=1)
            new_task = Task(
                task.description,
                task.time_minutes,
                "daily",
                completed=False,
                due_date=new_due,
                start_time=task.start_time,
            )
        elif freq == "weekly":
            base = task.due_date if task.due_date is not None else date.today()
            new_due = base + timedelta(weeks=1)
            new_task = Task(
                task.description,
                task.time_minutes,
                "weekly",
                completed=False,
                due_date=new_due,
                start_time=task.start_time,
            )

        if new_task is not None and owner is not None and new_task.start_time is not None:
            conflict = task_overlaps_any_pending(owner, new_task, ignore_task=task)
            if conflict is not None:
                p2, t2 = conflict
                logger.warning(
                    "Skipping recurrence append for %r: overlaps pending %s/%r at %s-%s min",
                    task.description,
                    p2.name,
                    t2.description,
                    t2.start_time,
                    t2.time_minutes,
                )
                return

        task.mark_complete()
        if new_task is not None:
            self.add_task(new_task)


class Owner:
    """An owner who has one or more pets."""

    def __init__(self, name: str) -> None:
        """Create an owner with a name and no pets yet."""
        self._name = name
        self._pets: list[Pet] = []

    @property
    def name(self) -> str:
        """Return the owner's name."""
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        """Set the owner's name (e.g. when edited in the UI)."""
        self._name = value

    @property
    def pets(self) -> list[Pet]:
        """Return a shallow copy of this owner's pets."""
        return list(self._pets)

    def add_pet(self, pet: Pet) -> None:
        """Register a pet with this owner."""
        self._pets.append(pet)

    def all_tasks(self) -> list[Task]:
        """Return every task from every pet (order follows pet order, then task order)."""
        out: list[Task] = []
        for pet in self._pets:
            out.extend(pet.tasks)
        return out


def pending_task_interval_rows(owner: Owner) -> list[tuple[Pet, Task, int, int]]:
    """List (pet, task, start_min, end_min) for every incomplete task; skips tasks with invalid intervals."""
    rows: list[tuple[Pet, Task, int, int]] = []
    for pet in owner.pets:
        for task in pet.tasks:
            if task.completed:
                continue
            if task.start_time is None:
                continue
            try:
                a, b = task_day_interval_minutes(task)
            except ValueError:
                continue
            rows.append((pet, task, a, b))
    return rows


def task_overlaps_any_pending(
    owner: Owner,
    candidate: Task,
    *,
    ignore_task: Task | None = None,
) -> tuple[Pet, Task] | None:
    """
    If candidate's interval overlaps any incomplete task on the owner (any pet), return
    the first conflicting (pet, task); otherwise None.
    """
    try:
        c0, c1 = task_day_interval_minutes(candidate)
    except ValueError:
        return None
    for pet, task, t0, t1 in pending_task_interval_rows(owner):
        if ignore_task is not None and task is ignore_task:
            continue
        if candidate is task:
            continue
        if intervals_overlap_half_open(c0, c1, t0, t1):
            return pet, task
    return None


def validate_proposed_schedule(
    owner: Owner,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Validate AI schedule proposals against pending tasks.

    Rules:
    - Every pending incomplete task id appears exactly once.
    - Every proposed row has valid HH:MM and non-overlapping [start, start+duration).
    - Rows are normalized and returned sorted by order, then start_time.
    """
    pending_pairs = [
        (pet, task)
        for pet in owner.pets
        for task in pet.tasks
        if not task.completed
    ]
    expected_ids = {task.task_id for _, task in pending_pairs}
    by_id = {task.task_id: (pet, task) for pet, task in pending_pairs}

    seen_ids: set[str] = set()
    normalized: list[dict[str, Any]] = []
    intervals: list[tuple[str, int, int, str]] = []

    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"Invalid proposal row at index {idx}: expected object.")
        task_id = str(row.get("task_id", "")).strip()
        if not task_id:
            raise ValueError(f"Missing task_id at proposal row {idx}.")
        if task_id not in expected_ids:
            raise ValueError(f"Unknown task_id in proposal: {task_id}.")
        if task_id in seen_ids:
            raise ValueError(f"Duplicate task_id in proposal: {task_id}.")
        seen_ids.add(task_id)

        start_time_raw = row.get("start_time")
        if not isinstance(start_time_raw, str) or not start_time_raw.strip():
            raise ValueError(f"Missing/invalid start_time for task_id {task_id}.")
        start_time = _normalize_hhmm(start_time_raw)

        pet, task = by_id[task_id]
        scheduled = Task(
            task.description,
            task.time_minutes,
            task.frequency,
            completed=False,
            due_date=task.due_date,
            start_time=start_time,
            task_id=task.task_id,
        )
        a0, a1 = task_day_interval_minutes(scheduled)
        intervals.append((task_id, a0, a1, task.description))

        cited_ids = row.get("cited_ids") or []
        if isinstance(cited_ids, str):
            cited_ids = [cited_ids]
        reason = str(row.get("reason", "")).strip()
        order_raw = row.get("order", idx + 1)
        try:
            order = int(order_raw)
        except (TypeError, ValueError):
            order = idx + 1

        normalized.append(
            {
                "task_id": task_id,
                "start_time": start_time,
                "order": order,
                "reason": reason,
                "cited_ids": [str(x) for x in cited_ids if str(x).strip()],
                "pet": pet.name,
                "species": pet.species,
                "task": task.description,
                "time_minutes": task.time_minutes,
                "frequency": task.frequency,
            }
        )

    if seen_ids != expected_ids:
        missing = sorted(expected_ids - seen_ids)
        extra = sorted(seen_ids - expected_ids)
        raise ValueError(f"Proposal task_id set mismatch. Missing={missing}, extra={extra}.")

    for i in range(len(intervals)):
        for j in range(i + 1, len(intervals)):
            id_a, a0, a1, desc_a = intervals[i]
            id_b, b0, b1, desc_b = intervals[j]
            if intervals_overlap_half_open(a0, a1, b0, b1):
                raise ValueError(
                    f"Overlapping proposal windows: {id_a} ({desc_a}) and {id_b} ({desc_b})."
                )

    return sorted(normalized, key=lambda r: (int(r["order"]), str(r["start_time"]), str(r["task_id"])))


class DailyPlan:
    """An ordered schedule for one run of the scheduler."""

    @dataclass(frozen=True)
    class PlanSlot:
        """One row in the schedule: pet, task, order, and explanation."""

        order: int
        pet: Pet
        task: Task
        explanation: str

        def get_order(self) -> int:
            """Return the step number in today's schedule."""
            return self.order

        def get_pet(self) -> Pet:
            """Return the pet this slot belongs to."""
            return self.pet

        def get_task(self) -> Task:
            """Return the scheduled task."""
            return self.task

        def get_explanation(self) -> str:
            """Return why this task was placed here."""
            return self.explanation

    def __init__(self, slots: list[PlanSlot]) -> None:
        """Build a plan from an ordered list of slots."""
        self._slots = list(slots)

    @property
    def slots(self) -> list[DailyPlan.PlanSlot]:
        """Return a copy of the schedule slots."""
        return list(self._slots)


class Scheduler:
    """Collects tasks from an owner's pets and builds an ordered daily plan."""

    _FREQUENCY_RANK: dict[str, int] = {"daily": 3, "weekly": 2, "once": 1}

    def __init__(self) -> None:
        """Create a scheduler with no internal state."""
        pass

    @staticmethod
    def _hhmm_sort_key(task: Task) -> tuple[int, int]:
        """Sort key for optional HH:MM strings; unscheduled tasks sort last."""
        if task.start_time is None:
            return (24, 0)
        h, m = task.start_time.split(":")
        return (int(h), int(m))

    def sort_by_time(self, tasks: list[Task]) -> list[Task]:
        """Return tasks ordered by scheduled start time (HH:MM), earliest first."""
        return sorted(tasks, key=self._hhmm_sort_key)

    def filter_tasks(
        self,
        owner: Owner,
        *,
        completed: bool | None = None,
        pet_name: str | None = None,
    ) -> list[tuple[Pet, Task]]:
        """Return (pet, task) pairs matching optional completion and pet name filters."""
        out: list[tuple[Pet, Task]] = []
        name_needle = pet_name.strip().lower() if pet_name is not None else None
        for pet in owner.pets:
            if name_needle is not None and pet.name.lower() != name_needle:
                continue
            for task in pet.tasks:
                if completed is not None and task.completed != completed:
                    continue
                out.append((pet, task))
        return out

    def schedule_time_conflicts(self, owner: Owner) -> list[str]:
        """
        Warn when two or more incomplete tasks have overlapping clock windows [start, start+duration)
        on the same calendar day model (minutes from midnight; tasks must not extend past midnight).
        """
        rows = pending_task_interval_rows(owner)
        n = len(rows)
        if n <= 1:
            return []

        parent = list(range(n))

        def find(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(i: int, j: int) -> None:
            ri, rj = find(i), find(j)
            if ri != rj:
                parent[ri] = rj

        for i in range(n):
            for j in range(i + 1, n):
                _, _, a0, a1 = rows[i]
                _, _, b0, b1 = rows[j]
                if intervals_overlap_half_open(a0, a1, b0, b1):
                    union(i, j)

        groups: dict[int, list[int]] = defaultdict(list)
        for i in range(n):
            groups[find(i)].append(i)

        warnings: list[str] = []
        for idxs in groups.values():
            if len(idxs) <= 1:
                continue
            parts: list[str] = []
            for i in idxs:
                pet, task, t0, t1 = rows[i]
                h0, m0 = divmod(t0, 60)
                h1, m1 = divmod(t1, 60)
                parts.append(
                    f"{pet.name}: {task.description} "
                    f"({task.start_time}–{h1:02d}:{m1:02d}, {task.time_minutes} min)"
                )
            detail = "; ".join(sorted(parts))
            warnings.append(
                f"Overlap: {len(idxs)} pending tasks share clock time — {detail}. "
                "Change a start time or duration so only one activity runs at a time."
            )
        return warnings

    def build_plan(self, owner: Owner) -> DailyPlan:
        """Gather incomplete tasks from all pets, sort them, and attach explanations."""
        pairs: list[tuple[Pet, Task]] = []
        for pet in owner.pets:
            for task in pet.tasks:
                if not task.completed:
                    pairs.append((pet, task))

        if not pairs:
            return DailyPlan([])

        ordered = sorted(
            pairs,
            key=lambda pt: (
                -self._frequency_rank(pt[1].frequency),
                pt[1].time_minutes,
                pt[0].name.lower(),
                pt[1].description.lower(),
            ),
        )

        slots: list[DailyPlan.PlanSlot] = []
        for index, (pet, task) in enumerate(ordered, start=1):
            explanation = self._explain_slot(
                index, owner, pet, task, ordered, len(ordered)
            )
            slots.append(DailyPlan.PlanSlot(index, pet, task, explanation))
        return DailyPlan(slots)

    def _frequency_rank(self, frequency: str) -> int:
        """Map a frequency label to a sortable rank (higher = earlier in the day)."""
        return self._FREQUENCY_RANK.get(frequency.strip().lower(), 0)

    def _explain_slot(
        self,
        order: int,
        owner: Owner,
        pet: Pet,
        task: Task,
        ordered_pairs: list[tuple[Pet, Task]],
        total: int,
    ) -> str:
        """Build a short human-readable reason for this slot."""
        label = task.frequency.capitalize()
        duration = task.time_minutes
        prev = ordered_pairs[order - 2] if order > 1 else None

        base = (
            f'Step {order}/{total}: "{task.description}" ({duration} min, {label}) '
            f"for {pet.name} ({pet.species})."
        )
        if order == 1:
            reason = (
                "Scheduled first: highest recurring importance among pending tasks "
                "(ties: shorter time first, then pet name, then description)."
            )
        else:
            assert prev is not None
            prev_pet, prev_task = prev
            r = self._frequency_rank(task.frequency)
            r_prev = self._frequency_rank(prev_task.frequency)
            if r == r_prev and pet is prev_pet:
                reason = (
                    "Same frequency and pet as the previous step; shorter tasks are listed first."
                )
            elif r == r_prev:
                reason = (
                    "Same frequency tier; ordered by time, then pet name, to balance care across pets."
                )
            else:
                reason = (
                    "Lower frequency tier than earlier steps, so it comes after more recurring care."
                )

        return f"{base} {reason} Planned for {owner.name}."
