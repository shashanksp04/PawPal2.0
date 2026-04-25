"""Tests for pawpal_system.Task, Pet, Owner, DailyPlan, and Scheduler."""

from datetime import date

from pawpal_system import DailyPlan, Owner, Pet, Scheduler, Task


def test_mark_complete_changes_status() -> None:
    task = Task("Brush fur", 15, "daily", completed=False)
    assert task.completed is False
    task.mark_complete()
    assert task.completed is True


def test_add_task_increases_pet_task_count() -> None:
    pet = Pet("Mochi", "dog")
    assert len(pet.tasks) == 0
    pet.add_task(Task("Walk", 20, "daily"))
    assert len(pet.tasks) == 1
    pet.add_task(Task("Feed", 5, "daily"))
    assert len(pet.tasks) == 2


# --- Sorting (chronological by clock time via sort_by_time) ---


def test_sort_by_time_returns_chronological_order() -> None:
    """Tasks with different start_time values sort earliest HH:MM first."""
    sched = Scheduler()
    tasks = [
        Task("late", 10, "daily", start_time="18:00"),
        Task("early", 10, "daily", start_time="07:15"),
        Task("mid", 10, "daily", start_time="12:00"),
    ]
    ordered = sched.sort_by_time(tasks)
    assert [t.description for t in ordered] == ["early", "mid", "late"]


def test_sort_by_time_normalizes_unpadded_hours() -> None:
    """9:00 and 09:00 compare equal for ordering; tie-break is stable sort."""
    sched = Scheduler()
    a = Task("a", 1, "once", start_time="9:00")
    b = Task("b", 1, "once", start_time="09:00")
    c = Task("c", 1, "once", start_time="10:00")
    ordered = sched.sort_by_time([c, a, b])
    assert [t.start_time for t in ordered[:2]] == ["09:00", "09:00"]
    assert ordered[2].start_time == "10:00"


def test_sort_by_time_empty_list() -> None:
    assert Scheduler().sort_by_time([]) == []


# --- Recurrence (complete_task → next occurrence) ---


def test_complete_daily_task_creates_next_day_task() -> None:
    """Marking a daily task done appends a new incomplete task for the following day."""
    base = date(2026, 3, 10)
    pet = Pet("Mochi", "dog")
    t = Task("Morning walk", 20, "daily", completed=False, due_date=base, start_time="08:00")
    pet.add_task(t)
    pet.complete_task(t)

    assert t.completed is True
    assert len(pet.tasks) == 2
    next_tasks = [x for x in pet.tasks if not x.completed]
    assert len(next_tasks) == 1
    nxt = next_tasks[0]
    assert nxt.description == "Morning walk"
    assert nxt.frequency == "daily"
    assert nxt.due_date == date(2026, 3, 11)
    assert nxt.start_time == "08:00"


def test_complete_weekly_task_creates_next_week_task() -> None:
    base = date(2026, 3, 1)
    pet = Pet("Luna", "cat")
    t = Task("Grooming", 45, "weekly", due_date=base, start_time="14:00")
    pet.add_task(t)
    pet.complete_task(t)

    nxt = next(x for x in pet.tasks if not x.completed)
    assert nxt.due_date == date(2026, 3, 8)
    assert nxt.frequency == "weekly"


def test_complete_once_task_does_not_append_new_task() -> None:
    pet = Pet("X", "dog")
    t = Task("Vaccine", 30, "once")
    pet.add_task(t)
    pet.complete_task(t)
    assert len(pet.tasks) == 1
    assert t.completed is True


def test_complete_task_unknown_pet_task_is_noop() -> None:
    pet = Pet("P", "dog")
    t = Task("Walk", 5, "daily")
    pet.complete_task(t)  # t not in pet.tasks
    assert len(pet.tasks) == 0
    assert not t.completed


# --- Conflict detection (same start_time) ---


