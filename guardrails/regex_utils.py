"""Regex patterns and text-redaction helpers shared across guardrail layers."""

import math
import re
from typing import Any, List


# Secret detection patterns — (compiled_pattern, type_label); more-specific patterns listed first.
SECRET_PATTERNS: List[tuple] = [
    (re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |DSA |)?PRIVATE KEY-----'), "PRIVATE_KEY"),
    (re.compile(r'\bAKIA[0-9A-Z]{16}\b'), "AWS_ACCESS_KEY"),
    (re.compile(r'\bAIza[0-9A-Za-z\-_]{35}\b'), "GOOGLE_API_KEY"),
    (re.compile(r'\bghp_[a-zA-Z0-9]{36}\b'), "GITHUB_PAT"),
    (re.compile(r'\bghs_[a-zA-Z0-9]{36}\b'), "GITHUB_APP_TOKEN"),
    (re.compile(r'\bsk-[a-zA-Z0-9]{48}\b'), "OPENAI_KEY"),
    (re.compile(r'\beyJ[A-Za-z0-9\-_=]{20,}\.eyJ[A-Za-z0-9\-_=]{20,}\.[A-Za-z0-9\-_.+/=]{10,}\b'), "JWT_TOKEN"),
    (re.compile(r'(?i)\bpassword\s*[:=]\s*\S{8,}'), "PASSWORD"),
    (re.compile(r'(?i)\bapi[_\-]?key\s*[:=]\s*["\']?\S{8,}'), "API_KEY"),
    (re.compile(r'(?i)\b(?:secret|token)\s*[:=]\s*["\']?\S{8,}'), "SECRET_TOKEN"),
    (re.compile(r'"private_key"\s*:\s*"-----BEGIN'), "GCP_SERVICE_ACCOUNT"),
    (re.compile(r'(?i)\bsv=\S+&se=\S+&sig=[A-Za-z0-9%+/=]{10,}'), "AZURE_SAS_TOKEN"),
    (re.compile(r'DefaultEndpointsProtocol=https;AccountName=\S+;AccountKey=[A-Za-z0-9+/=]{20,}'), "AZURE_STORAGE_KEY"),
    (re.compile(r'(?i)(?:postgresql|mysql|mongodb(?:\+srv)?|redis|mssql|mariadb)://[^:@\s]+:[^@\s]+@'), "DB_CONNECTION_STRING"),
    (re.compile(r'Bearer\s+[A-Za-z0-9\-_=.]{20,}'), "BEARER_TOKEN"),
    (re.compile(r'\bxoxb-[0-9]+-[0-9]+-[a-zA-Z0-9]{24,}\b'), "SLACK_BOT_TOKEN"),
    (re.compile(r'\bsk_live_[a-zA-Z0-9]{24,}\b'), "STRIPE_KEY"),
]

SECRET_TYPE_LABELS: dict = {
    "PRIVATE_KEY":           "Private Key (PEM format)",
    "AWS_ACCESS_KEY":        "AWS Access Key",
    "GOOGLE_API_KEY":        "Google API Key",
    "GITHUB_PAT":            "GitHub Personal Access Token",
    "GITHUB_APP_TOKEN":      "GitHub App Token",
    "OPENAI_KEY":            "OpenAI API Key",
    "JWT_TOKEN":             "JSON Web Token (JWT)",
    "PASSWORD":              "Password",
    "API_KEY":               "API Key",
    "SECRET_TOKEN":          "Secret / Token",
    "GCP_SERVICE_ACCOUNT":   "GCP Service Account Key",
    "AZURE_SAS_TOKEN":       "Azure SAS Token",
    "AZURE_STORAGE_KEY":     "Azure Storage Account Key",
    "DB_CONNECTION_STRING":  "Database Connection String",
    "BEARER_TOKEN":          "Bearer Token",
    "SLACK_BOT_TOKEN":       "Slack Bot Token",
    "STRIPE_KEY":            "Stripe API Key",
    "HIGH_ENTROPY_SECRET":   "High-entropy credential (unknown format)",
}


def describe_detected_secrets(found: List[str]) -> str:
    """Returns a comma-separated human-readable description of detected secret types."""
    labels = []
    for t in found:
        if t.startswith("HIGH_ENTROPY_SECRET:"):
            keyword = t.split(":", 1)[1]
            labels.append(f"High-entropy credential (found after keyword: '{keyword}')")
        else:
            labels.append(SECRET_TYPE_LABELS.get(t, t))
    return ", ".join(labels)

