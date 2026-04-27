# PawPal+ Implementation Context

## Feature Overview
- Added an optional **Schedule Q&A** experience inside the scheduling flow.
- Added **preference-aware scheduling** where chat-derived preferences are passed to schedule generation as best-effort guidance.
- Kept feasibility guardrails intact: schedules must still pass existing validation (coverage, HH:MM format, and no overlap).

## UI and State Changes (`app.py`)
- Added imports for `chat_schedule_assistant_with_rag` and updated scheduling flow orchestration.
- Added helper functions:
  - `_build_pending_schedule_context(owner)` to produce `tasks_payload`, retrieval lines, and species list.
  - `_merge_preferences(existing, incoming)` to normalize and deduplicate session preferences.
  - `_preference_lines(preferences)` to serialize stored preferences for retrieval enrichment.
- Added new `st.session_state` keys:
  - `schedule_chat_messages`
  - `schedule_preferences`
  - `schedule_chat_summary`
  - `last_applied_preferences`
  - `last_unapplied_preferences`
  - `reset_schedule_chat_input`
- Added optional **Schedule Q&A (optional)** section:
  - Collapsible expander.
  - `Send` action for chat requests.
  - `Clear chat` action resetting chat/preference state.
  - Preference table showing captured session preferences.
  - Hint updated to clarify preferences are session-only and used when generating schedules.
- Fixed Streamlit widget-state behavior:
  - Uses `reset_schedule_chat_input` flag + `st.rerun()` to clear input safely.
  - Avoids mutating widget-bound key after widget instantiation.
- Removed the **Scheduling insights** section per cleanup request.
- Added post-generation transparency UI:
  - `Applied preferences` table.
  - `Could not fully apply` table with reasons when provided.

## Gemini Client Changes (`gemini_client.py`)
- Added `_normalize_preferences(raw)`:
  - Validates/normalizes fields: `preference_text`, `type`, `confidence`, `hard_or_soft`, `source_message`.
  - Coerces invalid confidence/strength values to safe defaults.
- Added `chat_schedule_assistant_with_rag(...)`:
  - Accepts tasks + knowledge chunks + recent chat history.
  - Uses rolling context window (`history_window`, default 10).
  - Returns structured payload:
    - `assistant_reply`
    - `chat_summary`
    - `preferences` (structured extraction)
- Extended `propose_daily_schedule_with_rag(...)`:
  - New optional args: `user_preferences`, `chat_summary`.
  - Prompt now includes `USER_CHAT_SUMMARY` and `USER_PREFERENCES`.
  - Prompt requests:
    - `applied_preferences`
    - `unapplied_preferences` with brief reasons.
  - Response normalization now ensures stable output shape for these fields.

## Retrieval Update (`pawpal_rag.py`)
- Extended `retrieve_for_schedule_context(...)` with optional `preference_lines`.
- Added bounded enrichment to retrieval query:
  - Trims each preference line to 120 chars.
  - Uses at most 4 preference lines.
- Goal: improve retrieval relevance without introducing excessive query noise.

## Data Flow Summary
1. User enters optional chat message in Schedule Q&A.
2. App sends recent chat + tasks + RAG knowledge to Gemini chat helper.
3. Chat helper returns response + extracted preferences + chat summary.
4. App stores these values in session state only.
5. On **Generate schedule**, app passes tasks + knowledge + preferences + summary to proposal API.
6. Proposal is validated with existing `validate_proposed_schedule`.
7. UI shows schedule plus applied/unapplied preference transparency.

## Guardrails and Non-Changes
- Validation core remains unchanged: `validate_proposed_schedule` is still authoritative.
- Retry path remains intact; now includes preferences and summary for consistency across attempts.
- Behavior remains backward-compatible:
  - If chat is unused, schedule generation still works as before.
  - Preference-aware enhancements are optional and additive.

## Submission Cleanup Applied
- Reset `data/pawpal_store.json` to a clean state:
  - Owner present (`Jordan`)
  - `pets: []` (no pets/tasks preloaded)

## Verification Notes
- Lint diagnostics on edited files: no linter errors reported.
- Test run status during implementation cycle:
  - `python -m pytest -q` passed (`46 passed`, with one warning from upstream `google.generativeai` deprecation notice).
- Streamlit input-reset runtime exception was fixed via rerun-safe state handling.

## README-Derived Feature Additions (Detailed, Non-Duplicate)
- **Task creation is now time-agnostic by default:**
  - Users can create tasks without entering `HH:MM` at creation time.
  - This shifts the workflow from manual slotting to AI-assisted planning.
  - The `start_time` field can remain `null` until a generated schedule is accepted.
- **AI now proposes executable daily timing for pending tasks:**
  - Schedule generation assigns a concrete `start_time` to each pending `task_id`.
  - Proposals include ordering and timing rationale, not just raw timestamps.
  - The generation path is exposed through `propose_daily_schedule_with_rag(...)` in `gemini_client.py`.
- **Validation guarantees feasibility before a plan is accepted:**
  - Every pending task must appear **exactly once** in the generated result.
  - All proposed times must be valid `HH:MM`.
  - Intervals are checked as `[start, start + duration)` and must not overlap.
  - Any task that would extend past midnight is rejected.
  - These checks are enforced in code before persistence, preserving deterministic safety guardrails.
- **Reasoning and citation transparency are part of the scheduling UX:**
  - The UI surfaces model reasoning to explain why tasks were arranged a certain way.
  - The UI also shows citation IDs mapped to snippets from `data/knowledge_base.json`.
  - This makes generated plans inspectable and easier to trust or reject.
- **Schedule persistence is explicit and user-controlled:**
  - Generated times are not immediately committed to storage.
  - Users finalize by clicking **Save schedule**, which writes approved start times to `data/pawpal_store.json`.
  - This keeps generation and persistence as separate steps for safer review.
- **Storage and schema behavior are now clearly defined:**
  - Primary store: `data/pawpal_store.json` (auto-created when missing).
  - Reference schema: `data/pawpal_store.example.json`.
  - Schema version is `2` and supports unscheduled tasks via `start_time: null`.
- **Core AI + retrieval stack is documented end-to-end:**
  - Retrieval layer: `pawpal_rag.py` over `data/knowledge_base.json`.
  - Model client and scheduling prompt/response orchestration: `gemini_client.py`.
  - Prompt guardrails require JSON-only output, no diagnosis advice, non-overlapping windows, and citation IDs from provided retrieval snippets.