def test_schedule_time_conflicts_flags_duplicate_times() -> None:
    """Two incomplete tasks at the same HH:MM produce one conflict warning."""
    pet = Pet("Mochi", "dog")
    pet.add_task(Task("Feed", 5, "daily", start_time="09:00"))
    pet.add_task(Task("Meds", 2, "daily", start_time="09:00"))
    owner = Owner("Alex")
    owner.add_pet(pet)

    warnings = Scheduler().schedule_time_conflicts(owner)
    assert len(warnings) == 1
    assert "Conflict" in warnings[0]
    assert "09:00" in warnings[0]
    assert "Feed" in warnings[0] and "Meds" in warnings[0]


def test_schedule_time_conflicts_same_time_across_two_pets() -> None:
    p1 = Pet("A", "dog")
    p2 = Pet("B", "cat")
    p1.add_task(Task("Walk", 10, "daily", start_time="07:00"))
    p2.add_task(Task("Breakfast", 5, "daily", start_time="07:00"))
    owner = Owner("O")
    owner.add_pet(p1)
    owner.add_pet(p2)

    warnings = Scheduler().schedule_time_conflicts(owner)
    assert len(warnings) == 1
    assert "A: Walk" in warnings[0] and "B: Breakfast" in warnings[0]


def test_schedule_time_conflicts_no_warning_when_times_differ() -> None:
    pet = Pet("P", "dog")
    pet.add_task(Task("a", 1, "daily", start_time="08:00"))
    pet.add_task(Task("b", 1, "daily", start_time="08:01"))
    owner = Owner("O")
    owner.add_pet(pet)
    assert Scheduler().schedule_time_conflicts(owner) == []


def test_schedule_time_conflicts_ignores_completed_tasks() -> None:
    pet = Pet("P", "dog")
    t1 = Task("a", 1, "daily", start_time="12:00")
    t2 = Task("b", 1, "daily", start_time="12:00")
    t2.mark_complete()
    pet.add_task(t1)
    pet.add_task(t2)
    owner = Owner("O")
    owner.add_pet(pet)
    assert Scheduler().schedule_time_conflicts(owner) == []


# --- Edge cases ---


def test_pet_with_no_tasks_yields_empty_plan() -> None:
    owner = Owner("O")
    owner.add_pet(Pet("Solo", "bird"))
    plan = Scheduler().build_plan(owner)
    assert plan.slots == []


def test_two_tasks_same_start_time_both_appear_in_plan_with_conflict_warning() -> None:
    """Same-time tasks still schedule; conflicts are reported separately."""
    pet = Pet("P", "dog")
    pet.add_task(Task("First", 5, "daily", start_time="10:00"))
    pet.add_task(Task("Second", 5, "daily", start_time="10:00"))
    owner = Owner("O")
    owner.add_pet(pet)
    sched = Scheduler()
    plan = sched.build_plan(owner)
    assert len(plan.slots) == 2
    assert len(sched.schedule_time_conflicts(owner)) == 1


# --- Pressure / stress ---


def test_many_tasks_single_pet_orders_by_frequency_then_time() -> None:
    pet = Pet("Stress", "dog")
    for i in range(120):
        pet.add_task(Task(f"task-{i:03d}", time_minutes=(i % 60) + 1, frequency="once"))
    pet.add_task(Task("daily-short", 1, "daily"))
    pet.add_task(Task("weekly-mid", 30, "weekly"))

    owner = Owner("O")
    owner.add_pet(pet)
    plan = Scheduler().build_plan(owner)

    assert len(plan.slots) == 122
    first = plan.slots[0].get_task()
    assert first.description == "daily-short"
    assert first.frequency == "daily"
    # All slot orders unique and sequential
    orders = [s.get_order() for s in plan.slots]
    assert orders == list(range(1, 123))


def test_many_pets_many_tasks_all_included() -> None:
    owner = Owner("Multi")
    n_pets = 25
    tasks_per = 8
    for p in range(n_pets):
        pet = Pet(f"Pet{p}", "cat" if p % 2 else "dog")
        for t in range(tasks_per):
            pet.add_task(Task(f"P{p}-T{t}", 5 + t, "daily"))
        owner.add_pet(pet)

    plan = Scheduler().build_plan(owner)
    assert len(plan.slots) == n_pets * tasks_per
    seen = {(s.get_pet().name, s.get_task().description) for s in plan.slots}
    assert len(seen) == n_pets * tasks_per


