# StudyDesk Agent — Project report

## Problem identification and relevance (10%)

Students repeatedly switch between notes, to-do lists, and calculators while
planning coursework. StudyDesk brings these small administrative tasks into
one natural-language interface. A single request can create a study note, add
a task, and calculate time. The outcome is a changed workspace, rather than
only a conversational answer.

The target user is a student preparing coursework or an exam. Success means
the requested artifacts are created accurately, the student can review what
will happen, and failures are visible and recoverable through a new plan.
The tool is intentionally limited to its own educational workspace.

## Application design and implementation (30%)

The Python backend separates the LLM planner from the executor. OpenAI returns
a structured proposal; it cannot execute Python, SQL, or operating-system
commands. A validation layer converts the proposal into allowlisted commands.
The browser shows the complete proposal and its exact arguments before
execution. The executor acts on files, SQLite tasks, and arithmetic.

The LLM integration uses the HTTPS Responses API, a configurable model, and
strict schema output. Authentication errors do not retry. Rate limiting,
server errors, and connection failures receive bounded retries. Refusals,
incomplete responses, malformed JSON, and invalid action plans are surfaced
as user-facing errors, without execution.

The interpreter checks tool names and exact argument types. It rejects extra
fields, traversal/absolute filenames, device filenames, invalid IDs, long
payloads, and unsafe arithmetic. SQLite values use parameterized statements.
Arithmetic traverses a bounded syntax tree and rejects function calls and
attribute access. No arbitrary shell tool is exposed.

Browser sessions map to different note folders and databases. A cryptographic
random plan ID references a stored plan, so client edits cannot replace the
executor's actions. A plan expires after 15 minutes, can be cancelled, and
can run once. The server identifies overwrites and deletions, including two
writes to the same filename in one plan. It requires an explicit confirmation
and rechecks risk before execution. Every started action receives an audit
record followed by a success or failure record during normal execution.

Execution stops at the first failure and reports any skipped actions. Earlier
successes remain saved. A crash can leave an `executing` plan and a started
audit event; it cannot be blindly replayed. This conservative choice avoids
silently repeating file or database mutations.

## Prompt engineering techniques (20%)

The actual prompt and schema are in `studydesk/llm.py`.

1. **Role and scope:** The model is a student-workspace planner. It is told
   that a separate executor will validate and execute its proposal.
2. **Explicit tool contract:** Each tool and its argument names are listed.
   Unsupported operations cannot be invented into executable authority.
3. **Few-shot examples:** Task creation, time calculation, a combined note/task
   request, and an ambiguous bulk-deletion request illustrate desired behavior.
4. **Schema-constrained output:** The Responses API enforces a plan envelope
   and fixed action/argument shape. Independent local validation also checks
   domain semantics; JSON compliance alone is insufficient for execution.
5. **Grounding in current state:** Each request includes the current filenames
   and task records. The model can use actual task IDs and resolve follow-up
   references against this inventory, rather than guessing.
6. **Abstention and clarification:** An empty action list is valid for missing
   information, unsupported intent, or ambiguity. The summary asks the user
   for clarification, instead of taking an irreversible guess.
7. **Untrusted-data boundary:** Workspace strings are explicitly data. Note
   contents are not automatically fed back into the model. Runtime allowlists
   and sandbox checks remain the authority even if a prompt instruction fails.

These techniques guide the planner; none replaces deterministic safeguards.
There is no claim that prompt injection is fully solved. Users review content
and task relevance before executing any model-generated plan.

## UI/UX design (10%)

The browser interface follows Request -> Review -> Results. Example buttons
populate the request without triggering execution. The workspace overview
shows notes and open tasks; note buttons prepare a read request. Exact action
arguments and output remain inspectable. In-progress controls prevent duplicate
clicks. Status text uses an accessible live region, inputs have labels, and
the layout adapts to narrow screens.

The two planner choices are explicit: Offline demo is a deterministic grammar,
while OpenAI requires an API key and interprets flexible natural language.
Missing configuration produces an actionable error, not a silent fallback.

## Presentation and live demo (30%)

Use `DEMO_SCRIPT.md` to show the problem, a real LLM-generated multi-domain
plan, execution results, a destructive preview, and the audit log in 1–2 minutes.
Use offline mode as a contingency only and describe it honestly. The submitted
demo should include a real OpenAI call once credentials are configured.

## Requirement traceability

| Assignment requirement | Implementation | Verification |
| --- | --- | --- |
| Connect to an LLM API | `OpenAIPlanner`, HTTPS Responses endpoint | Mocked request/response contract; live call needs user's key |
| Send prompts and receive responses | System prompt, workspace inventory, strict plan schema | Response parser tests |
| API errors/rate limits | Authentication handling, retries, backoff, Retry-After | Mocked 401, 429, timeout, malformed/refusal tests |
| Extract executable commands | JSON plan -> `validate_plan` | Unknown tools/types/arguments rejected |
| Actions across domains | Note files, SQLite tasks, arithmetic | End-to-end multi-domain test |
| Natural language UI | Browser request field + OpenAI planner | Browser workflow verification; live inference pending key |
| Results/status/feedback | Preview, spinner text, results, desk counters | Browser multi-action workflow |
| Validate before execution | Server validation and server-owned plan | Schema, traversal, replay and expiry tests |
| Graceful failures | User-facing errors, stop-on-failure results | Partial failure and skipped-action tests |
| Destructive confirmation | Risk preview + server confirmation check | Delete, overwrite, changed-risk tests |
| Auditability | SQLite audit history and activity panel | Action outcome and rejected-plan tests |
| GitHub repository URL | [BrandenRomero/StudyDesk_Agent](https://github.com/BrandenRomero/StudyDesk_Agent) | Source and documentation at repository root |
| Deployed URL | Dockerfile + Render blueprint + smoke checklist | User deploys to their hosting account |
| 1–2 minute video link | Timed recording script | User records and publishes demo |

## Limitations and future work

This is a single-process educational deployment. Sessions are isolated by
random browser cookies, not individual user accounts. Rate limits reset with
the server. Disk quotas are per session and cannot stop someone creating many
sessions. The optional shared password is appropriate for a small evaluator
demo; a public product needs real identity, durable quotas, managed secrets,
distributed locking, backups, and a durable database.

The planner performs a single planning pass and does not automatically reflect
on results or replan. It can return an ordered multi-action plan but cannot
substitute newly created IDs into later actions. Users can make another request
after results update the inventory. It does not browse the web, send messages,
or run arbitrary code. The local verification used offline mode and mocked
OpenAI responses; real-key evaluation remains a separate step.
