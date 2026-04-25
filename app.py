import logging
import os
from datetime import date

import streamlit as st

from gemini_client import propose_daily_schedule_with_rag
from pawpal_rag import retrieve_for_schedule_context
from pawpal_store import (
    TaskValidationError,
    default_store_path,
    ensure_default_store,
    load_owner,
    save_owner,
    try_add_task,
)
from pawpal_system import Owner, Pet, Scheduler, Task, validate_proposed_schedule

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")
st.title("🐾 PawPal+")

sched = Scheduler()

if "owner" not in st.session_state:
    loaded = load_owner()
    st.session_state.owner = loaded if loaded is not None else ensure_default_store()
if "proposed_schedule_rows" not in st.session_state:
    st.session_state.proposed_schedule_rows = []
if "proposed_schedule_summary" not in st.session_state:
    st.session_state.proposed_schedule_summary = ""

owner: Owner = st.session_state.owner

st.markdown(
    """
Welcome to **PawPal+**. Add tasks without a start time, then click **Generate schedule**.
Gemini + RAG proposes the day plan, and **Save schedule** writes those times into JSON.
"""
)

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
    st.write("")
    st.write("")
    add_pet_clicked = st.button("Add pet", type="primary")

if add_pet_clicked:
    if not new_pet_name.strip():
        st.warning("Enter a pet name.")
    else:
        owner.add_pet(Pet(new_pet_name.strip(), new_pet_species))
        save_owner(owner)
        st.success(f"Added **{new_pet_name.strip()}** ({new_pet_species}).")

if not owner.pets:
    st.info("No pets yet. Add one above.")

st.divider()

st.subheader("Tasks")
st.caption(
    "Add tasks without start time. AI proposes HH:MM during schedule generation. "
    f"Store: `{default_store_path().as_posix()}`"
)

if not owner.pets:
    st.warning("Add at least one pet before adding tasks.")
else:
    pet_labels = [f"{p.name} ({p.species})" for p in owner.pets]
    pet_index = st.selectbox("Pet", range(len(owner.pets)), format_func=lambda i: pet_labels[i])

    c1, c2 = st.columns(2)
    with c1:
        task_desc = st.text_input("Task description", value="Morning walk", key="task_desc")
    with c2:
        duration = st.number_input("Time (minutes)", min_value=1, max_value=240, value=20, key="task_duration")

    frequency = st.selectbox("Frequency", ["daily", "weekly", "once"], index=0, key="task_freq")

    if st.button("Add task"):
        pet = owner.pets[pet_index]
        try:
            new_task = Task(
                description=task_desc,
                time_minutes=int(duration),
                frequency=frequency,
                start_time=None,
            )
            try_add_task(owner, pet, new_task)
            save_owner(owner)
            st.success(f"Task added for **{pet.name}**.")
        except TaskValidationError as exc:
            st.error(str(exc))

for p in owner.pets:
    if p.tasks:
        st.markdown(f"**{p.name}** — {len(p.tasks)} task(s)")
        st.table(
            [
                {
                    "Start": t.start_time if t.start_time is not None else "Unscheduled",
                    "Description": t.description,
                    "Minutes": t.time_minutes,
                    "Frequency": t.frequency,
                    "Done": t.completed,
                }
                for t in p.tasks
            ]
        )

st.divider()
if owner.pets and owner.all_tasks():
    st.subheader("Scheduling insights")
    conflicts = sched.schedule_time_conflicts(owner)
    if conflicts:
        st.warning("Some already scheduled tasks overlap.")
        st.table([{"Detail": msg} for msg in conflicts])
    else:
        st.success("No overlaps among tasks that currently have a start time.")

st.divider()
st.subheader("Build schedule")
st.caption("Gemini proposes times and reasons; validation enforces no overlaps and full task coverage.")

if st.button("Generate schedule"):
    pending_pairs = [
        (pet, task)
        for pet in owner.pets
        for task in pet.tasks
        if not task.completed
    ]
    if not pending_pairs:
        st.warning("Add at least one pending task first.")
    else:
        tasks_payload = []
        query_lines = []
        species = []
        for pet, task in pending_pairs:
            species.append(pet.species)
            tasks_payload.append(
                {
                    "task_id": task.task_id,
                    "pet": pet.name,
                    "species": pet.species,
                    "description": task.description,
                    "time_minutes": task.time_minutes,
                    "frequency": task.frequency,
                    "due_date": task.due_date.isoformat() if task.due_date is not None else None,
                }
            )
            query_lines.append(f"{pet.species} {task.frequency} task {task.description} {task.time_minutes} min")

        kb_chunks = retrieve_for_schedule_context(
            owner_name=owner.name,
            slot_lines=query_lines,
            species_list=sorted(set(species)),
            top_k=6,
        )
        logger.info("RAG retrieved knowledge ids: %s", [str(c.get("id")) for c in kb_chunks])

        key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        proposal = propose_daily_schedule_with_rag(
            owner_name=owner.name,
            target_date_iso=date.today().isoformat(),
            tasks_payload=tasks_payload,
            knowledge_chunks=kb_chunks,
            api_key=key,
        )
        if proposal is None:
            st.error("Gemini schedule generation failed. Check API key/model and try again.")
        else:
            try:
                validated = validate_proposed_schedule(owner, proposal.get("items", []))
            except ValueError as exc:
                logger.warning("First schedule proposal validation failed: %s", exc)
                retry = propose_daily_schedule_with_rag(
                    owner_name=owner.name,
                    target_date_iso=date.today().isoformat(),
                    tasks_payload=tasks_payload,
                    knowledge_chunks=kb_chunks,
                    api_key=key,
                    repair_feedback=str(exc),
                )
                if retry is None:
                    st.error("Gemini retry failed. Please generate again.")
                    validated = None
                else:
                    try:
                        validated = validate_proposed_schedule(owner, retry.get("items", []))
                        proposal = retry
                    except ValueError as exc2:
                        st.error(f"Gemini proposal failed validation after retry: {exc2}")
                        validated = None
            if validated is not None:
                st.session_state.proposed_schedule_rows = validated
                st.session_state.proposed_schedule_summary = str(proposal.get("plan_summary", "")).strip()
                st.success("Generated AI schedule proposal. Review and click Save schedule.")

rows = st.session_state.proposed_schedule_rows
if rows:
    if st.session_state.proposed_schedule_summary:
        st.markdown(f"**Plan summary:** {st.session_state.proposed_schedule_summary}")
    st.dataframe(
        [
            {
                "Order": r["order"],
                "Start": r["start_time"],
                "Pet": r["pet"],
                "Task": r["task"],
                "Minutes": r["time_minutes"],
                "Frequency": r["frequency"],
                "Reason": r["reason"] if r["reason"] else "—",
                "Sources": ", ".join(r["cited_ids"]) if r["cited_ids"] else "—",
            }
            for r in rows
        ],
        hide_index=True,
        use_container_width=True,
    )

    if st.button("Save schedule", type="primary"):
        task_by_id = {
            task.task_id: task
            for pet in owner.pets
            for task in pet.tasks
        }
        for row in rows:
            task = task_by_id[row["task_id"]]
            task.set_start_time(row["start_time"])
        save_owner(owner)
        st.success("Saved schedule times to JSON store.")
else:
    st.info("No AI schedule proposal yet. Click Generate schedule.")
