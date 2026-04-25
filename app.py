import streamlit as st

from pawpal_system import Owner, Pet, Scheduler, Task

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")

st.title("🐾 PawPal+")

# Stateless: safe to create each run; encapsulates sorting, filtering, and conflict checks.
sched = Scheduler()

# --- Session state: Owner persists across reruns (Streamlit reruns the script on each interaction) ---
if "owner" not in st.session_state:
    st.session_state.owner = Owner("Jordan")

owner: Owner = st.session_state.owner

st.markdown(
    """
Welcome to **PawPal+**. Your owner and pets live in `st.session_state` so they are not reset on every click.
"""
)

with st.expander("Scenario", expanded=False):
    st.markdown(
        """
**PawPal+** is a pet care planning assistant. It helps a pet owner plan care tasks
for their pet(s) based on constraints like time, priority, and preferences.
"""
    )

with st.expander("What this app does", expanded=False):
    st.markdown(
        """
- **Owner** is stored once in `st.session_state["owner"]` (checked with `in` before creating).
- **Add pet** calls `Owner.add_pet(Pet(...))`.
- **Add task** calls `Pet.add_task(Task(...))` on the pet you pick.
- **Scheduler** uses `sort_by_time`, `filter_tasks`, `schedule_time_conflicts`, and `build_plan(owner)` on the same owner object.
"""
    )

st.divider()

st.subheader("Owner")
owner_name = st.text_input("Owner name", value=owner.name, key="owner_name_input")
if owner_name.strip():
    owner.name = owner_name.strip()

st.subheader("Pets")
col_pet_a, col_pet_b, col_pet_c = st.columns(3)
with col_pet_a:
    new_pet_name = st.text_input("Pet name", value="Mochi", key="new_pet_name")
with col_pet_b:
    new_pet_species = st.selectbox("Species", ["dog", "cat", "other"], key="new_pet_species")
with col_pet_c:
    st.write("")  # align button with inputs
    st.write("")
    add_pet_clicked = st.button("Add pet", type="primary")

if add_pet_clicked:
    if not new_pet_name.strip():
        st.warning("Enter a pet name.")
    else:
        owner.add_pet(Pet(new_pet_name.strip(), new_pet_species))
        st.success(f"Added **{new_pet_name.strip()}** ({new_pet_species}).")

# Placeholder so the summary runs after "Add task" (Streamlit executes top-to-bottom; otherwise task counts lag one click).
if owner.pets:
    pet_summary_placeholder = st.empty()
else:
    pet_summary_placeholder = None
    st.info("No pets yet. Add one above.")

st.divider()

st.subheader("Tasks (schedule on a pet)")
st.caption("Choose a pet, then add tasks. Tasks store a **start time** for sorting and overlap checks.")

if not owner.pets:
    st.warning("Add at least one pet before scheduling tasks.")
else:
    pet_labels = [f"{p.name} ({p.species})" for p in owner.pets]
    pet_index = st.selectbox("Pet", range(len(owner.pets)), format_func=lambda i: pet_labels[i])

    c1, c2 = st.columns(2)
    with c1:
        task_desc = st.text_input("Task description", value="Morning walk", key="task_desc")
    with c2:
        duration = st.number_input("Time (minutes)", min_value=1, max_value=240, value=20, key="task_duration")

    c3, c4 = st.columns(2)
    with c3:
        frequency = st.selectbox("Frequency", ["daily", "weekly", "once"], index=0, key="task_freq")
    with c4:
        start_time_input = st.text_input(
            "Start time (HH:MM)",
            value="09:00",
            help="Used to sort pending tasks and detect multiple tasks at the same clock time.",
            key="task_start_time",
        )

    if st.button("Add task"):
        pet = owner.pets[pet_index]
        try:
            pet.add_task(
                Task(
                    description=task_desc,
                    time_minutes=int(duration),
                    frequency=frequency,
                    start_time=start_time_input.strip() or "09:00",
                )
            )
            st.success(f"Task added for **{pet.name}**.")
        except ValueError as e:
            st.error(f"Invalid start time: {e}")

    # Show tasks grouped by pet (raw order on each pet)
    for p in owner.pets:
        if p.tasks:
            st.markdown(f"**{p.name}** — {len(p.tasks)} task(s)")
            st.table(
                [
                    {
                        "Start": t.start_time,
                        "Description": t.description,
                        "Minutes": t.time_minutes,
                        "Frequency": t.frequency,
                        "Done": t.completed,
                    }
                    for t in p.tasks
                ]
            )

