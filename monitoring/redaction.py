"""Pluggable redaction layer for span attributes and logs. Defence-in-depth; primary PII pipeline is libs/dlp.py."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Pattern

DEFAULT_RULES: list[tuple[Pattern[str], str]] = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "<email>"),
    # Card must come before phone: phone regex would otherwise consume 4-digit groups inside a card number.
    (re.compile(r"\b(?:\d[ -]*?){13,19}\b"), "<card>"),
    (re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?(?:\(\d{2,4}\)[-.\s]?)?\d{3,4}[-.\s]?\d{3,4}\b"), "<phone>"),
    (re.compile(r"eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}"), "<jwt>"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "<aws-access-key>"),
    (re.compile(r"(?i)bearer\s+[a-zA-Z0-9._\-]+"), "Bearer <token>"),
    (re.compile(r"sk-[a-zA-Z0-9]{20,}"), "<openai-key>"),
]


@dataclass
class Redactor:
    rules: list[tuple[Pattern[str], str]] = field(default_factory=lambda: list(DEFAULT_RULES))
    enabled: bool = True

    def redact(self, text: str | None) -> str:
        if not text or not self.enabled:
            return text or ""
        out = text
        for pattern, repl in self.rules:
            out = pattern.sub(repl, out)
        return out

    def add_rule(self, pattern: str | Pattern[str], replacement: str) -> "Redactor":
        compiled = re.compile(pattern) if isinstance(pattern, str) else pattern
        self.rules.append((compiled, replacement))
        return self

    def extend(self, rules: Iterable[tuple[Pattern[str], str]]) -> "Redactor":
        self.rules.extend(rules)
        return self


def default_redactor() -> Redactor:
    from libs.config import get_settings
    return Redactor(enabled=get_settings().observability_redact_pii)