import logging
import os
from datetime import date

import streamlit as st

from gemini_client import chat_schedule_assistant_with_rag, propose_daily_schedule_with_rag
from pawpal_rag import retrieve_for_schedule_context
from pawpal_store import (
    TaskValidationError,
    default_store_path,
    ensure_default_store,
    load_owner,
    save_owner,
    try_add_task,
)
from pawpal_system import Owner, Pet, Task, validate_proposed_schedule

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _build_pending_schedule_context(owner: Owner) -> tuple[list[dict[str, object]], list[str], list[str]]:
    tasks_payload: list[dict[str, object]] = []
    query_lines: list[str] = []
    species: list[str] = []
    for pet in owner.pets:
        for task in pet.tasks:
            if task.completed:
                continue
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
    return tasks_payload, query_lines, sorted(set(species))


def _merge_preferences(existing: list[dict[str, str]], incoming: list[dict[str, str]]) -> list[dict[str, str]]:
    merged: dict[str, dict[str, str]] = {}
    for pref in [*existing, *incoming]:
        pref_text = str(pref.get("preference_text", "")).strip()
        if not pref_text:
            continue
        pref_type = str(pref.get("type", "other")).strip().lower() or "other"
        key = f"{pref_type}|{pref_text.lower()}"
        confidence = str(pref.get("confidence", "low")).strip().lower() or "low"
        if confidence not in {"low", "medium", "high"}:
            confidence = "low"
        hard_or_soft = str(pref.get("hard_or_soft", "soft")).strip().lower() or "soft"
        if hard_or_soft not in {"hard", "soft"}:
            hard_or_soft = "soft"
        merged[key] = {
            "preference_text": pref_text,
            "type": pref_type,
            "confidence": confidence,
            "hard_or_soft": hard_or_soft,
            "source_message": str(pref.get("source_message", "")).strip(),
        }
    return list(merged.values())


def _preference_lines(preferences: list[dict[str, str]]) -> list[str]:
    lines: list[str] = []
    for pref in preferences:
        pref_text = str(pref.get("preference_text", "")).strip()
        if not pref_text:
            continue
        hard_or_soft = str(pref.get("hard_or_soft", "soft")).strip().lower() or "soft"
        pref_type = str(pref.get("type", "other")).strip().lower() or "other"
        lines.append(f"{hard_or_soft} {pref_type} preference {pref_text}")
    return lines

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")
st.title("🐾 PawPal+")

if "owner" not in st.session_state:
    loaded = load_owner()
    st.session_state.owner = loaded if loaded is not None else ensure_default_store()
if "proposed_schedule_rows" not in st.session_state:
    st.session_state.proposed_schedule_rows = []
if "proposed_schedule_summary" not in st.session_state:
    st.session_state.proposed_schedule_summary = ""
if "schedule_chat_messages" not in st.session_state:
    st.session_state.schedule_chat_messages = []
if "schedule_preferences" not in st.session_state:
    st.session_state.schedule_preferences = []
if "schedule_chat_summary" not in st.session_state:
    st.session_state.schedule_chat_summary = ""
if "last_applied_preferences" not in st.session_state:
    st.session_state.last_applied_preferences = []
if "last_unapplied_preferences" not in st.session_state:
    st.session_state.last_unapplied_preferences = []
