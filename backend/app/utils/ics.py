"""Minimal RFC 5545 (iCalendar) writer: escaping, line folding, serialisation."""

from __future__ import annotations

import datetime
import unicodedata

CRLF = "\r\n"
MAX_OCTETS = 75


_FORBIDDEN_CATEGORIES = {"Cc", "Cf", "Cs", "Co", "Zl", "Zp"}
_ALLOWED_FORMAT_CHARS = {"\u200d"}  # zero-width joiner, needed by compound emoji


def is_forbidden_char(ch: str) -> bool:
    """Control, format (incl. bidi overrides), surrogate, private-use or line-
    separator characters. Only the emoji joiner U+200D is let through."""
    if ch in _ALLOWED_FORMAT_CHARS:
        return False
    return unicodedata.category(ch) in _FORBIDDEN_CATEGORIES


def has_forbidden_chars(value: str) -> bool:
    return any(is_forbidden_char(ch) for ch in value)


def escape_text(value: str) -> str:
    """Escape a TEXT value (RFC 5545 3.3.11): backslash, semicolon, comma, newline."""
    value = value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
    value = value.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n")
    return "".join(ch for ch in value if not is_forbidden_char(ch))


def fold_line(line: str) -> list[str]:
    """Fold a content line to at most 75 octets per physical line (UTF-8 safe).

    Continuation lines start with one space, which counts towards the 75 octets.
    A multi-byte character is never split across lines.
    """
    out: list[str] = []
    current: list[str] = []
    size = 0
    limit = MAX_OCTETS
    for ch in line:
        n = len(ch.encode("utf-8"))
        if size + n > limit:
            out.append("".join(current))
            current = [" "]
            size = 1
            limit = MAX_OCTETS
        current.append(ch)
        size += n
    out.append("".join(current))
    return out


def date_value(d: datetime.date) -> str:
    return d.strftime("%Y%m%d")


def datetime_utc_value(dt: datetime.datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%SZ")


def serialize(lines: list[str]) -> str:
    """Join logical content lines into CRLF-terminated, folded iCalendar text."""
    folded: list[str] = []
    for line in lines:
        folded.extend(fold_line(line))
    return CRLF.join(folded) + CRLF
