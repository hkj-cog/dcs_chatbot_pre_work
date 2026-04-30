# Google Cloud DLP wrapper with AU-specific pre-processing and false-positive protection
import re
from typing import List

from google.cloud import dlp_v2

from libs.logger import logger

# ── Pre-DLP normalisation ─────────────────────────────────────────────────────

# Normalises TFN variants like "TFN-123456782-2024" to "NNN NNN NNN" for Cloud DLP's checksum detector.
_TFN_EMBEDDED_RE = re.compile(
    r'(?i)\bTFN[-_/](\d{8,9})(?:[-_/]\w+)*\b'
)


# Converts embedded TFN formats (e.g. TFN-123456789) to "NNN NNN NNN" for Cloud DLP recognition
def _normalise_tfn(m: re.Match) -> str:
    d = m.group(1).zfill(9)
    return f"{d[:3]} {d[3:6]} {d[6:]}"


# AUSTRALIA_ABN_NUMBER is unavailable in australia-southeast1 — redacted locally instead.
_ABN_RE = re.compile(
    r'\b(\d{2})[\s\-]?(\d{3})[\s\-]?(\d{3})[\s\-]?(\d{3})\b'
)


# Government terms that trigger Cloud DLP false positives; swapped with placeholders before DLP runs.
_POLITICAL_TERMS_RE = re.compile(
    r'\b('
    r'NSW|ALP|LNP|Labor|Liberal|Greens|National|Coalition|Parliament|'
    r'Government|Opposition|Federal|State|Territory|Council|Minister|Premier|'
    r'Senator|MP|Councillor|Democrat|Republican|Independents?|'
    # "Galles" etc. — Cloud DLP flags multilingual translations of "Wales" as LAST_NAME
    r'Galles|Gales|Pays\s+de\s+Galles|'
    r'Nouvelle(?:\-Galles)?|Nueva\s+Gales|Nuovo\s+Galles|'
    r'Gouvernement|Gobierno|Governo|Regierung|Overheid|'
    r'Département|Departamento|Dipartimento|Abteilung|'
    r'Ministre|Ministro|Ministère|Ministerio|Ministero|'
    r'Parlement|Parlamento|Parlamento|Parlament'
    r')\b',
    re.I,
)
_PLACEHOLDER_PREFIX = "\x00TERM\x00"  # null-byte bookends — never appears in user text


def _protect_political_terms(text: str) -> tuple[str, dict]:
    """Replace political terms with indexed placeholders. Returns (modified_text, index_map)."""
    mapping: dict[str, str] = {}
    counter = [0]

    # Substitution callback that indexes each matched term and stores the original for restoration
    def replace(m: re.Match) -> str:
        original = m.group(0)
        key = f"{_PLACEHOLDER_PREFIX}{counter[0]}{_PLACEHOLDER_PREFIX}"
        mapping[key] = original
        counter[0] += 1
        return key

    protected = _POLITICAL_TERMS_RE.sub(replace, text)
    return protected, mapping


# Substitutes placeholders back to original political terms after Cloud DLP has run
def _restore_political_terms(text: str, mapping: dict) -> str:
    for placeholder, original in mapping.items():
        text = text.replace(placeholder, original)
    return text


def _preprocess(text: str) -> str:
    """Normalise TFN formats and redact ABNs locally before Cloud DLP runs."""
    text = _TFN_EMBEDDED_RE.sub(_normalise_tfn, text)
    text = _ABN_RE.sub("[REDACTED]", text)
    return text


class GoogleDlp:
    """Wraps the Cloud DLP API to redact PII from text before it reaches the LLM."""

    def __init__(
        self,
        project: str,
        info_types: List[str],
        replacement_str: str = "[REDACTED]",
        fail_open: bool = False,
        location: str = "australia-southeast1",  # australia-southeast1 for Privacy Act data residency
    ):
        if not project:
            raise ValueError("GoogleDlp: 'project' must be a non-empty GCP project ID.")
        if not info_types:
            raise ValueError("GoogleDlp: 'info_types' must contain at least one entry.")

        self._client = dlp_v2.DlpServiceClient()
        self._parent = f"projects/{project}/locations/{location}"

        dlp_info_types = [{"name": t} for t in info_types]

        self._inspect_config = {
            "info_types": dlp_info_types,
            "include_quote": False,  # don't echo PII back in the API response
        }

        self._deidentify_config = {
            "info_type_transformations": {
                "transformations": [
                    {
                        "info_types": dlp_info_types,
                        "primitive_transformation": {
                            "replace_config": {
                                "new_value": {"string_value": replacement_str}
                            }
                        },
                    }
                ]
            }
        }

        self._fail_open = fail_open

        logger.info(
            f"GoogleDlp initialised — project='{project}', location='{location}', "
            f"info_types={info_types}, replacement='{replacement_str}', "
            f"fail_open={fail_open}"
        )

    def invoke(self, query: str) -> str:
        """Redacts PII from `query`. Raises RuntimeError on API failure unless fail_open=True."""
        if not query or not query.strip():
            return query

        try:
            preprocessed = _preprocess(query)
            protected, term_map = _protect_political_terms(preprocessed)

            request = dlp_v2.DeidentifyContentRequest(
                parent=self._parent,
                deidentify_config=self._deidentify_config,
                inspect_config=self._inspect_config,
                item={"value": protected},
            )

            response = self._client.deidentify_content(request=request)
            sanitized = _restore_political_terms(response.item.value, term_map)

            if sanitized != query:
                logger.info("GoogleDlp: PII detected and redacted from user input.")
            else:
                logger.debug("GoogleDlp: No PII detected in user input.")

            return sanitized

        except Exception as e:
            logger.error(
                f"GoogleDlp: API call failed.",
                extra={"dlp_bypassed": self._fail_open, "error": str(e)},
            )
            if self._fail_open:
                logger.warning(
                    "GoogleDlp: Failing open — original query forwarded unredacted."
                )
                return query
            raise RuntimeError(
                f"DLP unavailable, blocking request to protect PII: {e}"
            ) from e