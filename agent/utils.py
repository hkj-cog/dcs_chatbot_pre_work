# GCP project and credential helpers used at agent startup
import os
from pathlib import Path

from dotenv import load_dotenv
from google.auth import default as google_auth_default
from google.auth.exceptions import DefaultCredentialsError

from libs.logger import logger


def load_config(dotenv_path: Path) -> None:
    """Loads .env file into the process environment, logging any file or parse issues."""
    if not dotenv_path.exists():
        logger.error(
            f".env file DOES NOT EXIST at {dotenv_path.absolute()}. "
            "Please ensure the .env file is correctly placed in the project root or specified path."
        )
    else:
        try:
            with open(dotenv_path, "r", encoding="utf-8") as f:
                pass
        except Exception as e:
            logger.error(f"Cannot read .env file at {dotenv_path.absolute()}: {e}")

    load_successful = load_dotenv(dotenv_path=dotenv_path, verbose=True, override=True)

    if not load_successful:
        logger.warning(
            "load_dotenv() reported that it did NOT load any variables. "
            "The file may be empty, malformed, or contain only comments."
        )


def get_gcp_project_id():
    """Returns the GCP project ID from env vars or ADC; None if not found."""
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    if project_id:
        logger.info(f"Found project ID from GOOGLE_CLOUD_PROJECT: {project_id}")
        return project_id

    project_id = os.getenv("GCLOUD_PROJECT")
    if project_id:
        logger.info(f"Found project ID from GCLOUD_PROJECT: {project_id}")
        return project_id

    try:
        credentials, project = google_auth_default()
        if project:
            logger.info(f"Found project ID via Application Default Credentials: {project}")
            return project
        else:
            logger.warning(
                "ADC found credentials but no default project ID. "
                "Run `gcloud config set project <PROJECT_ID>` to associate one."
            )
            return None
    except DefaultCredentialsError:
        logger.error(
            "Application Default Credentials not found. "
            "Run `gcloud auth application-default login` or set GOOGLE_APPLICATION_CREDENTIALS."
        )
        return None
    except Exception as e:
        logger.error(f"Unexpected error retrieving project ID via ADC: {e}")
        return None
