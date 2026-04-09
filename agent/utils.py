import os

from dotenv import load_dotenv
from google.auth import default as google_auth_default
from google.auth.exceptions import DefaultCredentialsError


def load_config(dotenv_path: str) -> None:
    """
    Loads environment variables from a specified .env file into the process environment.

    This function attempts to load environment variables from the given `dotenv_path`
    using the `python-dotenv` library. It includes robust checks for file existence
    and basic readability permissions, printing informative error messages if issues
    are encountered. It also issues a warning if `load_dotenv` reports that it did
    not find any variables to load, which can happen for empty or malformed files.

    Variables loaded by this function will **override** any existing environment
    variables with the same name, as `override=True` is used.

    :param dotenv_path: The `str` object pointing to the .env file
                        (e.g., `".env"`).
    :type dotenv_path: str
    :returns: None
    :rtype: NoneType
    """
    # 1. Check if the .env file actually exists at the specified path.
    # This prevents `load_dotenv` from potentially failing silently or with a generic error
    # if the file simply isn't there.
    if not dotenv_path.exists():
        print(f"ERROR: .env file DOES NOT EXIST at {dotenv_path.absolute()}")
        print(
            "Please ensure the .env file is correctly placed in the project root or specified path."
        )
    else:
        # 2. Attempt to open the file to check for basic read permissions.
        # This acts as a preliminary check to catch permission errors before `load_dotenv`
        # begins its parsing. Using a 'with' statement ensures the file is properly closed.
        try:
            with open(dotenv_path, "r", encoding="utf-8") as f:
                # No need to read content here, just checking if it can be opened.
                pass
        except Exception as e:
            print(f"ERROR reading .env file: {e}")
            print(f"Please check file permissions for {dotenv_path.absolute()}")

    # 3. Load environment variables using python-dotenv.
    #    - dotenv_path: Specifies the exact path to the .env file.
    #    - verbose=True: Prints status messages about the loading process, which is helpful for debugging.
    #    - override=True: Ensures that variables in the .env file will overwrite any existing
    #                     environment variables with the same names.
    load_successful = load_dotenv(dotenv_path=dotenv_path, verbose=True, override=True)

    # 4. Check the return value of load_dotenv.
    #    `load_dotenv` returns False if it couldn't find or parse any variables,
    #    e.g., if the file was empty, only contained comments, or was malformed.
    if not load_successful:
        print("WARNING: load_dotenv() reported that it did NOT load any variables.")
        print(
            "This could mean the file was empty, malformed, or contained only comments."
        )


def get_gcp_project_id():
    """
    Attempts to retrieve the current Google Cloud project ID.

    It checks:
    1. The GOOGLE_CLOUD_PROJECT environment variable.
    2. The GCLOUD_PROJECT environment variable.
    3. Application Default Credentials (ADC) via google.auth.default().

    Returns:
        str: The Google Cloud project ID if found, otherwise None.
    """
    # 1. Try environment variables first (explicitly set)
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    if project_id:
        print(
            f"Found project ID from GOOGLE_CLOUD_PROJECT environment variable: {project_id}"
        )
        return project_id

    project_id = os.getenv("GCLOUD_PROJECT")
    if project_id:
        print(
            f"Found project ID from GCLOUD_PROJECT environment variable: {project_id}"
        )
        return project_id

    # 2. Try Application Default Credentials (ADC)
    try:
        credentials, project = google_auth_default()
        if project:
            print(
                f"Found project ID using Application Default Credentials (ADC): {project}"
            )
            return project
        else:
            print(
                "ADC found credentials, but no default project ID associated with them."
            )
            print(
                "This can happen if you authenticated with `gcloud auth login` but didn't set a default project,"
            )
            print(
                "or if the credentials don't provide a project context (e.g., some manual key files)."
            )
            return None
    except DefaultCredentialsError:
        print("Default credentials could not be found.")
        print(
            "Please ensure you are authenticated (e.g., `gcloud auth application-default login`)"
        )
        print(
            "or that `GOOGLE_APPLICATION_CREDENTIALS` is set if using a service account key file locally."
        )
        return None
    except Exception as e:
        print(
            f"An unexpected error occurred while trying to get project ID via ADC: {e}"
        )
        return None
