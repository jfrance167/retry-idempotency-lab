"""Reviewed local bounded JSON/exclusive output, reused from our timeline lab."""
import json
import os
import tempfile
import unicodedata
from pathlib import Path

MAX_BYTES = 65536
MAX_DEPTH = 12
MAX_NUMBER = 20
MAX_STRING = 256
MAX_OUTPUT = 1048576


class InputError(ValueError):
    """Fixed, data-redacted validation failure."""


class OutputCleanupError(OSError):
    def __init__(self, published):
        super().__init__("temporary cleanup failed")
        self.published = published


def _scan(text):
    depth = number = 0
    inside = escaped = False
    for char in text:
        if inside:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                inside = False
            continue
        if char == '"':
            inside = True
        if char in "[{":
            depth += 1
            if depth > MAX_DEPTH:
                raise InputError("JSON nesting limit exceeded")
        elif char in "]}":
            depth -= 1
        if char in "0123456789.eE+-":
            number += 1
            if number > MAX_NUMBER:
                raise InputError("numeric token limit exceeded")
        else:
            number = 0


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InputError("duplicate JSON field")
        result[key] = value
    return result


def _unsupported_number(_value):
    raise InputError("floating-point and nonfinite numbers are unsupported")


def _strings(value):
    if type(value) is str:
        if len(value) > MAX_STRING or any(0xD800 <= ord(c) <= 0xDFFF for c in value):
            raise InputError("string limit exceeded or invalid Unicode scalar")
    elif type(value) is dict:
        for key, child in value.items():
            _strings(key)
            _strings(child)
    elif type(value) is list:
        for child in value:
            _strings(child)


def decode(raw):
    """Predecode byte/depth/token admission; cardinality is checked after decoding."""
    if type(raw) is not bytes or len(raw) > MAX_BYTES:
        raise InputError("input byte limit exceeded or invalid bytes")
    try:
        text = raw.decode("utf-8", errors="strict")
        _scan(text)
        data = json.loads(text, object_pairs_hook=_pairs, parse_float=_unsupported_number, parse_constant=_unsupported_number)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise InputError("invalid UTF-8 JSON") from exc
    _strings(data)
    return data


def fields(value, required):
    if type(value) is not dict or set(value) != set(required):
        raise InputError("object fields do not match schema")


def visible(value):
    return "".join(" " if unicodedata.category(c).startswith("C") else c for c in value)


def markdown(value):
    return "".join(c if c.isalnum() or c == " " else f"&#{ord(c)};" for c in visible(value))


def write_new(path, raw, *, input_path=None):
    """Flush sibling bytes, then publish exclusively; never replace any output."""
    if type(raw) is not bytes or len(raw) > MAX_OUTPUT:
        raise InputError("output byte limit exceeded or invalid bytes")
    target = Path(path)
    if input_path is not None and target.resolve() == Path(input_path).resolve():
        raise InputError("output aliases input")
    if os.path.lexists(target):
        raise InputError("output already exists; exclusive creation required")
    temporary = None
    published = False
    try:
        with tempfile.NamedTemporaryFile(prefix=".retry-report-", suffix=".tmp", dir=target.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, target)
        published = True
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError as exc:
                raise OutputCleanupError(published) from exc