# ─── Jailbreak detection patterns (applied to input and tool responses) ────────

JAILBREAK_REGEX_PATTERNS: List[re.Pattern] = [
    re.compile(r"ignore\s+(?:all\s+|previous\s+|prior\s+|above\s+|your\s+)?(?:instructions?|rules?|guidelines?|constraints?|context|prompt)", re.I),
    re.compile(r"(?:forget|disregard|override|bypass|disable)\s+(?:your\s+|all\s+)?(?:instructions?|rules?|guidelines?|restrictions?|safety|constraints?|training)", re.I),
    re.compile(r"you\s+are\s+(?:now\s+)?(?:DAN\b|an?\s+AI\s+without|no\s+longer\s+bound)", re.I),
    re.compile(r"act\s+as\s+(?:if\s+)?(?:you\s+have\s+no\s+restrictions?|there\s+(?:are|is)\s+no\s+(?:rules?|restrictions?|limits?|constraints?))", re.I),
    re.compile(r"pretend\s+(?:you\s+(?:are|have)|there\s+(?:are|is)\s+no\s+(?:rules?|restrictions?|limits?))", re.I),
    re.compile(r"\bDAN\b"),
    re.compile(r"do\s+anything\s+now", re.I),
    re.compile(r"\bjailbreak\b", re.I),
    re.compile(r"\bdeveloper\s+mode\b", re.I),
    re.compile(r"(?:system|admin|root)\s+(?:prompt|override|command)", re.I),
    re.compile(r"<\|(?:im_start|im_end|endoftext|system)\|>"),
    re.compile(r"\[\[(?:SYSTEM|INST|HUMAN|ASSISTANT)\]\]", re.I),
    re.compile(r"prompt\s+injection", re.I),
]


# Entropy-based secret detection — context-anchored; only fires after keyword prefixes, not on IDs or URLs.

_ENTROPY_CONTEXT_RE = re.compile(
    r"(?i)(api[_\-]?key|secret[_\-]?key|secret|token|password|passwd|pwd"
    r"|credential|auth[_\-]?token|private[_\-]?key|access[_\-]?key)"
    r"\s*[:=]\s*[\"']?([A-Za-z0-9+/=\-_.~]{20,})"
)
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.I,
)
_ENTROPY_THRESHOLD = 4.2  # bits/char; real secrets typically exceed 4.5


# Computes Shannon entropy (bits/char) to distinguish high-entropy secrets from structured IDs
def _shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    freq: dict = {}
    for c in s:
        freq[c] = freq.get(c, 0) + 1
    n = len(s)
    return -sum((f / n) * math.log2(f / n) for f in freq.values())


def detect_high_entropy_secrets(text: str) -> List[str]:
    """Returns a type string describing what triggered entropy detection. UUIDs excluded."""
    for match in _ENTROPY_CONTEXT_RE.finditer(text):
        keyword, candidate = match.group(1), match.group(2)
        if _UUID_RE.match(candidate):
            continue
        if _shannon_entropy(candidate) > _ENTROPY_THRESHOLD:
            return [f"HIGH_ENTROPY_SECRET:{keyword.lower()}"]
    return []


def redact_secrets(text: str) -> tuple:
    """Replaces every matched secret pattern with [REDACTED_<TYPE>]; returns (redacted_text, type_names)."""
    redacted = text
    found: List[str] = []
    for pattern, secret_type in SECRET_PATTERNS:
        new_text = pattern.sub(f"[REDACTED_{secret_type}]", redacted)
        if new_text != redacted:
            found.append(secret_type)
            redacted = new_text
    return redacted, found


def detect_secrets(text: str) -> List[str]:
    """Returns detected secret type names without redacting the text."""
    _, found = redact_secrets(text)
    return found


# Leet-speak decode table: applied during normalisation to catch obfuscated terms.
_LEET_TABLE = str.maketrans({
    "0": "o", "1": "i", "3": "e", "4": "a",
    "5": "s", "6": "g", "7": "t", "@": "a", "$": "s",
})

