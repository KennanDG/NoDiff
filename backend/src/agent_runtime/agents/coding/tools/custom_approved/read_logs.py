"""Log-reading utilities for the coding agent.

Public entry point: :func:`read_logs`.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

try:  # pragma: no cover - depends on the runtime package layout
    from agent_runtime.agents.coding.tools.filesystem import resolve_in_repo
except Exception:  # pragma: no cover - fall back to plain path handling
    resolve_in_repo = None  # type: ignore[assignment]

__all__ = ["read_logs"]

DEFAULT_MAX_LINES = 200
HARD_MAX_LINES = 5000
DEFAULT_MAX_BYTES = 4 * 1024 * 1024
MIN_MAX_BYTES = 4096
MAX_MAX_BYTES = 64 * 1024 * 1024
DEFAULT_MAX_LINE_LENGTH = 400
MAX_CONTEXT = 25

LEVEL_ORDER = ("TRACE", "DEBUG", "INFO", "WARN", "ERROR", "CRITICAL")
CANONICAL_LEVELS = frozenset(LEVEL_ORDER) | {"UNKNOWN"}

_LEVEL_ALIASES = {
    "trace": "TRACE",
    "verbose": "TRACE",
    "debug": "DEBUG",
    "dbg": "DEBUG",
    "fine": "DEBUG",
    "info": "INFO",
    "information": "INFO",
    "notice": "INFO",
    "warn": "WARN",
    "warning": "WARN",
    "error": "ERROR",
    "err": "ERROR",
    "severe": "ERROR",
    "fatal": "CRITICAL",
    "critical": "CRITICAL",
    "crit": "CRITICAL",
    "panic": "CRITICAL",
    "emerg": "CRITICAL",
    "emergency": "CRITICAL",
    "alert": "CRITICAL",
}

_JSON_LEVEL_KEYS = frozenset(
    {
        "level",
        "lvl",
        "severity",
        "severity_text",
        "severitytext",
        "levelname",
        "level_name",
        "log_level",
        "loglevel",
        "log.level",
    }
)

_LEVEL_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_])"
    r"(TRACE|DEBUG|INFO|NOTICE|WARNING|WARN|ERROR|ERR|FATAL|CRITICAL|CRIT|PANIC|SEVERE|ALERT|EMERG)"
    r"\b",
    re.IGNORECASE,
)
_FIRST_TOKEN_RE = re.compile(r'[\s\[\(\{<"|#*\-]*(?P<token>[A-Za-z]+)')
_LOGFMT_LEVEL_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:level|lvl|severity|loglevel|levelname|log\.level)"
    r'=[\"\']?(?P<lvl>[A-Za-z]+)',
    re.IGNORECASE,
)
_TIMESTAMP_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d{1,6})?(?:Z|[+-]\d{2}:?\d{2})?"
)


def _clamp_int(value: Any, default: int, low: int, high: int, name: str, warnings: list) -> int:
    """Coerce ``value`` to an int inside ``[low, high]``, recording any adjustment."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        warnings.append(name + " is not an integer; using default " + str(default))
        return default
    clamped = max(low, min(high, number))
    if clamped != number:
        warnings.append(name + "=" + str(number) + " clamped to " + str(clamped))
    return clamped


def _resolve_path(path: str) -> Path:
    """Resolve ``path`` through the repository sandbox when the tool package is available."""
    if resolve_in_repo is not None:
        try:
            resolved = resolve_in_repo(path)
        except Exception as exc:  # rejected by the sandbox, or otherwise unusable
            raise ValueError(str(exc)) from exc
        if isinstance(resolved, (str, os.PathLike)):
            return Path(resolved)
    return Path(path)


def _read_window(path: Path, size: int, *, tail: bool, max_bytes: int) -> tuple:
    """Read at most ``max_bytes`` from the head or the tail of ``path``.

    Returns ``(data, truncated)`` where ``truncated`` is True when the whole file did
    not fit inside the requested window.
    """
    if size <= max_bytes:
        with path.open("rb") as handle:
            return handle.read(), False
    with path.open("rb") as handle:
        if tail:
            handle.seek(size - max_bytes)
            data = handle.read()
            newline = data.find(b"\n")
            if newline != -1:
                data = data[newline + 1:]
            return data, True
        data = handle.read(max_bytes)
        cut = data.rfind(b"\n")
        if cut > 0:
            data = data[:cut]
        return data, True


