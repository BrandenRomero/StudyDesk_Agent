import base64
import io
import json
import os
import tempfile
import threading
import time
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from studydesk.llm import OpenAIPlanner, demo_plan
from studydesk.service import AgentService
from studydesk.tools import AgentError, calculate, note_path, validate_plan
from studydesk.web import create_app

SESSION = "a" * 32
OTHER = "b" * 32


class ToolTests(unittest.TestCase):
    def test_arithmetic(self):
        self.assertEqual(calculate("(45 + 15) * 3"), 180)
        self.assertEqual(calculate("-3 + 2 ** 4 / 2"), 5)

    def test_arithmetic_rejects_code_and_resource_abuse(self):
        for expression in ["__import__('os').getcwd()", "(1).__class__", "2 ** 10000000",
                           "1/0", "1e999", "1j", "True", "1" * 201, "1e15 * 2"]:
            with self.subTest(expression=expression), self.assertRaises(AgentError):
                calculate(expression)

    def test_rejects_path_traversal_absolute_paths_and_hidden_files(self):
        for name in ["../secret.md", "C:\\secret.txt", "/etc/passwd", ".env", "a/b.md", "file.py"]:
            with self.subTest(name=name), self.assertRaises(AgentError):
                validate_plan({"summary": "Test", "actions": [{"tool": "note.read", "arguments": {"name": name}}]})

    def test_rejects_unknown_tools_wrong_types_and_extra_args(self):
        for action in [{"tool": "shell.run", "arguments": {}},
                       {"tool": "task.delete", "arguments": {"task_id": True}},
                       {"tool": "task.delete", "arguments": {"task_id": 0}},
                       {"tool": "note.list", "arguments": {"sql": "DELETE FROM tasks"}},
                       {"tool": "task.add", "arguments": {"title": " "}}]:
            with self.subTest(action=action), self.assertRaises(AgentError):
                validate_plan({"summary": "Test", "actions": [action]})

    def test_symlink_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "notes"
            root.mkdir()
            target = Path(tmp) / "outside.md"
            target.write_text("private")
            try:
                (root / "link.md").symlink_to(target)
            except OSError:
                self.skipTest("Symlink privilege is unavailable on this Windows account")
            with self.assertRaises(AgentError):
                note_path(root, "link.md")

    def test_windows_device_names_are_rejected(self):
        for name in ["CON.md", "nul.txt", "COM1.md", "LPT9.txt"]:
            with self.subTest(name=name), self.assertRaises(AgentError):
                validate_plan({"summary": "Read", "actions": [{"tool": "note.read", "arguments": {"name": name}}]})

    def test_demo_is_explicit_and_rejects_unsupported_requests(self):
        self.assertEqual(demo_plan("Send an email")["actions"], [])
        self.assertEqual(len(demo_plan("Add task: Read; Calculate 2+2")["actions"]), 2)


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.service = AgentService(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def plan(self, text, session=SESSION):
        return self.service.preview(session, text, "demo")

    def run_plan(self, text, confirmed=False):
        plan = self.plan(text)
        return self.service.execute(SESSION, plan["id"], confirmed)

    def test_end_to_end_three_domains(self):
        result = self.run_plan("Create note exam.md: Review BFS; Add task: Practice BFS; Calculate 45 * 2")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["results"][-1]["result"]["value"], 90)
        state = self.service.state(SESSION)
        self.assertEqual(state["notes"], ["exam.md"])
        self.assertEqual(state["tasks"][0]["title"], "Practice BFS")
        self.assertTrue(any(r["event"] == "action.succeeded" for r in state["audit"]))
        read = self.run_plan("Read note exam.md")
        self.assertEqual(read["results"][0]["result"]["content"], "Review BFS")

    def test_confirmation_on_delete_and_overwrite(self):
        self.run_plan("Create note exam.md: original")
        for text in ["Create note exam.md: changed", "Delete note exam.md"]:
            plan = self.plan(text)
            self.assertTrue(plan["warnings"])
            with self.assertRaisesRegex(AgentError, "Confirm"):
                self.service.execute(SESSION, plan["id"])
            self.assertEqual((Path(self.tmp.name) / SESSION / "notes/exam.md").read_text(), "original")
            self.service.execute(SESSION, plan["id"], True)
            if text.startswith("Create"):
                self.run_plan("Create note exam.md: original", True)
        self.assertEqual(self.service.state(SESSION)["notes"], [])

    def test_two_saves_in_one_plan_require_confirmation(self):
        plan = self.plan("Create note a.md: one; Create note a.md: two")
        self.assertTrue(plan["warnings"])
        with self.assertRaises(AgentError):
            self.service.execute(SESSION, plan["id"])
        self.assertEqual(self.service.state(SESSION)["notes"], [])

    def test_overwrite_risk_matches_operating_system_filename_casing(self):
        self.run_plan("Create note Exam.md: Original")
        plan = self.plan("Create note exam.md: Changed")
        self.assertEqual(bool(plan["warnings"]), os.path.normcase("Exam.md") == os.path.normcase("exam.md"))

    def test_replay_is_rejected_even_concurrently(self):
        plan = self.plan("Add task: One task")
        outcomes = []
        def run():
            try:
                outcomes.append(self.service.execute(SESSION, plan["id"])["status"])
            except AgentError:
                outcomes.append("rejected")
        threads = [threading.Thread(target=run) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertCountEqual(outcomes, ["completed", "rejected"])
        self.assertEqual(len(self.service.state(SESSION)["tasks"]), 1)

    def test_sessions_are_isolated(self):
        plan = self.plan("Add task: Private")
        with self.assertRaises(AgentError):
            self.service.execute(OTHER, plan["id"])
        self.service.execute(SESSION, plan["id"])
        self.assertEqual(self.service.state(OTHER)["tasks"], [])

    def test_cancel_and_expiry(self):
        plan = self.plan("Add task: Never")
        self.service.execute(SESSION, plan["id"], cancel=True)
        with self.assertRaises(AgentError):
            self.service.execute(SESSION, plan["id"])
        plan = self.plan("Add task: Expired")
        with closing(self.service.connect(SESSION)) as conn:
            conn.execute("UPDATE plans SET created=? WHERE id=?", (time.time() - 901, plan["id"]))
            conn.commit()
        with self.assertRaisesRegex(AgentError, "expired"):
            self.service.execute(SESSION, plan["id"])
        self.assertEqual(self.service.state(SESSION)["tasks"], [])

    def test_partial_failure_stops_remaining_actions(self):
        result = self.run_plan("Add task: Persist; Read note missing.md; Add task: Skipped")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["skipped"], 1)
        self.assertEqual([t["title"] for t in self.service.state(SESSION)["tasks"]], ["Persist"])

    def test_changed_workspace_invalidates_risk_preview(self):
        plan = self.plan("Create note a.md: original plan")
        self.run_plan("Create note a.md: another plan")
        with self.assertRaisesRegex(AgentError, "workspace changed"):
            self.service.execute(SESSION, plan["id"], True)

    def test_task_completion_and_deletion(self):
        self.run_plan("Add task: First")
        self.run_plan("Complete task 1")
        self.assertEqual(self.service.state(SESSION)["tasks"][0]["done"], 1)
        self.run_plan("Delete task 1", True)
        self.assertEqual(self.service.state(SESSION)["tasks"], [])

    def test_audit_does_not_copy_note_content(self):
        self.run_plan("Create note a.md: SECRET_NOTE_BODY")
        self.assertNotIn("SECRET_NOTE_BODY", json.dumps(self.service.state(SESSION)["audit"]))

    def test_invalid_plan_is_audited(self):
        with self.assertRaises(AgentError):
            self.plan("Calculate __import__('os')")
        self.assertEqual(self.service.state(SESSION)["audit"][0]["event"], "plan.rejected")

    def test_rate_limit(self):
        for _ in range(10):
            self.plan("List notes")
        with self.assertRaisesRegex(AgentError, "wait a minute"):
            self.plan("List notes")


