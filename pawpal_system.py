from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta


def _normalize_hhmm(value: str) -> str:
    """Normalize a clock time to zero-padded HH:MM for sorting and comparisons."""
    parts = value.strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"start_time must be HH:MM, got {value!r}")
    hour, minute = int(parts[0]), int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"Invalid clock time: {value!r}")
    return f"{hour:02d}:{minute:02d}"


class Task:
    """A single care activity for a pet."""

    def __init__(
        self,
        description: str,
        time_minutes: int,
        frequency: str,
        completed: bool = False,
        due_date: date | None = None,
        start_time: str = "09:00",
    ) -> None:
        """Create a task with description, duration, frequency, optional due date and start time."""
        self._description = description
        self._time_minutes = time_minutes
        self._frequency = frequency.strip().lower()
        self._completed = completed
        self._due_date = due_date
        self._start_time = _normalize_hhmm(start_time)

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
    def start_time(self) -> str:
        """Return scheduled start of day as HH:MM (used for sorting and conflict checks)."""
        return self._start_time

    def mark_complete(self) -> None:
        """Mark this task as completed."""
        self._completed = True


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

    def complete_task(self, task: Task) -> None:
        """Mark a task done; for daily/weekly, append the next occurrence with an updated due date."""
        if task not in self._tasks:
            return
        task.mark_complete()
        freq = task.frequency
        if freq == "daily":
            base = task.due_date if task.due_date is not None else date.today()
            new_due = base + timedelta(days=1)
            self.add_task(
                Task(
                    task.description,
                    task.time_minutes,
                    "daily",
                    completed=False,
                    due_date=new_due,
                    start_time=task.start_time,
                )
            )
        elif freq == "weekly":
            base = task.due_date if task.due_date is not None else date.today()
            new_due = base + timedelta(weeks=1)
            self.add_task(
                Task(
                    task.description,
                    task.time_minutes,
                    "weekly",
                    completed=False,
                    due_date=new_due,
                    start_time=task.start_time,
                )
            )


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
        """Sort key for normalized HH:MM strings (hour, minute)."""
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
        Lightweight conflict check: warn when two or more incomplete tasks share the same start_time.
        Does not model overlapping durations—only exact same HH:MM.
        """
        by_time: dict[str, list[tuple[Pet, Task]]] = defaultdict(list)
        for pet in owner.pets:
            for task in pet.tasks:
                if task.completed:
                    continue
                by_time[task.start_time].append((pet, task))
        warnings: list[str] = []
        for st, group in sorted(by_time.items()):
            if len(group) <= 1:
                continue
            detail = "; ".join(f"{p.name}: {t.description}" for p, t in group)
            warnings.append(
                f"Conflict: {len(group)} tasks at {st} - {detail}. "
                "Resolve by changing a start time or staggering care."
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
