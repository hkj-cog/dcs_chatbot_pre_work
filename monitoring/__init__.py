"""Observability evaluation + redaction package.

Heavy phoenix/google-cloud imports are intentionally lazy — `from monitoring import X`
should not import the Phoenix client unless X needs it.
"""
from .redaction import Redactor, default_redactor  # noqa: F401
from .session_processor import GlobalSessionIdProcessor  # noqa: F401