if pet_summary_placeholder is not None:
    pet_rows = [{"Name": p.name, "Species": p.species, "Tasks": len(p.tasks)} for p in owner.pets]
    pet_summary_placeholder.dataframe(pet_rows, use_container_width=True, hide_index=True)

st.divider()

# --- Algorithmic layer: conflicts + sorted / filtered pending tasks ---
if owner.pets and owner.all_tasks():
    st.subheader("Scheduling insights")
    st.caption("Uses `Scheduler.schedule_time_conflicts`, `filter_tasks`, and `sort_by_time`.")

    conflicts = sched.schedule_time_conflicts(owner)
    if conflicts:
        st.warning(
            "**Time overlap:** More than one unfinished task is set for the same clock time. "
            "You can only do one thing at a time—adjust a **start time** above, or use the generated "
            "plan below to decide what to do first."
        )
        with st.expander("Which tasks overlap?", expanded=True):
            st.table([{"Detail": msg} for msg in conflicts])
    else:
        pending = sched.filter_tasks(owner, completed=False)
        if pending:
            st.success("No overlapping start times among **pending** tasks.")

    filter_label = st.selectbox(
        "Pending tasks — filter by pet",
        ["All pets"] + [p.name for p in owner.pets],
        key="pending_filter_pet",
    )
    if filter_label == "All pets":
        pairs = sched.filter_tasks(owner, completed=False)
    else:
        pairs = sched.filter_tasks(owner, completed=False, pet_name=filter_label)

    if pairs:
        sorted_pairs = sorted(
            pairs,
            key=lambda pt: tuple(int(x) for x in pt[1].start_time.split(":")),
        )
        st.markdown("**Pending tasks sorted by start time** (earliest first)")
        st.table(
            [
                {
                    "Start": task.start_time,
                    "Pet": pet.name,
                    "Task": task.description,
                    "Minutes": task.time_minutes,
                    "Frequency": task.frequency,
                }
                for pet, task in sorted_pairs
            ]
        )
    else:
        st.info("No pending tasks for this filter (all may be completed).")

st.divider()

st.subheader("Build schedule")
st.caption("Runs `Scheduler.build_plan(owner)` on your session owner and all pets/tasks.")

if st.button("Generate schedule"):
    if not owner.pets:
        st.warning("Add at least one pet first.")
    elif not owner.all_tasks():
        st.warning("Add at least one task to a pet before generating a schedule.")
    else:
        plan = sched.build_plan(owner)
        if not plan.slots:
            st.info("No pending tasks (all may be completed).")
        else:
            st.success(
                f"Schedule for **{owner.name}** — {len(owner.pets)} pet(s), "
                f"{len(plan.slots)} step(s). Order follows recurring priority, then duration and names."
            )
            rows = []
            for slot in plan.slots:
                t = slot.get_task()
                p = slot.get_pet()
                rows.append(
                    {
                        "Order": slot.get_order(),
                        "Start": t.start_time,
                        "Pet": p.name,
                        "Task": t.description,
                        "Minutes": t.time_minutes,
                        "Frequency": t.frequency,
                        "Done": t.completed,
                        "Why": slot.get_explanation(),
                    }
                )
            st.dataframe(rows, use_container_width=True, hide_index=True)