if "reset_schedule_chat_input" not in st.session_state:
    st.session_state.reset_schedule_chat_input = False

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
    st.subheader("Schedule Q&A (optional)")
    st.caption(
        "Ask questions about task timing and share preferences. "
        "Preferences are session-only, stored for future use when generating schedules, and best effort."
    )
    with st.expander("Open schedule chat", expanded=False):
        if st.session_state.reset_schedule_chat_input:
            st.session_state.schedule_chat_input = ""
            st.session_state.reset_schedule_chat_input = False

        if st.button("Clear chat", key="clear_schedule_chat"):
            st.session_state.schedule_chat_messages = []
            st.session_state.schedule_preferences = []
            st.session_state.schedule_chat_summary = ""
            st.success("Cleared session chat and preferences.")

        for msg in st.session_state.schedule_chat_messages:
            role = "You" if msg.get("role") == "user" else "AI"
            st.markdown(f"**{role}:** {str(msg.get('content', '')).strip()}")
        if st.session_state.schedule_preferences:
            st.caption("Session preferences captured so far:")
            st.table(
                [
                    {
                        "Preference": p.get("preference_text", ""),
                        "Type": p.get("type", "other"),
                        "Strength": p.get("hard_or_soft", "soft"),
                        "Confidence": p.get("confidence", "low"),
                    }
                    for p in st.session_state.schedule_preferences
                ]
            )

        chat_input = st.text_input(
            "Ask about the schedule or add preference (example: no walks before 8am).",
            key="schedule_chat_input",
        )
        if st.button("Send", key="send_schedule_chat"):
            user_message = chat_input.strip()
            if not user_message:
                st.warning("Enter a message first.")
            else:
                st.session_state.schedule_chat_messages.append({"role": "user", "content": user_message})
                tasks_payload, query_lines, species = _build_pending_schedule_context(owner)
                if not tasks_payload:
                    assistant_reply = "Add at least one pending task to discuss schedule options."
                    st.session_state.schedule_chat_messages.append({"role": "assistant", "content": assistant_reply})
                else:
                    key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
                    kb_chunks = retrieve_for_schedule_context(
                        owner_name=owner.name,
                        slot_lines=query_lines,
                        species_list=species,
                        preference_lines=_preference_lines(st.session_state.schedule_preferences),
                        top_k=6,
                    )
                    with st.spinner("Thinking..."):
                        chat_result = chat_schedule_assistant_with_rag(
                            owner_name=owner.name,
                            target_date_iso=date.today().isoformat(),
                            tasks_payload=tasks_payload,
                            knowledge_chunks=kb_chunks,
                            chat_messages=st.session_state.schedule_chat_messages,
                            api_key=key,
                            history_window=10,
                        )
                    if chat_result is None:
                        fallback = (
                            "I could not process chat right now. You can still generate a schedule; "
                            "preference capture may be limited."
                        )
                        st.session_state.schedule_chat_messages.append({"role": "assistant", "content": fallback})
                    else:
                        st.session_state.schedule_chat_messages.append(
                            {"role": "assistant", "content": chat_result.get("assistant_reply", "")}
                        )
                        summary = str(chat_result.get("chat_summary", "")).strip()
                        if summary:
                            st.session_state.schedule_chat_summary = summary
                        incoming = chat_result.get("preferences") or []
                        st.session_state.schedule_preferences = _merge_preferences(
                            st.session_state.schedule_preferences, incoming
                        )
                st.session_state.reset_schedule_chat_input = True
                st.rerun()

st.subheader("Build schedule")
st.caption("Gemini proposes times and reasons; validation enforces no overlaps and full task coverage.")

if st.button("Generate schedule"):
    tasks_payload, query_lines, species = _build_pending_schedule_context(owner)
    if not tasks_payload:
        st.warning("Add at least one pending task first.")
    else:
        kb_chunks = retrieve_for_schedule_context(
            owner_name=owner.name,
            slot_lines=query_lines,
            species_list=species,
            preference_lines=_preference_lines(st.session_state.schedule_preferences),
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
            user_preferences=st.session_state.schedule_preferences,
            chat_summary=st.session_state.schedule_chat_summary,
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
                    user_preferences=st.session_state.schedule_preferences,
                    chat_summary=st.session_state.schedule_chat_summary,
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
                st.session_state.last_applied_preferences = list(proposal.get("applied_preferences") or [])
                st.session_state.last_unapplied_preferences = list(proposal.get("unapplied_preferences") or [])
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
    applied = st.session_state.last_applied_preferences
    unapplied = st.session_state.last_unapplied_preferences
    if applied or unapplied:
        st.caption("Preference handling is best effort; task coverage and no-overlap rules take priority.")
    if applied:
        st.success("Applied preferences:")
        st.table([{"Preference": str(item)} for item in applied])
    if unapplied:
        st.info("Could not fully apply:")
        st.table(
            [
                {
                    "Preference": str(item.get("preference_text", "")).strip()
                    if isinstance(item, dict)
                    else str(item).strip(),
                    "Why": (
                        str(item.get("why", "")).strip() or "Not specified by model."
                        if isinstance(item, dict)
                        else "Not specified by model."
                    ),
                }
                for item in unapplied
                if (
                    str(item.get("preference_text", "")).strip()
                    if isinstance(item, dict)
                    else str(item).strip()
                )
            ]
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
