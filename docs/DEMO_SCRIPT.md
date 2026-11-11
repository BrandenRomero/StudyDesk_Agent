# StudyDesk — 1–2 minute demo script

Target length: **about 1 minute 50 seconds**. Record the app, your narration,
and a short glimpse of the code. Do not show API keys or private settings.
Before recording, start the server with a real API key, select OpenAI, and
practice the request once in a separate workspace. Use a clean private browser
for recording, so filenames and task IDs are predictable.

| Time | On screen | Suggested narration |
| --- | --- | --- |
| 0:00–0:15 | App home, workspace overview | "StudyDesk helps students manage the small tasks around studying. Instead of switching between notes, a task list, and a calculator, one request produces a reviewed plan and real changes." |
| 0:15–0:35 | Select OpenAI; enter request below; Build a plan | "The backend sends this request to OpenAI with a tool contract, examples, and a strict JSON schema. It receives proposed actions, rather than executable code." |
| 0:35–0:55 | Inspect the note, task, and calculation arguments | "Before anything runs, the app validates tool names, argument types, filenames, and arithmetic. I can inspect every action here. Files stay in an isolated workspace and database operations use parameterized SQL." |
| 0:55–1:10 | Execute plan; show results and desk counters | "Now I execute the reviewed plan. The note is saved, the task is stored in SQLite, and the calculator returns 155 minutes. Each action has a visible result." |
| 1:10–1:25 | Request `Delete note review.md`; show checkbox; Cancel | "Destructive operations require a separate confirmation, enforced by the server. I'll cancel this plan, keeping the note." |
| 1:25–1:40 | Open Activity log; briefly show `llm.py` | "The audit log records planning, cancellation, and action outcomes. The API client handles authentication failures, rate limiting, and temporary errors with bounded retries." |
| 1:40–1:50 | App and deployed URL | "This agent works across files, database tasks, and calculations. The code repository and deployed application are linked with my submission." |

Real LLM request:

```text
Create a note called review.md with a short checklist for BFS, DFS, and A*. Add a task to practice search algorithms. Calculate the total time for three 45-minute study sessions and two 10-minute breaks.
```

Expected arithmetic: `3 * 45 + 2 * 10 = 155`.
Inspect the generated plan before execution; the LLM may phrase the checklist
or equivalent expression differently. If it asks for clarification, answer in
a fresh request and review the new plan.

## Offline rehearsal

If you have no API key yet, select Offline demo and use:

```text
Create note review.md: Review BFS, DFS, and A*; Add task: Practice search algorithms; Calculate 3 * 45 + 2 * 10
```

Describe this explicitly as offline rehearsal using a deterministic parser.
It exercises the same executor and safety controls, but it does **not**
demonstrate the required real LLM call. The final assignment video should
show OpenAI mode with a successful real API request.

## Recording and publishing

Record with your preferred screen recorder at a readable resolution. Keep
the final clip between one and two minutes. Upload it to the video service
you choose, with access that allows the instructor to watch it, and test the
link from another browser. A demo script is supplied here; no video has been
recorded or published automatically.
