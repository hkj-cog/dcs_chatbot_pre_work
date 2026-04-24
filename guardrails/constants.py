"""Shared block messages and security-classification sets for the guardrail chain."""

_IMPROPER_BLOCK_MSG = (
    "Your message contains content that cannot be processed. "
    "Please rephrase and try again."
)

_SECRETS_BLOCK_MSG = (
    "Your message appears to contain a credential or secret such as an API key, "
    "password, or token. For your security, please remove any credentials and try again."
)

_OUTPUT_SECRETS_BLOCK_MSG = (
    "I'm unable to provide that response. "
    "Please contact Service NSW for assistance."
)

_TOPIC_BLOCK_MSG = (
    "I can only assist with questions about NSW Government services. "
    "Please ask a question about a NSW government service and I will be happy to help."
)

_OUTPUT_BLOCK_MSG = (
    "I'm unable to provide that response. "
    "Please contact Service NSW for assistance."
)

_JUDGE_UNAVAILABLE_BLOCK_MSG = (
    "I'm temporarily unable to process your request. Please try again shortly, "
    "or contact Service NSW for assistance."
)

_NSW_COMPLIANCE_BLOCK_MSG = (
    "I'm unable to provide that response as it does not meet NSW Government "
    "AI policy requirements. Please contact Service NSW for assistance."
)

_OUTPUT_TOO_LONG_MSG = (
    "I'm sorry, the response was too long to deliver safely. "
    "Please contact Service NSW for detailed assistance."
)

_MISSING_DISCLAIMER_MSG = (
    "For advice specific to your individual circumstances, please contact "
    "Service NSW or a qualified professional."
)

_INFORMATION_CURRENCY_DISCLAIMER = (
    "\n\n*Fees, deadlines, and eligibility requirements are subject to change. "
    "Please verify the most current details at "
    "[service.nsw.gov.au](https://www.service.nsw.gov.au) "
    "or contact Service NSW on 13 77 88 before taking action.*"
)

_COPYRIGHT_BLOCK_MSG = (
    "I found relevant information but cannot reproduce it verbatim. "
    "Please visit the official NSW Government website or contact Service NSW "
    "for the full details."
)

_BIAS_BLOCK_MSG = (
    "I'm unable to assist with that request. "
    "Please contact Service NSW for assistance."
)

_INPUT_TOO_LONG_MSG = (
    "Your message is too long to process. Please shorten it and try again."
)

_LANGUAGE_BLOCK_MSG = (
    "The response was generated in an unexpected language. Please try again, "
    "or contact Service NSW on 13 77 88 for assistance."
)

_LANGUAGE_NOT_SUPPORTED_MSG = (
    "I'm currently only able to respond in English and a limited set of "
    "supported languages. Please try asking your question in English, "
    "or contact Service NSW on 13 77 88 for assistance in your language."
)

_POLITENESS_BLOCK_MSG = (
    "I wasn't able to respond to that in an appropriate way. "
    "Please try rephrasing your question, or contact Service NSW for assistance."
)

_BAN_WORDS_BLOCK_MSG = (
    "I'm unable to provide that response as it contains disallowed content. "
    "Please contact Service NSW for assistance."
)

_SOFT_BAN_BLOCK_MSG = (
    "I'm unable to process that request. Please rephrase your question, "
    "or contact Service NSW on 13 77 88 for assistance."
)

_RELEVANCY_BLOCK_MSG = (
    "I wasn't able to give a relevant answer to your question. "
    "Could you please rephrase it, or contact Service NSW for assistance?"
)

_GROUNDEDNESS_BLOCK_MSG = (
    "I couldn't find verified information to fully answer your question. "
    "Please contact Service NSW for authoritative assistance."
)

_JAILBREAK_BLOCK_MSG = (
    "I'm designed to follow my instructions carefully. "
    "Please rephrase your query if you intended something specific."
)

_HARMFUL_INTENT_BLOCK_MSG = (
    "I'm unable to assist with requests that may facilitate harmful, fraudulent, "
    "or illegal activity. If you have a legitimate question about NSW Government "
    "services, please rephrase and try again."
)

_AGENT_ERROR_MSG = (
    "I'm sorry, I wasn't able to process your request. "
    "Please try again, or contact Service NSW on 13 77 88 for assistance."
)

_CRISIS_SUPPORT_MSG = (
    "It sounds like you may be going through a very difficult time. "
    "Your wellbeing matters.\n\n"
    "If you are in immediate danger, please call **000**.\n\n"
    "Free, confidential support is available any time:\n"
    "- **Lifeline** — 13 11 14 (24 hours, 7 days)\n"
    "- **Beyond Blue** — 1300 22 4636\n"
    "- **NSW Mental Health Line** — 1800 011 511\n\n"
    "You are not alone."
)

# Cannot be disabled via DISABLED_GUARDRAILS — baseline safety is unconditional.
NON_DISABLEABLE_GUARDRAILS: frozenset = frozenset({
    "SecretsInputGuardRail",
    "SecretsInputPreCheckGuardRail",
    "SecretsOutputGuardRail",
    "JailbreakGuardRail",
    "DlpInputGuardRail",
    "DlpOutputGuardRail",
    "GroundednessChecker",
})

ALL_BLOCK_MESSAGES: frozenset = frozenset({
    _IMPROPER_BLOCK_MSG,
    _SECRETS_BLOCK_MSG,
    _OUTPUT_SECRETS_BLOCK_MSG,
    _TOPIC_BLOCK_MSG,
    _OUTPUT_BLOCK_MSG,
    _JUDGE_UNAVAILABLE_BLOCK_MSG,
    _INPUT_TOO_LONG_MSG,
    _LANGUAGE_BLOCK_MSG,
    _POLITENESS_BLOCK_MSG,
    _BIAS_BLOCK_MSG,
    _BAN_WORDS_BLOCK_MSG,
    _SOFT_BAN_BLOCK_MSG,
    _RELEVANCY_BLOCK_MSG,
    _GROUNDEDNESS_BLOCK_MSG,
    _JAILBREAK_BLOCK_MSG,
    _NSW_COMPLIANCE_BLOCK_MSG,
    _OUTPUT_TOO_LONG_MSG,
    _COPYRIGHT_BLOCK_MSG,
    _HARMFUL_INTENT_BLOCK_MSG,
    _CRISIS_SUPPORT_MSG,
    _AGENT_ERROR_MSG,
})

# Subset used by SessionThreatTracker. Crisis support excluded — a person in distress is not an attacker.
SECURITY_BLOCK_MESSAGES: frozenset = frozenset({
    _IMPROPER_BLOCK_MSG,
    _SECRETS_BLOCK_MSG,
    _OUTPUT_SECRETS_BLOCK_MSG,
    _TOPIC_BLOCK_MSG,
    _JAILBREAK_BLOCK_MSG,
    _BIAS_BLOCK_MSG,
    _BAN_WORDS_BLOCK_MSG,
    _HARMFUL_INTENT_BLOCK_MSG,
})