def _level_from_number(value: float) -> str:
    """Map syslog/bunyan/pino style numeric severities onto canonical levels."""
    if value >= 60:
        return "CRITICAL"
    if value >= 50:
        return "ERROR"
    if value >= 40:
        return "WARN"
    if value >= 30:
        return "INFO"
    if value >= 20:
        return "DEBUG"
    return "TRACE"


def _level_from_json(text: str) -> str:
    """Best-effort level extraction from a single JSON log line (empty string if none)."""
    if len(text) > 8192:
        return ""
    try:
        payload = json.loads(text)
    except (ValueError, TypeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    for key, value in payload.items():
        if not isinstance(key, str) or key.strip().lower() not in _JSON_LEVEL_KEYS:
            continue
        if isinstance(value, str):
            level = _LEVEL_ALIASES.get(value.strip().lower())
            if level:
                return level
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            return _level_from_number(float(value))
    return ""


def _detect_level(line: str) -> str:
    """Infer the severity of a log line, returning ``UNKNOWN`` when unclear."""
    stripped = line.strip()
    if stripped.startswith("{"):
        level = _level_from_json(stripped)
        if level:
            return level
    match = _LOGFMT_LEVEL_RE.search(line)
    if match:
        level = _LEVEL_ALIASES.get(match.group("lvl").lower())
        if level:
            return level
    match = _FIRST_TOKEN_RE.match(line)
    if match:
        level = _LEVEL_ALIASES.get(match.group("token").lower())
        if level:
            return level
    match = _LEVEL_TOKEN_RE.search(line)
    if match:
        return _LEVEL_ALIASES.get(match.group(1).lower(), "UNKNOWN")
    return "UNKNOWN"


def _normalize_levels(levels: Any) -> tuple:
    """Normalise a level filter into ``(frozenset_or_None, unknown_names)``."""
    if levels is None:
        return None, []
    if isinstance(levels, str):
        parts = re.split(r"[,\s|]+", levels)
    else:
        try:
            parts = [str(item) for item in levels]
        except TypeError:
            return None, [repr(levels)]
    accepted = set()
    unknown = []
    for part in parts:
        name = part.strip()
        if not name:
            continue
        canonical = _LEVEL_ALIASES.get(name.lower())
        if canonical is None and name.upper() in CANONICAL_LEVELS:
            canonical = name.upper()
        if canonical is None:
            unknown.append(name)
        else:
            accepted.add(canonical)
    if not accepted:
        return None, unknown
    return frozenset(accepted), unknown


def _ordered_counts(counts: Counter) -> dict:
    """Return level counts ordered by severity, then alphabetically."""

    def sort_key(item):
        name = item[0]
        rank = LEVEL_ORDER.index(name) if name in LEVEL_ORDER else len(LEVEL_ORDER)
        return (rank, name)

    return {name: count for name, count in sorted(counts.items(), key=sort_key)}


def read_logs(
    path: str,
    max_lines: int = DEFAULT_MAX_LINES,
    tail: bool = True,
    pattern: str = None,
    levels: Any = None,
    context: int = 0,
    ignore_case: bool = True,
    max_line_length: int = DEFAULT_MAX_LINE_LENGTH,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> dict:
    """Read a log file and return filtered, annotated lines.

    Args:
        path: Log file path, resolved through the repository sandbox when available.
        max_lines: Maximum number of matching lines to return (1-5000, default 200).
        tail: When True (default) the end of the file is scanned and the most recent
            matches are returned; when False the scan starts at the beginning.
        pattern: Optional regular expression; only matching lines are returned.
        levels: Optional severity filter, e.g. ``"error,warn"`` or ``["ERROR", "WARN"]``.
            Aliases such as ``warning``, ``err`` and ``fatal`` are normalised.
        context: Number of surrounding non-matching lines to include per match (0-25).
        ignore_case: Use case-insensitive pattern matching (default True).
        max_line_length: Long lines are truncated to this many characters.
        max_bytes: Maximum bytes read from the file window (default 4 MiB).

    Returns:
        A dictionary with ``ok`` and, on success, ``entries`` (``line``, ``level``,
        ``text``, ``is_match`` plus an optional ``timestamp``), ``level_counts``,
        ``matched_lines``, ``returned_lines``, ``scan_truncated``, ``results_truncated``,
        ``line_numbers_are_absolute`` and the first/last timestamps seen. Failures
        return ``ok`` False together with an ``error`` message.
    """
    warnings = []
    result = {"ok": False, "path": path}

    if not isinstance(path, str) or not path.strip():
        result["error"] = "path must be a non-empty string"
        return result

    max_lines_i = _clamp_int(max_lines, DEFAULT_MAX_LINES, 1, HARD_MAX_LINES, "max_lines", warnings)
    context_i = _clamp_int(context, 0, 0, MAX_CONTEXT, "context", warnings)
    max_line_i = _clamp_int(
        max_line_length, DEFAULT_MAX_LINE_LENGTH, 40, 10000, "max_line_length", warnings
    )
    max_bytes_i = _clamp_int(
        max_bytes, DEFAULT_MAX_BYTES, MIN_MAX_BYTES, MAX_MAX_BYTES, "max_bytes", warnings
    )
    tail_flag = bool(tail)

    if pattern is not None and not isinstance(pattern, str):
        result["error"] = "pattern must be a string"
        return result
    pattern_re = None
    if pattern:
        try:
            pattern_re = re.compile(pattern, re.IGNORECASE if ignore_case else 0)
        except re.error as exc:
            result["error"] = "invalid regex pattern: " + str(exc)
            return result

    levels_filter, unknown_levels = _normalize_levels(levels)
    if unknown_levels:
        warnings.append("ignored unknown level(s): " + ", ".join(sorted(set(unknown_levels))))

    try:
        target = _resolve_path(path)
    except Exception as exc:
        result["error"] = "could not resolve path: " + str(exc)
        return result

    try:
        if not target.exists():
            result["error"] = "file not found: " + path
            return result
        if target.is_dir():
            result["error"] = path + " is a directory; pass a specific log file"
            return result
        size = target.stat().st_size
        data, scan_truncated = _read_window(
            target, size, tail=tail_flag, max_bytes=max_bytes_i
        )
    except OSError as exc:
        result["error"] = "could not read " + path + ": " + str(exc)
        return result

    absolute_numbers = (not tail_flag) or (not scan_truncated)
    if not absolute_numbers:
        warnings.append(
            "line numbers are relative to the tail window, not the start of the file"
        )

    raw_lines = data.decode("utf-8", errors="replace").splitlines()

    level_counts = Counter()
    matched_counts = Counter()
    levels_by_index = []
    matched_indexes = []

    for index, raw in enumerate(raw_lines):
        line = raw.rstrip("\r")
        level = _detect_level(line)
        levels_by_index.append(level)
        level_counts[level] += 1
        if levels_filter is not None and level not in levels_filter:
            continue
        if pattern_re is not None and pattern_re.search(line) is None:
            continue
        matched_counts[level] += 1
        matched_indexes.append(index)

    total_matches = len(matched_indexes)
    if tail_flag:
        selected = matched_indexes[-max_lines_i:]
    else:
        selected = matched_indexes[:max_lines_i]
    results_truncated = total_matches > len(selected)

    keep = set()
    for position in selected:
        start = max(0, position - context_i)
        end = min(len(raw_lines), position + context_i + 1)
        keep.update(range(start, end))
    selected_set = set(selected)

    entries = []
    first_timestamp = None
    last_timestamp = None
    for index in sorted(keep):
        line = raw_lines[index].rstrip("\r")
        display = line
        truncated_text = False
        if len(display) > max_line_i:
            display = display[:max_line_i] + "..."
            truncated_text = True
        found = _TIMESTAMP_RE.search(line)
        timestamp = found.group(0) if found else None
        if timestamp:
            if first_timestamp is None:
                first_timestamp = timestamp
            last_timestamp = timestamp
        entry = {
            "line": index + 1,
            "level": levels_by_index[index],
            "text": display,
            "is_match": index in selected_set,
        }
        if timestamp:
            entry["timestamp"] = timestamp
        if truncated_text:
            entry["text_truncated"] = True
        entries.append(entry)

    result.update(
        {
            "ok": True,
            "resolved_path": str(target),
            "file_size_bytes": size,
            "scanned_bytes": len(data),
            "scanned_lines": len(raw_lines),
            "matched_lines": total_matches,
            "returned_lines": len(entries),
            "scan_truncated": scan_truncated,
            "results_truncated": results_truncated,
            "line_numbers_are_absolute": absolute_numbers,
            "level_counts": _ordered_counts(level_counts),
            "matched_level_counts": _ordered_counts(matched_counts),
            "first_timestamp": first_timestamp,
            "last_timestamp": last_timestamp,
            "entries": entries,
        }
    )
    if warnings:
        result["warnings"] = warnings
    return result
