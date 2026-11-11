"""Run with Python's local server, or use waitress for hosted deployment."""
import argparse
import logging
import os
from wsgiref.simple_server import make_server

from studydesk.web import create_app


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="StudyDesk AI agent")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    parser.add_argument("--data-dir", default=os.environ.get("DATA_DIR", "data"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    application = create_app(args.data_dir)
    print(f"StudyDesk: http://{args.host}:{args.port} (Ctrl+C to stop)", flush=True)
    try:
        from waitress import serve
    except ImportError:
        with make_server(args.host, args.port, application) as server:
            server.serve_forever()
    else:
        serve(application, host=args.host, port=args.port, threads=4)
