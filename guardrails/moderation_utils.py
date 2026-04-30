"""Google Cloud Language API moderation helpers shared across input and output guardrails."""

from zoneinfo import ZoneInfo

from google.cloud import language_v1

# ─── Australia/Sydney timezone ────────────────────────────────────────────────
SYDNEY_TZ = ZoneInfo("Australia/Sydney")

# ─── Moderation category membership sets ─────────────────────────────────────
TOXIC_CATEGORIES = {"Toxic", "Insult", "Derogatory", "Profanity"}
HARMFUL_CATEGORIES = {
    "Death_Harm_Tragedy",
    "Illicit_drugs",
    "Firearms_Weapons",
    "Violence",
    "War_Conflict",
    "Sexually_Explicit",
}

# Per-layer thresholds: input is lenient (avoid false positives), output is strict (LLM content standard).

MODERATION_CATEGORIES_INPUT = {
    "Profanity":          0.5,
    "Toxic":              0.7,
    "Insult":             0.7,
    "Derogatory":         0.7,
    "Illicit_drugs":      0.8,
    "Firearms_Weapons":   0.8,
    # 0.85 for INPUT: bereavement/estate/funeral queries are legitimate government topics.
    "Death_Harm_Tragedy": 0.85,
    # Violence/War_Conflict excluded from INPUT — citizens must ask about DV orders, ANZAC programs, etc.
    # 0.9 for INPUT: defence-in-depth behind Gemini safety settings; avoids false positives on sexual-health queries.
    "Sexually_Explicit":  0.9,
}

MODERATION_CATEGORIES_OUTPUT = {
    "Toxic":              0.7,
    "Insult":             0.7,
    "Derogatory":         0.6,   # stricter on output
    "Profanity":          0.5,
    "Death_Harm_Tragedy": 0.85,
    "Illicit_drugs":      0.8,
    "Firearms_Weapons":   0.8,
    "Violence":           0.75,  # OUTPUT only — citizens must still be able to ask about DV services
    "War_Conflict":       0.85,
    # Defence-in-depth backstop for Gemini's HARM_CATEGORY_SEXUALLY_EXPLICIT safety setting.
    "Sexually_Explicit":  0.9,
}

# Lazy init — avoids a GCP connection at import time (fails in test environments).
_language_client = None


# Lazy singleton initialiser for the Cloud Natural Language client
def _get_language_client() -> language_v1.LanguageServiceClient:
    global _language_client
    if _language_client is None:
        _language_client = language_v1.LanguageServiceClient()
    return _language_client


def check_moderation_categories(text: str, thresholds: dict) -> list:
    """Returns triggered category names whose confidence exceeds the threshold. Call via asyncio.to_thread()."""
    document = language_v1.Document(
        content=text,
        type_=language_v1.Document.Type.PLAIN_TEXT,
    )
    response = _get_language_client().moderate_text(document=document)
    triggered = []
    for cat in response.moderation_categories:
        threshold = thresholds.get(cat.name)
        if threshold is not None and cat.confidence > threshold:
            triggered.append(cat.name)
    return triggered
