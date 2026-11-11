# Validation record

The local project was tested on Windows using Python 3.14.

## Automated checks

```text
python -m unittest discover -s tests -v
Ran 30 tests
OK (skipped=1)
```

**29 tests passed; one symlink test skipped** because this Windows account
does not have permission to create symbolic links. Path traversal, absolute
paths, reserved device filenames, and filename casing were tested separately.

Also passed:

```text
node --check studydesk/static/app.js
python -m compileall -q app.py build_submission.py studydesk
```

The tests cover three-domain execution, server-side destructive confirmation,
overwrite detection inside a plan, stale-risk detection, replay/concurrency,
session isolation, expiry/cancellation, partial failures, audit events, numeric
bounds, unknown tools, invalid arguments, API payload parsing, API retries,
authentication failures, refusals/incomplete output, same-origin checks,
request limits, optional password access, and health checks.

OpenAI responses were mocked. **No live OpenAI API call was made** because a
key was not configured. The project does not silently treat offline behavior
as proof of LLM performance. Docker and cloud deployment were not executed.

## Browser checks

The actual local web app was opened and exercised through its UI:

1. Built a three-action offline plan: save `exam.md`, add a study task, and
   evaluate `(45 + 15) * 3`.
2. Executed the plan; note/task counters changed to one each.
3. Built and executed a follow-up read/list/calculation plan. The UI displayed
   the saved note text, the SQLite task, and the result **180**.
4. Switched to OpenAI mode. The interface displayed the missing-key guidance,
   then returned to Offline demo.
5. Built `Delete note exam.md`. Execute was disabled with the confirmation
   unchecked and enabled after checking it. The plan was **cancelled**, so the
   note remained present and the activity log recorded cancellation.
6. Reloaded and verified workspace persistence under the same session cookie.
7. Inspected the layout at the normal browser size and at a **390 × 844**
   mobile viewport. Reset the viewport override afterward.

Screenshots captured from the live app are included as `preview.jpg`,
`preview-results.jpg`, `preview-confirmation.jpg`, and `preview-mobile.jpg`.
These are viewport screenshots, not a recorded video.

## Remaining submission work

- Configure a real OpenAI API key and confirm one successful live request.
- Verify instructor access to [the source repository](https://github.com/BrandenRomero/StudyDesk_Agent).
- Deploy using the supplied Docker/Render configuration and verify access.
- Record and publish a 1–2 minute demo using `DEMO_SCRIPT.md`.
- Submit the actual repository, deployment, and video URLs through the course
  form. Confirm the due date in Canvas.

Hosting, API configuration, and video publication remain with the user.
