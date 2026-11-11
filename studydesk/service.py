"""Plan lifecycle, session isolation, persistence, confirmation, and audit trail."""
import json
import logging
import secrets
import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path

from .llm import OpenAIPlanner, demo_plan
from .tools import AgentError, execute_action, risks, validate_plan

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
    done INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS plans (
    id TEXT PRIMARY KEY, body TEXT NOT NULL, mode TEXT NOT NULL,
    created REAL NOT NULL, status TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY, at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    event TEXT NOT NULL, detail TEXT NOT NULL);
"""


class AgentService:
    def __init__(self, data_dir, planner=None):
        self.root = Path(data_dir).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.planner = planner or OpenAIPlanner()
        self.lock = threading.RLock()
        self.llm_slots = threading.BoundedSemaphore(2)
        self.requests = []

    def workspace(self, session):
        if len(session) != 32 or any(c not in "0123456789abcdef" for c in session):
            raise AgentError("Invalid browser session.")
        root = self.root / session
        (root / "notes").mkdir(parents=True, exist_ok=True)
        return root

    def connect(self, session):
        conn = sqlite3.connect(self.workspace(session) / "agent.sqlite3", timeout=10)
        conn.row_factory = sqlite3.Row
        conn.executescript(SCHEMA)
        return conn

    @staticmethod
    def log(conn, event, detail):
        conn.execute("INSERT INTO audit(event,detail) VALUES (?,?)", (event, json.dumps(detail)))
        conn.commit()

    def state(self, session):
        with self.lock, closing(self.connect(session)) as conn:
            return {
                "notes": sorted(p.name for p in (self.workspace(session) / "notes").iterdir()
                                if p.is_file() and not p.is_symlink()),
                "tasks": [dict(r) for r in conn.execute("SELECT * FROM tasks ORDER BY id DESC")],
                "audit": [dict(r) for r in conn.execute("SELECT * FROM audit ORDER BY id DESC LIMIT 50")],
                "live_available": bool(self.planner.api_key), "model": self.planner.model,
            }

    def preview(self, session, prompt, mode):
        if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 4000:
            raise AgentError("Enter a request between 1 and 4,000 characters.")
        if mode not in ("demo", "openai"):
            raise AgentError("Choose Offline demo or OpenAI.")
        with self.lock:
            now = time.time()
            self.requests = [(t, s) for t, s in self.requests if now - t < 60]
            if len(self.requests) >= 60 or sum(s == session for _, s in self.requests) >= 10:
                raise AgentError("Too many plans. Please wait a minute before trying again.")
            self.requests.append((now, session))
        context = self.state(session)
        context = {"notes": context["notes"], "tasks": context["tasks"]}
        try:
            if mode == "demo":
                plan = demo_plan(prompt.strip())
            else:
                if not self.llm_slots.acquire(blocking=False):
                    raise AgentError("The planner is busy. Please try again shortly.")
                try:
                    plan = self.planner.plan(prompt.strip(), context)
                finally:
                    self.llm_slots.release()
            plan = validate_plan(plan)
            with self.lock, closing(self.connect(session)) as conn:
                plan_id = secrets.token_hex(16)
                warnings = risks(plan["actions"], self.workspace(session) / "notes")
                # Preview risk is part of the server-owned plan, not client authority.
                body = {**plan, "warnings": warnings}
                conn.execute("DELETE FROM plans WHERE created < ?", (time.time() - 3600,))
                conn.execute("INSERT INTO plans VALUES (?,?,?,?,?)",
                             (plan_id, json.dumps(body), mode, time.time(), "pending"))
                self.log(conn, "plan.created", {"plan_id": plan_id, "mode": mode,
                                               "tools": [a["tool"] for a in plan["actions"]]})
                return {**body, "id": plan_id, "mode": mode, "status": "pending"}
        except AgentError as exc:
            with self.lock, closing(self.connect(session)) as conn:
                self.log(conn, "plan.rejected", {"mode": mode, "error": str(exc)})
            raise

    def execute(self, session, plan_id, confirmed=False, cancel=False):
        if not isinstance(plan_id, str) or len(plan_id) != 32:
            raise AgentError("Invalid plan ID.")
        with self.lock, closing(self.connect(session)) as conn:
            # This lock covers risk revalidation and execution. Only one process is supported.
            row = conn.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
            if row is None:
                raise AgentError("This plan does not belong to your session or no longer exists.")
            if row["status"] != "pending":
                raise AgentError("This plan is no longer pending. Create a new plan.")
            if time.time() - row["created"] > 900:
                conn.execute("UPDATE plans SET status='expired' WHERE id=?", (plan_id,))
                self.log(conn, "plan.expired", {"plan_id": plan_id})
                raise AgentError("This plan expired after 15 minutes. Create a fresh preview.")
            if cancel:
                conn.execute("UPDATE plans SET status='cancelled' WHERE id=?", (plan_id,))
                self.log(conn, "plan.cancelled", {"plan_id": plan_id})
                return {"status": "cancelled", "results": []}
            body = json.loads(row["body"])
            plan = validate_plan({k: body[k] for k in ("summary", "actions")})
            root = self.workspace(session) / "notes"
            current_risks = risks(plan["actions"], root)
            if current_risks != body["warnings"]:
                conn.execute("UPDATE plans SET status='stale' WHERE id=?", (plan_id,))
                self.log(conn, "plan.stale", {"plan_id": plan_id})
                raise AgentError("The workspace changed and this plan has different risks. Create a new preview.")
            if current_risks and confirmed is not True:
                self.log(conn, "execution.blocked", {"plan_id": plan_id, "reason": "confirmation required"})
                raise AgentError("Confirm the displayed deletions or overwrites before executing.")
            if not plan["actions"]:
                raise AgentError("There are no actions to execute. Update your request.")
            conn.execute("UPDATE plans SET status='executing' WHERE id=?", (plan_id,))
            self.log(conn, "execution.started", {"plan_id": plan_id})
            results = []
            status = "completed"
            for index, action in enumerate(plan["actions"]):
                self.log(conn, "action.started", {"plan_id": plan_id, "index": index, "tool": action["tool"]})
                try:
                    result = execute_action(action, root, conn)
                    results.append({"tool": action["tool"], "status": "success", "result": result})
                    self.log(conn, "action.succeeded", {"plan_id": plan_id, "index": index,
                                                        "tool": action["tool"]})
                except (AgentError, OSError, sqlite3.Error, UnicodeError) as exc:
                    conn.rollback()
                    message = str(exc) if isinstance(exc, AgentError) else "The action could not access workspace storage."
                    if not isinstance(exc, AgentError):
                        logging.exception("Workspace action failed")
                    results.append({"tool": action["tool"], "status": "error", "error": message})
                    self.log(conn, "action.failed", {"plan_id": plan_id, "index": index,
                                                    "tool": action["tool"], "error": message})
                    status = "failed"
                    # Earlier successes persist. Never claim that a partial run rolled back.
                    break
            conn.execute("UPDATE plans SET status=? WHERE id=?", (status, plan_id))
            self.log(conn, "execution.finished", {"plan_id": plan_id, "status": status,
                                                  "skipped": len(plan["actions"]) - len(results)})
            return {"status": status, "results": results,
                    "skipped": len(plan["actions"]) - len(results)}