class LLMTests(unittest.TestCase):
    def response(self, value=None, **kwargs):
        plan = value or {"summary": "List your notes", "actions": [{"tool": "note.list", "arguments": {}}]}
        body = {"status": "completed", "output": [{"content": [{"type": "output_text", "text": json.dumps(plan)}]}]}
        body.update(kwargs)
        return io.BytesIO(json.dumps(body).encode())

    def test_real_api_payload_and_response_parser(self):
        captured = []
        def opener(request, **kwargs):
            captured.append(request)
            return self.response()
        planner = OpenAIPlanner("test-key", opener=opener)
        self.assertEqual(planner.plan("List notes", {"notes": []})["actions"][0]["tool"], "note.list")
        payload = json.loads(captured[0].data)
        self.assertTrue(payload["text"]["format"]["strict"])
        self.assertFalse(payload["store"])
        self.assertEqual(captured[0].full_url, "https://api.openai.com/v1/responses")

    def test_retry_after_rate_limit(self):
        calls, sleeps = [], []
        def opener(*args, **kwargs):
            calls.append(1)
            if len(calls) < 3:
                raise HTTPError("url", 429, "rate limit", {"Retry-After": "2"}, None)
            return self.response()
        planner = OpenAIPlanner("key", opener=opener, sleeper=sleeps.append)
        planner.plan("List notes", {})
        self.assertEqual(sleeps, [2, 2])
        self.assertEqual(len(calls), 3)

    def test_auth_failure_is_not_retried_or_leaked(self):
        def opener(*args, **kwargs):
            raise HTTPError("url", 401, "secret provider details", {}, None)
        sleeps = []
        planner = OpenAIPlanner("SECRET", opener=opener, sleeper=sleeps.append)
        with self.assertRaises(AgentError) as caught:
            planner.plan("List notes", {})
        self.assertNotIn("SECRET", str(caught.exception))
        self.assertEqual(sleeps, [])

    def test_transport_retries_are_bounded(self):
        calls = []
        def opener(*args, **kwargs):
            calls.append(1)
            raise URLError("timeout")
        with self.assertRaises(AgentError):
            OpenAIPlanner("key", opener=opener, sleeper=lambda _: None).plan("List notes", {})
        self.assertEqual(len(calls), 3)

    def test_rejects_refusal_incomplete_malformed_and_unsafe_output(self):
        values = [self.response(status="incomplete"),
                  self.response(output=[{"content": [{"type": "refusal"}]}]),
                  io.BytesIO(b"not json"),
                  self.response({"summary": "Run shell", "actions": [{"tool": "shell.run", "arguments": {}}]})]
        for response in values:
            with self.subTest(response=response), self.assertRaises(AgentError):
                OpenAIPlanner("key", opener=lambda *a, **k: response).plan("test", {})

    def test_no_api_key(self):
        with self.assertRaisesRegex(AgentError, "not configured"):
            OpenAIPlanner("").plan("List notes", {})


class WebTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        with patch.dict(os.environ, {"APP_PASSWORD": ""}):
            self.app = create_app(self.tmp.name)
        self.cookie = ""

    def tearDown(self):
        self.tmp.cleanup()

    def request(self, path="/api/state", payload=None, **extra):
        encoded = json.dumps(payload).encode() if payload is not None else b""
        env = {"PATH_INFO": path, "REQUEST_METHOD": "POST" if payload is not None else "GET",
               "CONTENT_TYPE": "application/json", "CONTENT_LENGTH": str(len(encoded)),
               "wsgi.input": io.BytesIO(encoded), "HTTP_HOST": "localhost:8000",
               "HTTP_COOKIE": self.cookie, "wsgi.url_scheme": "http", **extra}
        capture = {}
        def start(status, headers):
            capture.update(status=status, headers=dict(headers))
        body = b"".join(self.app(env, start))
        if "Set-Cookie" in capture["headers"]:
            self.cookie = capture["headers"]["Set-Cookie"].split(";")[0]
        return capture, body

    def test_http_plan_and_execute(self):
        response, _ = self.request()
        self.assertIn("HttpOnly", response["headers"]["Set-Cookie"])
        response, body = self.request("/api/plan", {"mode": "demo", "prompt": "Add task: HTTP task"})
        self.assertTrue(response["status"].startswith("200"))
        response, body = self.request("/api/execute", {"plan_id": json.loads(body)["id"]})
        self.assertEqual(json.loads(body)["status"], "completed")
        self.assertIn("Content-Security-Policy", response["headers"])

    def test_cross_origin_non_json_and_oversized_are_rejected(self):
        response, _ = self.request("/api/plan", {}, HTTP_ORIGIN="https://evil.example")
        self.assertTrue(response["status"].startswith("403"))
        response, _ = self.request("/api/plan", {}, CONTENT_TYPE="text/plain")
        self.assertTrue(response["status"].startswith("415"))
        response, _ = self.request("/api/plan", {}, CONTENT_LENGTH="99999")
        self.assertTrue(response["status"].startswith("413"))

    def test_invalid_json_unknown_routes_and_static_traversal(self):
        response, _ = self.request("/api/plan", {}, **{"wsgi.input": io.BytesIO(b"{{")})
        self.assertTrue(response["status"].startswith("400"))
        response, _ = self.request("/../app.py")
        self.assertTrue(response["status"].startswith("404"))

    def test_basic_auth_and_health(self):
        with patch.dict(os.environ, {"APP_PASSWORD": "test-password"}):
            self.app = create_app(self.tmp.name)
        response, _ = self.request()
        self.assertTrue(response["status"].startswith("401"))
        header = "Basic " + base64.b64encode(b"studydesk:test-password").decode()
        response, _ = self.request(HTTP_AUTHORIZATION=header)
        self.assertTrue(response["status"].startswith("200"))
        response, _ = self.request("/health")
        self.assertTrue(response["status"].startswith("200"))


if __name__ == "__main__":
    unittest.main()