def test_owner_all_tasks_matches_flattened_count() -> None:
    owner = Owner("Alex")
    for i in range(15):
        p = Pet(f"P{i}", "other")
        for j in range(20):
            p.add_task(Task(f"job-{i}-{j}", 10, "weekly"))
        owner.add_pet(p)
    assert len(owner.all_tasks()) == 15 * 20


def test_scheduler_ignores_completed_tasks_only() -> None:
    pet = Pet("Mochi", "dog")
    for i in range(50):
        t = Task(f"open-{i}", 10, "daily")
        if i % 3 == 0:
            t.mark_complete()
        pet.add_task(t)
    owner = Owner("O")
    owner.add_pet(pet)
    plan = Scheduler().build_plan(owner)
    expected_pending = sum(1 for i in range(50) if i % 3 != 0)
    assert len(plan.slots) == expected_pending
    assert all(not s.get_task().completed for s in plan.slots)


def test_all_tasks_completed_yields_empty_plan() -> None:
    pet = Pet("X", "cat")
    for i in range(100):
        t = Task(f"t{i}", 1, "daily")
        t.mark_complete()
        pet.add_task(t)
    owner = Owner("O")
    owner.add_pet(pet)
    assert Scheduler().build_plan(owner).slots == []


def test_daily_plan_slots_copy_is_isolated() -> None:
    pet = Pet("P", "dog")
    pet.add_task(Task("a", 1, "daily"))
    owner = Owner("O")
    owner.add_pet(pet)
    plan = Scheduler().build_plan(owner)
    slots = plan.slots
    slots.append(plan.slots[0])
    assert len(plan.slots) == 1


def test_pet_tasks_copy_is_isolated() -> None:
    pet = Pet("P", "dog")
    pet.add_task(Task("a", 1, "daily"))
    tasks = pet.tasks
    tasks.append(Task("b", 2, "once"))
    assert len(pet.tasks) == 1


def test_unknown_frequency_sorts_after_once() -> None:
    pet = Pet("P", "dog")
    pet.add_task(Task("once", 1, "once"))
    pet.add_task(Task("weird", 1, "adhoc"))
    owner = Owner("O")
    owner.add_pet(pet)
    plan = Scheduler().build_plan(owner)
    titles = [s.get_task().description for s in plan.slots]
    assert titles[0] == "once"
    assert titles[1] == "weird"


def test_scheduler_stable_under_repeated_builds() -> None:
    owner = Owner("O")
    p = Pet("M", "dog")
    for i in range(30):
        p.add_task(Task(f"x{i}", (i * 7) % 120 + 1, ["daily", "weekly", "once"][i % 3]))
    owner.add_pet(p)
    s = Scheduler()
    a = [s.get_task().description for s in s.build_plan(owner).slots]
    b = [s.get_task().description for s in s.build_plan(owner).slots]
    assert a == b


def test_filter_tasks_by_pet_and_completed() -> None:
    s = Scheduler()
    owner = Owner("O")
    p1 = Pet("Mochi", "dog")
    p1.add_task(Task("open", 5, "daily"))
    done = Task("done", 1, "once")
    done.mark_complete()
    p1.add_task(done)
    owner.add_pet(p1)
    pending = s.filter_tasks(owner, completed=False)
    assert len(pending) == 1 and pending[0][1].description == "open"
    mochi_only = s.filter_tasks(owner, pet_name="Mochi")
    assert len(mochi_only) == 2


def test_high_volume_plan_under_one_second() -> None:
    import time

    owner = Owner("Bench")
    p = Pet("Big", "dog")
    for i in range(2000):
        p.add_task(Task(f"t{i}", 1 + (i % 90), "daily"))
    owner.add_pet(p)
    t0 = time.perf_counter()
    plan = Scheduler().build_plan(owner)
    elapsed = time.perf_counter() - t0
    assert len(plan.slots) == 2000
    assert elapsed < 1.0, f"build_plan took {elapsed:.2f}s"
