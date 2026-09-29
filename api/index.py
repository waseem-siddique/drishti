"""Vercel entry point: exposes the DRISHTI API as a serverless function.

Vercel's filesystem is read-only except /tmp, so the SQLite database lives in
/tmp and is (re)built from the deterministic seed on cold start.
If start-up fails, every request returns the error as JSON (see /api/health).
"""
import json
import os
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler

os.environ.setdefault("DRISHTI_DATA_DIR", "/tmp/drishti-data")
sys.dont_write_bytecode = True
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

_lock = threading.Lock()
_state = {"ready": False, "error": None, "app": None}


def _init():
    with _lock:
        if _state["ready"]:
            return
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "drishti_app", os.path.join(ROOT, "backend", "app.py"))
            _app = importlib.util.module_from_spec(spec)
            sys.modules["drishti_app"] = _app
            spec.loader.exec_module(_app)
            _app.bootstrap(False)
            _state["app"] = _app
            _state["error"] = None
            _state["ready"] = True
        except Exception:
            _state["error"] = traceback.format_exc()


_init()


_Base = _state["app"].Handler if _state["ready"] else BaseHTTPRequestHandler


class handler(_Base):
    def _fail(self):
        body = json.dumps({"error": "startup failed", "trace": _state["error"]}).encode()
        self.send_response(500)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _guard(self, name):
        if not _state["ready"]:
            return self._fail()
        try:
            getattr(_Base, name)(self)
        except Exception:
            self._fail()

    def do_GET(self): self._guard("do_GET")
    def do_HEAD(self): self._guard("do_HEAD")
    def do_POST(self): self._guard("do_POST")
