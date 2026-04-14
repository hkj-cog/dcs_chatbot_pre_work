import logging
from typing import List

from google.cloud import dlp_v2

logger = logging.getLogger(__name__)


class GoogleDlp:
    """
    Wraps the Google Cloud Data Loss Prevention (DLP) API to de-identify
    (redact) personally identifiable information (PII) from user-supplied
    text before it is passed to the LLM agent.

    Detected PII tokens are replaced with a configurable replacement string
    (default: "[REDACTED]").

    Typical PII types for Australian government context:
        EMAIL_ADDRESS, PHONE_NUMBER, FIRST_NAME, LAST_NAME,
        PASSPORT, AUSTRALIA_TAX_FILE_NUMBER,
        AUSTRALIA_MEDICARE_NUMBER, AUSTRALIA_DRIVERS_LICENSE_NUMBER

    Usage:
        dlp = GoogleDlp(project="my-gcp-project", info_types=["EMAIL_ADDRESS"])
        clean_query = dlp.invoke("Contact me at user@example.com")
        # → "Contact me at [REDACTED]"
    """

    def __init__(
        self,
        project: str,
        info_types: List[str],
        replacement_str: str = "[REDACTED]",
    ):
        """
        Initialises the DLP client and pre-builds the inspect/de-identify
        configs so they are not reconstructed on every call.

        Args:
            project:         GCP project ID (used as the DLP parent resource).
            info_types:      List of DLP info-type names to detect and redact.
                             See: https://cloud.google.com/dlp/docs/infotypes-reference
            replacement_str: String that replaces each detected PII token.
        """
        if not project:
            raise ValueError("GoogleDlp: 'project' must be a non-empty GCP project ID.")
        if not info_types:
            raise ValueError("GoogleDlp: 'info_types' must contain at least one entry.")

        self._client = dlp_v2.DlpServiceClient()
        self._parent = f"projects/{project}/locations/global"

        dlp_info_types = [{"name": t} for t in info_types]

        # What to look for
        self._inspect_config = {
            "info_types": dlp_info_types,
            "include_quote": False,   # do not echo PII back in the API response
        }

        # How to transform detected findings — replace with replacement_str
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

        logger.info(
            f"GoogleDlp initialised — project='{project}', "
            f"info_types={info_types}, replacement='{replacement_str}'"
        )

    def invoke(self, query: str) -> str:
        """
        De-identifies PII in the provided query string.

        If the DLP API call fails for any reason, the original query is
        returned unchanged and the error is logged — this ensures the agent
        pipeline is never blocked by a DLP outage.

        Args:
            query: Raw user-supplied text that may contain PII.

        Returns:
            The de-identified text with PII tokens replaced, or the original
            text if the API call fails.
        """
        if not query or not query.strip():
            return query

        try:
            request = dlp_v2.DeidentifyContentRequest(
                parent=self._parent,
                deidentify_config=self._deidentify_config,
                inspect_config=self._inspect_config,
                item={"value": query},
            )

            response = self._client.deidentify_content(request=request)
            sanitized = response.item.value

            if sanitized != query:
                logger.info("GoogleDlp: PII detected and redacted from user input.")
            else:
                logger.debug("GoogleDlp: No PII detected in user input.")

            return sanitized

        except Exception as e:
            # Fail open — log and pass through rather than blocking the pipeline
            logger.error(
                f"GoogleDlp: API call failed, returning original query. Error: {e}"
            )
            return query