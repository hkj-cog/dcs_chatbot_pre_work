"""Cloud Function entry point: triggered by Cloud Scheduler to run scheduled evaluation."""
import asyncio

import functions_framework
from cloudevents.http.event import CloudEvent

from monitoring.gemini_eval_gcp import GeminiADKGcpLogsEvaluator


@functions_framework.cloud_event
def hello_cloud_event(cloud_event: CloudEvent) -> None:
    # Triggered by Cloud Scheduler; runs the Gemini eval pipeline and logs results.
    evaluator = GeminiADKGcpLogsEvaluator()
    result = asyncio.run(evaluator.run_scheduled_evaluation())
    print(f"Evaluation complete: {result}")
