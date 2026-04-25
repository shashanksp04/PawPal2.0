import logging
import os

import streamlit as st

from gemini_client import explain_schedule_with_rag
from pawpal_rag import retrieve_for_schedule_context
from pawpal_store import (
    TaskOverlapError,
    TaskValidationError,
    default_store_path,
    ensure_default_store,
    load_owner,
    save_owner,
    try_add_task,
)
from pawpal_system import Owner, Pet, Scheduler, Task

logging.basicConfig(level=logging.INFO)

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")

st.title("🐾 PawPal+")

# Stateless: safe to create each run; encapsulates sorting, filtering, and conflict checks.
sched = Scheduler()

# --- Session state + JSON store (single user) ---
if "owner" not in st.session_state:
    loaded = load_owner()
    st.session_state.owner = loaded if loaded is not None else ensure_default_store()

owner: Owner = st.session_state.owner

st.markdown(
    """
Welcome to **PawPal+**. Your owner and pets are loaded from **`data/pawpal_store.json`** when the app starts
and saved after changes.
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
- **Owner** is stored in `st.session_state["owner"]` and persisted to `data/pawpal_store.json`.
- **Add pet** calls `Owner.add_pet(Pet(...))` then saves the file.
- **Add task** uses `try_add_task` (validates and blocks **overlapping** times across all pets) then saves.
- **Scheduler** uses `sort_by_time`, `filter_tasks`, `schedule_time_conflicts`, and `build_plan(owner)` on the same owner object.
"""
    )

st.divider()

st.subheader("Owner")
owner_name = st.text_input("Owner name", value=owner.name, key="owner_name_input")
if owner_name.strip():
    new_name = owner_name.strip()
    if new_name != owner.name:
        owner.name = new_name
        save_owner(owner)

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
        save_owner(owner)
        st.success(f"Added **{new_pet_name.strip()}** ({new_pet_species}).")

# Placeholder so the summary runs after "Add task" (Streamlit executes top-to-bottom; otherwise task counts lag one click).
if owner.pets:
    pet_summary_placeholder = st.empty()
else:
    pet_summary_placeholder = None
    st.info("No pets yet. Add one above.")

st.divider()

st.subheader("Tasks (schedule on a pet)")
st.caption(
    "Choose a pet, then add tasks. A new task is rejected if its time window overlaps any pending task "
    "(any pet). Store: `%s`."
    % default_store_path().as_posix()
)

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
            help="Used for sorting and overlap detection ([start, start + duration) vs other pending tasks).",
            key="task_start_time",
        )

    if st.button("Add task"):
        pet = owner.pets[pet_index]
        try:
            new_task = Task(
                description=task_desc,
                time_minutes=int(duration),
                frequency=frequency,
                start_time=start_time_input.strip() or "09:00",
            )
            try_add_task(owner, pet, new_task)
            save_owner(owner)
            st.success(f"Task added for **{pet.name}**.")
        except ValueError as e:
            st.error(f"Invalid start time: {e}")
        except TaskOverlapError as e:
            st.error(str(e))
        except TaskValidationError as e:
            st.error(str(e))

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
    st.caption("Uses `Scheduler.schedule_time_conflicts` (overlapping time windows), `filter_tasks`, and `sort_by_time`.")

    conflicts = sched.schedule_time_conflicts(owner)
    if conflicts:
        st.warning(
            "**Time overlap:** Two or more unfinished tasks have overlapping time windows. "
            "Adjust a **start time** or **duration**, or use the generated plan below to decide what to do first."
        )
        with st.expander("Which tasks overlap?", expanded=True):
            st.table([{"Detail": msg} for msg in conflicts])
    else:
        pending = sched.filter_tasks(owner, completed=False)
        if pending:
            st.success("No overlapping time windows among **pending** tasks.")

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
            slot_lines: list[str] = []
            species_list: list[str] = []
            slots_payload: list[dict] = []
            for slot in plan.slots:
                t = slot.get_task()
                p = slot.get_pet()
                species_list.append(p.species)
                slot_lines.append(
                    f"{slot.get_order()}. {p.name} ({p.species}) {t.description} "
                    f"@ {t.start_time} {t.time_minutes}m {t.frequency}"
                )
                slots_payload.append(
                    {
                        "order": slot.get_order(),
                        "pet": p.name,
                        "species": p.species,
                        "task": t.description,
                        "start": t.start_time,
                        "minutes": t.time_minutes,
                        "frequency": t.frequency,
                        "code_why": slot.get_explanation(),
                    }
                )

            kb_chunks = retrieve_for_schedule_context(
                owner_name=owner.name,
                slot_lines=slot_lines,
                species_list=sorted(set(species_list)),
                top_k=5,
            )
            kb_ids = [str(c.get("id")) for c in kb_chunks]
            logging.getLogger(__name__).info("RAG retrieved knowledge ids: %s", kb_ids)

            ai_items = explain_schedule_with_rag(
                owner_name=owner.name,
                slots_payload=slots_payload,
                knowledge_chunks=kb_chunks,
                api_key=os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"),
            )
            by_order: dict[int, dict] = {}
            if ai_items:
                for row in ai_items:
                    by_order[int(row["order"])] = row
            else:
                st.caption(
                    "AI explanation: skipped (set **GOOGLE_API_KEY** or **GEMINI_API_KEY**, "
                    "and `pip install google-generativeai`). Showing **Why (code)** only."
                )

            rows = []
            for slot in plan.slots:
                t = slot.get_task()
                p = slot.get_pet()
                o = slot.get_order()
                ai_row = by_order.get(o)
                ai_why = (ai_row or {}).get("ai_why") or ""
                cited = (ai_row or {}).get("cited_ids") or []
                sources = ", ".join(cited) if cited else ""
                rows.append(
                    {
                        "Order": o,
                        "Start": t.start_time,
                        "Pet": p.name,
                        "Task": t.description,
                        "Minutes": t.time_minutes,
                        "Frequency": t.frequency,
                        "Done": t.completed,
                        "Why (code)": slot.get_explanation(),
                        "AI_Why": ai_why if ai_why else "—",
                        "Sources": sources if sources else "—",
                    }
                )
            st.dataframe(rows, use_container_width=True, hide_index=True)
