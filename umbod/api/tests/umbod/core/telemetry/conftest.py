import io
import logging
import sys
from collections.abc import Iterator

import pytest
from pytest import MonkeyPatch

from umbod.logging import configure_logging


@pytest.fixture
def stdout_stream(monkeypatch: MonkeyPatch) -> Iterator[io.StringIO]:
    root = logging.getLogger()
    previous_level = root.level
    structured = logging.getLogger("umbod.structured")
    previous_structured_level = structured.level
    monkeypatch.setattr(root, "handlers", [])
    monkeypatch.setattr(structured, "handlers", [])
    monkeypatch.setattr(structured, "filters", [])
    monkeypatch.setattr(structured, "disabled", False)
    monkeypatch.setattr(structured, "propagate", True)
    structured.setLevel(logging.NOTSET)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastmcp", "mcp"):
        logger = logging.getLogger(name)
        monkeypatch.setattr(logger, "handlers", list(logger.handlers))
        monkeypatch.setattr(logger, "propagate", logger.propagate)
    stream = io.StringIO()
    monkeypatch.setattr(sys, "stdout", stream)
    configure_logging("ingestion-test", "info")
    try:
        yield stream
    finally:
        root.setLevel(previous_level)
        structured.setLevel(previous_structured_level)
