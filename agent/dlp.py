from typing import List

from google.cloud import dlp_v2


class GoogleDlp:

    def __init__(
        self,
        project,
        info_types: List[str],
        replacement_str: str = "[REDACTED]",
    ):

        self._client = dlp_v2.DlpServiceClient()
        self._parent = f"projects/{project}/locations/global"
        dlp_info_types = [{"name": info_type} for info_type in info_types]

        # Configure the inspection (what to look for)
        self._inspect_config = {"info_types": dlp_info_types}

        # Configure the de-identification (how to transform)
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

    def invoke(self, query):
        request = dlp_v2.DeidentifyContentRequest(
            parent=self._parent,
            deidentify_config=self._deidentify_config,
            inspect_config=self._inspect_config,
            item={"value": query},
        )

        # Call the DLP API
        response = self._client.deidentify_content(request=request)

        return response.item.value
