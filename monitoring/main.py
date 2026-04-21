# functions/evaluation.py
from cloudevents.http.event import CloudEvent
import functions_framework
import asyncio

from monitoring.gemini_eval import GeminiADKEvaluator

@functions_framework.cloud_event
def hello_cloud_event(cloud_event: CloudEvent) -> None:
    """Triggered every 10 minutes by Cloud Scheduler."""
    print("Starting scheduled evaluation...")
    
    evaluator = GeminiADKEvaluator("","")
    results = asyncio.run(evaluator.evaluate_last_session())
    
    print(f"Evaluation complete: {results}")


