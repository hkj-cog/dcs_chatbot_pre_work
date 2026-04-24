"""Shared validation patterns used across API endpoints."""
import re

SESSION_ID_RE = re.compile(r'^[a-zA-Z0-9_\-]{1,128}$')
USER_ID_RE = re.compile(r'^[\w@.\-]{1,128}$')
