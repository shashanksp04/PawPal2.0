"""Terminal demo: sorting, filtering, recurrence, and schedule time conflicts."""

from datetime import date

from pawpal_system import Owner, Pet, Scheduler, Task


def main() -> None:
    owner = Owner("Alex")
    sched = Scheduler()

    mochi = Pet("Mochi", "dog")
    neko = Pet("Neko", "cat")

    # Tasks added out of chronological order (by start_time)
    mochi.add_task(
        Task("Afternoon play", 20, "daily", start_time="15:00", due_date=date.today())
    )
    mochi.add_task(
        Task("Morning walk", 30, "daily", start_time="08:30", due_date=date.today())
    )
    mochi.add_task(Task("Heart medication", 5, "daily", start_time="09:00"))
    neko.add_task(Task("Litter check", 10, "weekly", start_time="12:00"))

    # Same start time on different pets -> conflict warning (lightweight)
    mochi.add_task(Task("Brush coat", 15, "once", start_time="09:00"))
    neko.add_task(Task("Water fountain", 5, "once", start_time="09:00"))

    owner.add_pet(mochi)
    owner.add_pet(neko)

    print("=== Sort by start time (HH:MM) ===")
    all_tasks = [t for _, t in sched.filter_tasks(owner)]
    for t in sched.sort_by_time(all_tasks):
        print(f"  {t.start_time}  {t.description} ({t.time_minutes} min, {t.frequency})")

    print("\n=== Filter: pending tasks for Mochi only ===")
    for pet, task in sched.filter_tasks(owner, completed=False, pet_name="Mochi"):
        print(f"  {pet.name}: {task.description} @ {task.start_time} done={task.completed}")

    print("\n=== Schedule time conflicts (same HH:MM, incomplete tasks) ===")
    conflicts = sched.schedule_time_conflicts(owner)
    if not conflicts:
        print("  (none)")
    for msg in conflicts:
        print(f"  {msg}")

    print("\n=== Complete one daily task -> next occurrence (due date +1 day) ===")
    walk = next(t for t in mochi.tasks if t.description == "Morning walk" and not t.completed)
    print(f"  Before: {len(mochi.tasks)} tasks, completing: {walk.description}")
    mochi.complete_task(walk)
    print(f"  After: {len(mochi.tasks)} tasks")
    new_ones = [t for t in mochi.tasks if not t.completed and t.description == walk.description]
    for t in new_ones:
        print(
            f"  Pending '{t.description}': due {t.due_date}, start {t.start_time}, done={t.completed}"
        )

    print("\n=== Today's Schedule (build_plan) ===")
    plan = sched.build_plan(owner)
    print("=" * 60)
    if not plan.slots:
        print("(No pending tasks.)")
        return

    for slot in plan.slots:
        t = slot.get_task()
        p = slot.get_pet()
        print(f"\n{slot.get_order()}. {p.name} ({p.species}) - {t.description}")
        print(
            f"   Start: {t.start_time}  |  Duration: {t.time_minutes} min  "
            f"|  Frequency: {t.frequency}  |  Done: {t.completed}"
        )
        if t.due_date is not None:
            print(f"   Due: {t.due_date}")
        print(f"   Note: {slot.get_explanation()}")


if __name__ == "__main__":
    main()
