"""Small WSGI API with same-origin JSON requests and isolated browser sessions."""
import base64
import hmac
import json
import logging
import os
import secrets
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import urlsplit

from .service import AgentService
from .tools import AgentError

STATIC = Path(__file__).parent / "static"


def create_app(data_dir=None, planner=None):
    service = AgentService(data_dir or os.environ.get("DATA_DIR", "data"), planner=planner)
    password = os.environ.get("APP_PASSWORD", "")

    def app(environ, start_response):
        path = environ.get("PATH_INFO", "/")
        headers = [("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff"),
                   ("Referrer-Policy", "no-referrer"),
                   ("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")]

        def send(status, value, content_type="application/json; charset=utf-8"):
            data = json.dumps(value).encode() if content_type.startswith("application/json") else value
            start_response(status, headers + [("Content-Type", content_type), ("Content-Length", str(len(data)))])
            return [data]

        if path == "/health" and environ["REQUEST_METHOD"] == "GET":
            return send("200 OK", {"status": "ok"})
        if password:
            try:
                scheme, encoded = environ.get("HTTP_AUTHORIZATION", "").split(" ", 1)
                user, supplied = base64.b64decode(encoded, validate=True).decode().split(":", 1)
                authenticated = scheme.lower() == "basic" and user == "studydesk" and hmac.compare_digest(supplied.encode(), password.encode())
            except (ValueError, UnicodeError):
                authenticated = False
            if not authenticated:
                headers.append(("WWW-Authenticate", 'Basic realm="StudyDesk", charset="UTF-8"'))
                return send("401 Unauthorized", {"error": "Sign in with username studydesk and your application password."})
        cookie = SimpleCookie()
        try:
            cookie.load(environ.get("HTTP_COOKIE", ""))
            session = cookie["studydesk_session"].value if "studydesk_session" in cookie else ""
        except Exception:
            session = ""
        if len(session) != 32 or any(c not in "0123456789abcdef" for c in session):
            session = secrets.token_hex(16)
            secure = "; Secure" if environ.get("wsgi.url_scheme") == "https" or environ.get("HTTP_X_FORWARDED_PROTO") == "https" else ""
            headers.append(("Set-Cookie", f"studydesk_session={session}; Path=/; HttpOnly; SameSite=Strict{secure}"))
        method = environ["REQUEST_METHOD"]
        if method == "GET" and path in ("/", "/app.js", "/style.css"):
            filename, mime = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
                              "/style.css": ("style.css", "text/css")}[path]
            return send("200 OK", (STATIC / filename).read_bytes(), mime + "; charset=utf-8")
        try:
            if method == "GET" and path == "/api/state":
                return send("200 OK", service.state(session))
            if path not in ("/api/plan", "/api/execute", "/api/cancel"):
                return send("404 Not Found", {"error": "Route not found."})
            if method != "POST":
                return send("405 Method Not Allowed", {"error": "This route requires POST."})
            origin = environ.get("HTTP_ORIGIN")
            if origin and urlsplit(origin).netloc != environ.get("HTTP_HOST"):
                return send("403 Forbidden", {"error": "Cross-origin requests are not permitted."})
            if environ.get("CONTENT_TYPE", "").split(";")[0].strip() != "application/json":
                return send("415 Unsupported Media Type", {"error": "Send an application/json request."})
            try:
                length = int(environ.get("CONTENT_LENGTH") or 0)
            except ValueError:
                length = -1
            if not 0 < length <= 20000:
                return send("413 Payload Too Large", {"error": "The request must be between 1 and 20,000 bytes."})
            payload = json.loads(environ["wsgi.input"].read(length))
            if not isinstance(payload, dict):
                raise AgentError("The request must be a JSON object.")
            if path == "/api/plan":
                value = service.preview(session, payload.get("prompt"), payload.get("mode", "demo"))
            else:
                value = service.execute(session, payload.get("plan_id"), payload.get("confirmed", False),
                                        cancel=path == "/api/cancel")
            return send("200 OK", value)
        except (AgentError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            message = str(exc) if isinstance(exc, AgentError) else "The request is not valid JSON."
            return send("400 Bad Request", {"error": message})
        except Exception:
            logging.exception("Unexpected server error")
            return send("500 Internal Server Error", {"error": "The server could not complete this request. Check server logs."})

    app.service = service
    return app
