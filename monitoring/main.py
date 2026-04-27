"""Cloud Function entry point: triggered by Cloud Scheduler to run scheduled evaluation."""
import asyncio

import functions_framework
from cloudevents.http.event import CloudEvent

from monitoring.gemini_eval import GeminiADKEvaluator


@functions_framework.cloud_event
def hello_cloud_event(cloud_event: CloudEvent) -> None:
    evaluator = GeminiADKEvaluator()
    result = asyncio.run(evaluator.run_scheduled_evaluation())
    print(f"Evaluation complete: {result}")