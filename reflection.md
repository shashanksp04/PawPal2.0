# PawPal+ Project Reflection

## 1. System Design

a. Initial design

My first UML was the basic split: an Owner has several Pets, each Pet has a list of Tasks, and a Scheduler reads those tasks and builds a DailyPlan (ordered steps with a short explanation for each). Task in that sketch was: description, duration, frequency, and done or not. That matched how I pictured the app before coding.

b. Design changes

Yes, it changed a bit. The app lets you type a start time (HH:MM) for each new task, so Task in code stores a normalized start time—not just duration. That lines up with what you see on screen: description, minutes, frequency, and start time.

The first diagram showed Scheduler mostly as buildplan. The real class also has sortbytime, filtertasks, and scheduletimeconflicts, which the Streamlit page uses for the “scheduling insights” block (conflict messages, pending tasks by pet, table sorted by start time).

Streamlit reruns the whole script on each interaction, so I keep one Owner in st.sessionstate and only create it the first time. The owner’s name can be edited from a text field, so Owner has a way to set name without rebuilding the object—small detail that wasn’t on my first UML.

---

## 2. Scheduling Logic and Tradeoffs

a. Constraints and priorities

The main ordering happens in buildplan. It only uses incomplete tasks, then sorts by frequency first (daily, then weekly, then once), then duration, then pet name and task description so the order doesn’t jump around randomly. sortbytime is different: it sorts by start time only. The UI shows pending tasks in time order after you optionally narrow by pet—there is no separate “filter by time” control; time is just how the table is sorted.

filtertasks in code can take completion and pet name. In the app I only use it for unfinished tasks and, when you pick a name, one pet (or all pets).

b. Tradeoffs

scheduletimeconflicts only flags two unfinished tasks that share the same start time. It does not look at overlapping ranges (for example one task 8:00–8:45 and another 8:30–9:00).

That was enough for this project: same-minute matches are easy to show in the UI and to explain (“two things at 9:00”). Range overlap would need more rules and clearer copy. The downside is that some real overlaps could still slip through if the times are different but the tasks still clash in real life.

---

## 3. AI Collaboration

a. How you used AI

I had to figure out the owner / pet / task model myself. AI helped me in setting up Streamlit so st.sessionstate keeps the same Owner, calling Scheduler.sortbytime, filtertasks, and scheduletimeconflicts from there, showing overlaps with st.warning and a table, and building the pending-task list sorted by time with a dropdown to pick all pets or one pet. I also used it to tighten sentences when I updated umlfinal.mmd after Scheduler grew past just buildplan.

For tests, I asked for a rough outline and some pytest starters (sorting, recurrence, conflicts), then I renamed things, fixed assertions, and added cases until they matched pawpalsystem.py—especially that sortbytime and buildplan are not the same thing.

Short, specific questions worked better than “write the whole app for me.” Example: paste what scheduletimeconflicts returns and ask how to show it without copying the logic twice.

b. Judgment and verification

I didn’t ship the first UI draft blindly. AI suggested a few patterns that would have hidden errors (for example, swallowing bad time input). I kept Task’s constructor strict and used a try/except around adding a task so invalid HH:MM shows a clear st.error instead of failing the whole script. After bigger edits, I kept running python -m pytest until everything went green—not because I trust my memory, but because the scheduler is easy to break without noticing.

---

## 4. Testing and Verification

a. What you tested

I spent time on tests/testpawpal.py with the goal of focusing on three things the assignment called out: ordering, recurrence, and conflicts.

For clock order, I tested Scheduler.sortbytime explicitly—tasks with different starttime values should come out earliest-first, and 9:00 vs 09:00 should behave like the same minute on the clock. That matters because buildplan doesn’t sort by wall-clock time; it prioritizes frequency and duration (see section 2). I didn’t want to confuse “priority order” with “morning-to-evening order,” so the tests name that difference instead of pretending one function does both.

For recurrence, I used Pet.completetask: a daily task with a fixed duedate should spawn a new incomplete task the next day; weekly should jump forward a week; once shouldn’t clone itself. I also checked the simple guard case—calling completetask on a task that was never addtask’d to the pet should do nothing.

For conflicts, scheduletimeconflicts had to flag two incomplete tasks at the same HH:MM, whether they’re on one pet or two, and had to stay quiet when times differ by a minute or when one of the duplicates is already completed. I added a small integration-style check: two same-time tasks still show up in buildplan (the plan doesn’t drop them), while the conflict list says something’s wrong—that’s the behavior I actually want for a demo.

For filtering, there’s a focused test that filtertasks respects completed=False and petname so I don’t accidentally break “show me only Mochi’s unfinished stuff” when I refactor.

I kept the older stress tests too (lots of tasks, many pets, stability across repeated buildplan calls). They’re not very complex, but they catch silly regressions fast.

b. Confidence

I’m comfortable that the backend behaviors above match the tests I wrote. I’m still not very confident on Streamlit flows—button clicks, session state edge cases—and on every possible way someone might type a time. That’s fine for this scope; the next step would be a thin layer of UI tests or manual checklist, not more micro-unit tests for the same helpers.

filtertasks already has a basic unit test; if I had more time I’d add edge cases (weird casing on pet names, owner with zero pets, filters that return nothing) and one test that feeds buildplan tasks in scrambled order to prove ordering comes from the sort key, not insertion order.

---

## 5. Reflection

a. What went well

I’m happiest that the backend and UI match. You get conflict warnings, a pending list (optional filter by pet, always sorted by start time), and the generated plan with explanations, all driven by the same Scheduler helpers instead of copy-pasted logic. That makes the demo easier to walk through.

b. What you would improve

I’d want editing tasks (not just adding), and probably a cleaner story for interval overlaps if this were a real product. I’d also tighten the README and screenshots so someone landing on the repo immediately sees what the algorithms actually do—not just how to install.

c. Key takeaway

Design diagrams are a starting point, not a finalized plan. My implementation grew once I added start times, the extra Scheduler methods, and the Streamlit wiring. The skill I care about is keeping the diagram, code, and tests in sync so they don’t drift apart.
