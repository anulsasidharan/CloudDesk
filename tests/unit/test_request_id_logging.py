"""N3: the request id reaches JSON log lines emitted during the request."""

import io
import json
import logging

from app.core.logging import setup_logging
from app.middleware.request_id import RequestIdMiddleware
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_request_id_in_log_line():
    stream = io.StringIO()
    setup_logging(stream=stream)
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)

    @app.get("/x")
    async def x():
        logging.getLogger("t").info("inside")
        return {}

    TestClient(app).get("/x", headers={"X-Request-ID": "rid-9"})
    lines = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert any(line["message"] == "inside" and line["request_id"] == "rid-9" for line in lines)
