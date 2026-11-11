# Publish and deploy StudyDesk

Source repository: [BrandenRomero/StudyDesk_Agent](https://github.com/BrandenRomero/StudyDesk_Agent).
Cloud deployment, live API testing, and video publication remain separate
steps. The assignment's final submission requires actual URLs.

## 1. Access the source on GitHub

The repository linked above contains this project's files at its root. Clone
or download it to work on the project. If the repository is private, grant
the instructor access before submitting its URL.

Source includes `studydesk/`, `tests/`, `docs/`, `app.py`, `README.md`,
`requirements.txt`, `Dockerfile`, `.dockerignore`, `.gitignore`, `.env.example`,
and `render.yaml`. Local workspaces, caches, secrets, and the original
assignment PDF are excluded. Continue excluding those files from future commits.

If you instead publish the entire parent repository, set the hosting Root
Directory to `assignment4`. The blueprint below assumes this project is at
the repository root.

## 2. Deploy on Render

This project includes a Dockerfile and a `render.yaml` blueprint. The app reads
the host-assigned `PORT` and listens on `0.0.0.0` in Docker. Waitress runs one
process with four threads.

1. Sign in to Render and connect the GitHub repository you created.
2. Choose **New -> Blueprint**, select the repository, and review `render.yaml`.
   Alternatively create a **Web Service**, choose Docker runtime, and use the
   included Dockerfile with no start-command override.
3. Choose the available compute plan you want. The supplied blueprint requests
   the free plan. Review any provider cost or account requirements yourself.
4. Add environment variables in the hosting dashboard:

   | Variable | Value |
   | --- | --- |
   | `OPENAI_API_KEY` | Your API key, stored privately in hosting settings |
   | `OPENAI_MODEL` | `gpt-4o-mini` or an accessible compatible model |
   | `APP_PASSWORD` | A strong password you choose for evaluator access |
   | `DATA_DIR` | `/app/data` for an ephemeral classroom demo |

5. Deploy and wait for the health check `/health` to succeed. Copy the actual
   HTTPS service URL from the dashboard.
6. Open that URL. Sign in using username **studydesk** and the `APP_PASSWORD`
   you configured. Share these access details privately with the evaluator.
7. Choose OpenAI and run the smoke checks below. Inspect hosting logs if the
   UI returns an error. Never paste key values into screenshots or submissions.

Render's free instances can sleep after inactivity. Their local filesystem is
ephemeral, so notes/tasks/audit history can disappear after restarts/redeploys.
For persistence, use an appropriate hosting plan with a persistent disk mounted
at a writable location and set `DATA_DIR` to that location. Keep **one instance
and one server process**. Do not claim durable storage on the free configuration.

Official reference: [Your First Render Deploy](https://render.com/docs/your-first-deploy).

## 3. Alternative: Docker

From the project directory, with Docker installed:

```powershell
docker build -t studydesk-agent .
docker run --rm -p 127.0.0.1:8000:8000 studydesk-agent
```

The example above runs offline mode with temporary container storage. For
OpenAI, first configure your shell's `OPENAI_API_KEY` as described in the README,
then pass it by variable name without putting the value in the command:

```powershell
docker run --rm -p 127.0.0.1:8000:8000 -e OPENAI_API_KEY -e OPENAI_MODEL -e APP_PASSWORD studydesk-agent
```

To preserve data outside the container, mount a directory writable by the
container's `agent` user and set `DATA_DIR` accordingly. If hosting on your own
server, put the application behind an HTTPS reverse proxy. Do not expose a
live-key instance without the password or an equivalent authenticated gateway.

The Docker image/build was prepared but not executed in this environment.

## 4. Smoke checks before submission

- The HTTPS URL opens in a fresh/private browser, with access details available
  to the instructor. `/health` returns `{"status":"ok"}`.
- Offline demo creates a note and task; reload retains them while the session
  cookie and server data remain available.
- OpenAI handles a flexible request such as "Add a task to review agents and
  calculate two 50-minute sessions plus a 10-minute break." Verify the result.
- A deletion or overwrite preview shows a confirmation checkbox; Execute is
  disabled until checked. Cancel the preview if no deletion is needed.
- A missing note reports an error without crashing. The activity log shows
  the failed action and plan completion status.
- API errors show feedback without exposing credentials or provider payloads.
- Repository, deployed app, and video links are accessible to the evaluator.

## 5. Submit

Use the course form linked in the assignment PDF. Provide your **actual GitHub
URL, deployed application URL, and 1–2 minute demo video URL**. Check the due
date in Canvas. This project has not submitted the form for you.