# Strips inter-character punctuation to collapse symbol injection (f*ck → fck).
_INTER_CHAR_PUNCT_RE = re.compile(r"(?<=\w)[^\w\s]+(?=\w)")


def normalise(text: str) -> str:
    """Lowercase → strip inter-character symbols → decode leet-speak. Used for obfuscation detection."""
    stripped = _INTER_CHAR_PUNCT_RE.sub("", text.lower())
    return stripped.translate(_LEET_TABLE)


def matches_banned_word(banned: str, text_lower: str, threshold: int) -> bool:
    """Phrases: partial_ratio on full text. Single words: word-boundary check then per-token fuzzy."""
    from rapidfuzz import fuzz
    if " " in banned:
        return fuzz.partial_ratio(banned, text_lower) >= threshold
    if re.search(rf"\b{re.escape(banned)}\b", text_lower):
        return True
    for token in re.findall(r"\w+", text_lower):
        if fuzz.ratio(banned, token) >= threshold:
            return True
    return False


def extract_tool_response_text(response: Any) -> str:
    """Recursively extracts all string content from a tool response."""
    if isinstance(response, str):
        return response
    if isinstance(response, dict):
        return " ".join(extract_tool_response_text(v) for v in response.values())
    if isinstance(response, (list, tuple)):
        return " ".join(extract_tool_response_text(item) for item in response)
    return str(response) if response is not None else ""


def redact_tool_response(response: Any) -> Any:
    """Recursively redacts secrets from all string values in a tool response."""
    if isinstance(response, str):
        redacted, _ = redact_secrets(response)
        return redacted
    if isinstance(response, dict):
        return {k: redact_tool_response(v) for k, v in response.items()}
    if isinstance(response, list):
        return [redact_tool_response(item) for item in response]
    return response


# ─── Inflection expansion ─────────────────────────────────────────────────────

_INFLECTION_SUFFIXES = ("s", "es", "ed", "ing", "er", "ers", "ion", "ment")
_VOWELS = frozenset("aeiou")


def expand_inflections(words: List[str]) -> List[str]:
    """Pre-expands common English inflected forms. Only for words ≥ 5 chars to avoid short-stem over-matching."""
    result: set = set(words)
    for w in words:
        if len(w) < 5:
            continue
        for sfx in _INFLECTION_SUFFIXES:
            if sfx[0] in _VOWELS and w.endswith("e"):
                result.add(w[:-1] + sfx)
            result.add(w + sfx)
    return list(result)


# ─── Contextual unblocking ────────────────────────────────────────────────────

def _is_context_unblocked(text: str, context_allowlist: List[str]) -> bool:
    """True if any allowlist pattern matches (e.g. legal citation). Hard-tier words are never unblocked."""
    for pattern_str in context_allowlist:
        try:
            if re.search(pattern_str, text, re.I):
                return True
        except re.error:
            pass
    return False


def check_banned_words_tiered(
    text: str,
    hard_words: List[str],
    soft_words: List[str],
    warn_words: List[str],
    context_allowlist: List[str],
    threshold: int,
) -> tuple:
    """Returns (tier, matched_words): hard=block, soft=soft-block, warn=log-only, None=clean. Context downgrades soft→warn."""
    context_reduced = bool(context_allowlist) and _is_context_unblocked(text, context_allowlist)

    # Hard tier — never reduced by context
    matched = check_banned_words(text, hard_words, threshold)
    if matched:
        return "hard", matched

    # Soft tier — reduced to warn when context unblocked
    matched = check_banned_words(text, soft_words, threshold)
    if matched:
        return ("warn" if context_reduced else "soft"), matched

    # Warn tier — reduced to allow when context unblocked
    matched = check_banned_words(text, warn_words, threshold)
    if matched and not context_reduced:
        return "warn", matched

    return None, []


def check_banned_words(
    text: str,
    banned_words: List[str],
    threshold: int,
) -> List[str]:
    """Two-pass fuzzy match (raw + leet/symbol-normalised). Returns matched words; empty = no match."""
    text_lower = text.lower()
    text_norm = normalise(text)
    matched = []
    for b in banned_words:
        if matches_banned_word(b, text_lower, threshold):
            matched.append(b)
        elif text_norm != text_lower and matches_banned_word(b, text_norm, threshold):
            matched.append(b)
    return matched
