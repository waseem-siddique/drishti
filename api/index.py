"""Vercel entry point: exposes the DRISHTI API as a serverless function.

Vercel's filesystem is read-only except /tmp, so the SQLite database lives in
/tmp and is (re)built from the deterministic seed on every cold start.
"""
import os
import sys

os.environ.setdefault("DRISHTI_DATA_DIR", "/tmp/drishti-data")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

import app as _app  # noqa: E402

_app.bootstrap(False)


class handler(_app.Handler):
    pass
