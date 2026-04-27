# PawPal+ Project README

![PawPal+ Demo](assets/Demo%20Video.gif)

## Original Project (Modules 1-3): PawPal
My original project was called **PawPal**. The main goal was to help one pet owner keep pet-care tasks organized in one place so daily care was easier to manage. It focused on storing pets and tasks clearly, so people could avoid forgetting important care steps.

## Title and Summary
**PawPal+** is an AI-assisted pet-care planner built with Streamlit. It helps users add pet tasks, generate a daily schedule with AI, and save approved task times. This matters because it supports more consistent pet care and reduces the stress of planning everything manually.

## Architecture Overview
The app has four main parts that work together:

1. `app.py` handles the user interface and task input.
2. `pawpal_rag.py` pulls useful care guidance from a knowledge base.
3. `gemini_client.py` sends task context to Gemini and gets a schedule proposal.
4. Validation logic checks that the proposed schedule is safe and complete before saving to `data/pawpal_store.json`.

In simple terms, users add tasks, the AI suggests when to do them, the app checks if the plan makes sense, and then users choose whether to save it.

## Setup Instructions
1. Create a virtual environment:
   ```bash
   python -m venv .venv
   ```
2. Activate the environment:
   - Windows:
     ```powershell
     .venv\Scripts\activate
     ```
   - macOS/Linux:
     ```bash
     source .venv/bin/activate
     ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Set your Gemini API key:
   - PowerShell:
     ```powershell
     $env:GOOGLE_API_KEY="your-key"
     ```
   - macOS/Linux:
     ```bash
     export GOOGLE_API_KEY="your-key"
     ```
5. Run the app:
   ```bash
   streamlit run app.py
   ```

## Sample Interactions
### Test Case 1: Preference-based scheduling (single pet)
- **Input:** Jordan has one dog (Mochi) with two daily 20-minute tasks: Walk and Food. In Schedule Q&A, the user says: "Walk in the evening, food in the afternoon."
- **AI Output:** The app generates a schedule that follows the preference: Food around afternoon and Walk around evening.
- **Result shown in test run:** Food at `14:00`, Walk at `19:00`, and both preferences appear as applied.

### Test Case 2: Basic scheduling without chat preferences
- **Input:** Same tasks for Mochi (Walk and Food), but no chat message is provided.
- **AI Output:** The app creates a default consistent plan with morning tasks in sequence.
- **Result shown in test run:** Walk at `07:00`, Food at `07:20`.

### Test Case 3: Multi-pet coordination request
- **Input:** Mochi has daily Walk and Food. Maya has a weekly Pet Daycare task. User asks to time Mochi's walk so it lines up with Maya's daycare ending, so both can come home together.
- **AI Output:** The app generates a valid plan for all tasks and reports which preference could not be fully applied.
- **Result shown in test run:** A full schedule is generated (for example Food morning, Daycare afternoon, Walk later), and the app marks the "match daycare end time" preference as not fully applied when timing rules conflict.

## Design Decisions
- I kept schedule validation strict, so the app can reject unsafe plans like overlapping task times.
- I kept saving as a separate step, so users can review AI suggestions before anything is written to storage.
- I used a small reference knowledge base to help the AI make more useful scheduling suggestions.

Trade-offs:
- More checks improve safety, but they add extra logic and make the scheduling flow longer.
- AI output quality depends on the prompt and the reference data, so results can vary.

Additional decisions from the latest implementation:
- I made Schedule Q&A optional and placed it in a collapsed section, so users who just want fast scheduling can ignore it.
- I stored chat preferences only in session state, which keeps setup simple and avoids long-term personal preference storage.
- I added transparent "applied" and "not fully applied" preference feedback after generation, so users can understand AI decisions.
- I bounded preference text used for retrieval context to keep RAG results focused and reduce noisy matches.

## Testing Summary
What worked well:
- The test suite passed during implementation (`pytest`), including schedule checks and knowledge lookup behavior.
- Core safety checks stayed stable while new schedule-chat preference features were added.

What did not work at first:
- There was a Streamlit input reset issue during the scheduling chat flow.
- That issue was fixed by improving how the app resets chat input state.

What I learned:
- AI features are more reliable when combined with clear validation and small iterative fixes.
- Testing each change quickly helps prevent regressions.

Additional testing notes from this update:
- I ran `python -m pytest -q` and all tests passed (`46 passed`).
- The schedule pipeline was validated in two paths: without chat (baseline generation) and with chat preferences (preference-aware generation).
- There was one expected warning from the `google.generativeai` dependency deprecation notice, but it did not affect app behavior.
- After fixing the chat input reset flow with rerun-safe state handling, the Streamlit runtime exception no longer reproduced.

## Reliability and Evaluation
- **Automated tests:** `46/46` tests passed in the latest run, including schedule validation and retrieval checks.
- **Logging and error handling:** the app logs generation and validation failures, retries once when a proposal fails validation, and shows clear error messages when it still fails.
- **Human evaluation:** I reviewed multiple real app runs (Test Case 1, 2, and 3) to confirm behavior with normal inputs, no-preference inputs, and preference conflicts.
- **Current limitation:** confidence scoring is not added yet. Reliability currently depends on validation rules, test coverage, and manual review of outputs.

Quick summary: `46/46` tests passed. Reliability improved after adding validation checks, retry handling, and clearer preference feedback when the AI could not fully apply a request.

## Reflection
This project taught me that AI is most useful when it is paired with practical safety checks and a clear user review step. I also learned that good problem-solving is usually iterative: test a small change, learn from what fails, then improve. Building PawPal+ helped me think more carefully about trust, usability, and how to turn AI output into something people can actually use in daily life.

With the new Schedule Q&A flow, I also learned how important explanation and transparency are for trust. Users are more comfortable with AI scheduling when they can ask follow-up questions and see why some preferences were applied while others were not. I also got better at handling UI state issues in Streamlit, especially around widget lifecycle rules. That bug fix reminded me that reliable user experience is not only about model quality, it is also about careful state management.

## Responsible AI Reflection
### Limitations and potential bias
This system depends on the quality of user input and the knowledge base. If the task details are incomplete or unclear, the schedule quality drops. It can also reflect bias from the source content, such as assumptions about ideal pet-care timing that may not fit every owner, routine, or culture.

### What surprised me during reliability testing
What surprised me most was that reliability issues were not only model-related. A UI state bug in Streamlit caused failures even when the AI logic was fine. Fixing state handling and adding clear validation improved reliability more than prompt changes alone.

### Collaboration with AI during this project
AI was useful as a coding partner for generating scheduling drafts and for helping shape preference-aware behavior. One helpful suggestion was to keep generation and save as separate steps, which made review safer and improved trust. One flawed suggestion was a schedule that failed validation because of overlapping windows, even after retry. That showed me I still need strong guardrails and test-driven checks around model outputs.
