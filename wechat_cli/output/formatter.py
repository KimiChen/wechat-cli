"""Output helpers for JSON and plain text."""

import json
import os
import sys


def _prepare_stream(file):
    file = file or sys.stdout
    if os.name == "nt" and file in (sys.stdout, sys.stderr):
        reconfigure = getattr(file, "reconfigure", None)
        if reconfigure:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass
    return file


def _write_text(file, text):
    file = _prepare_stream(file)
    try:
        file.write(text)
    except UnicodeEncodeError:
        encoding = getattr(file, "encoding", None) or "utf-8"
        buffer = getattr(file, "buffer", None)
        data = text.encode(encoding, errors="replace")
        if buffer is not None:
            buffer.write(data)
        else:
            file.write(data.decode(encoding, errors="replace"))
    flush = getattr(file, "flush", None)
    if flush:
        flush()


def output_json(data, file=None):
    rendered = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    _write_text(file or sys.stdout, rendered)


def output_text(text, file=None):
    rendered = text if text.endswith("\n") else text + "\n"
    _write_text(file or sys.stdout, rendered)


def output(data, fmt="json", file=None):
    if fmt == "json":
        output_json(data, file)
    else:
        if isinstance(data, str):
            output_text(data, file)
        elif isinstance(data, dict) and "text" in data:
            output_text(data["text"], file)
        else:
            output_json(data, file)
