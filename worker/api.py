import logging
from typing import Annotated, Optional
from fastapi import APIRouter, Header, Response
from fastapi.requests import Request
import base64
import json

router = APIRouter()

# Setup basic logging so you can see the worker's heartbeat in Cloud Run logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@router.post("/push-subscription")
async def process_pubsub_message(request: Request):
    return {}
