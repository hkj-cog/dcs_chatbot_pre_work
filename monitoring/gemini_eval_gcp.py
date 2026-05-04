import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from google.cloud import trace_v1
from google.cloud import logging
import pandas as pd
import google.cloud.logging
from phoenix.evals.evaluators import async_evaluate_dataframe, bind_evaluator, evaluate_dataframe
from phoenix.evals.llm import LLM
from phoenix.evals.metrics.correctness import CorrectnessEvaluator
from phoenix.evals.metrics.faithfulness import FaithfulnessEvaluator
from phoenix.trace import suppress_tracing
from libs.config import get_settings
from libs import logger

setting = get_settings()

class GeminiADKGcpLogsEvaluator:
    def __init__(self, project_id: str, cursor_file: str = "cursor.json"):
        # 1. Initialize GCP Cloud Logging
        self.logging_client = google.cloud.logging.Client(project=project_id)
        self.logging_client.setup_logging()
        
        # 2. Phoenix LLM (Used only for the evaluation logic)
        self.llm = LLM(
            provider="google",
            model="gemini-2.5-flash",
            client="google-genai",
        )
        
        self.cursor_file = Path(cursor_file)
        self.project_id = project_id

    def _load_cursor(self) -> str | None:
        if self.cursor_file.exists():
            data = json.loads(self.cursor_file.read_text())
            return data.get("last_timestamp")
        return None

    def _save_cursor(self, timestamp: str) -> None:
        self.cursor_file.write_text(json.dumps({"last_timestamp": timestamp}))


    async def fetch_traces_from_gcp(self, limit: int = 100) -> pd.DataFrame:
        """Fetches traces using the correct Request object for the Trace Client."""
        
        trace_client = trace_v1.TraceServiceClient()
        
        # 1. Prepare the request dictionary 
        # (Matches the ListTracesRequest fields)
        start_time_str = self._load_cursor()
        end_time_str = datetime.utcnow().isoformat() + "Z"

        request = {
            "project_id": setting.project_id,
            "start_time": start_time_str,
            "end_time": end_time_str,
            "page_size": limit,
            "order_by": "start"
        }

        # 2. Pass the request dictionary to list_traces
        pager = trace_client.list_traces(request=request)

        rows = []
        current_cursor = start_time_str

        for trace in pager:

            trace = trace_client.get_trace(
                project_id=setting.project_id, 
                trace_id=trace.trace_id
            )
            for span in trace.spans:
                # logger.info(f"Processing span {span.span_id} from trace {trace.trace_id}")
                # ts_str = span.start_time.isoformat()
                # if ts_str > current_cursor:
                #     current_cursor = ts_str
                #
                rows.append({
                    "trace_id": trace.trace_id,
                    "span_id": span.span_id,
                    "parent_span_id": span.parent_span_id,
                    "name": span.name,
                    "end_time": span.end_time.isoformat(),
                    "labels": dict(span.labels),
                    "span_kind": span.labels.get("openinference.span.kind"),
                    "input": span.labels.get("eval.input"),
                    "output": span.labels.get("output.value")
                })

        return pd.DataFrame(rows)


    def _parse_span_entry(self, entry) -> dict:
        """Extracts span fields (input/output, model, tokens, latency) from a log entry."""
        payload = entry.payload or {}
        attrs = payload.get("attributes", {}) or {}

        # Input/output values may be JSON-encoded strings; try to decode
        def _maybe_json(v):
            if isinstance(v, str):
                try:
                    return json.loads(v)
                except (json.JSONDecodeError, TypeError):
                    return v
            return v

        start = payload.get("start_time")
        end = payload.get("end_time")
        latency_ms = None
        if start and end:
            try:
                latency_ms = (
                    pd.to_datetime(end) - pd.to_datetime(start)
                ).total_seconds() * 1000
            except Exception:
                latency_ms = None

        return {
            "trace_id": payload.get("trace_id") or entry.trace,
            "span_id": payload.get("span_id") or entry.span_id,
            "parent_span_id": payload.get("parent_span_id"),
            "name": payload.get("name"),
            "span_kind": attrs.get("openinference.span.kind"),
            "input": _maybe_json(attrs.get("input.value")),
            "output": _maybe_json(attrs.get("output.value")),
            "input_mime_type": attrs.get("input.mime_type"),
            "output_mime_type": attrs.get("output.mime_type"),
            "model": attrs.get("llm.model_name"),
            "input_tokens": attrs.get("llm.token_count.prompt"),
            "output_tokens": attrs.get("llm.token_count.completion"),
            "total_tokens": attrs.get("llm.token_count.total"),
            "status": payload.get("status", {}).get("code") if isinstance(payload.get("status"), dict) else payload.get("status"),
            "start_time": start or entry.timestamp,
            "end_time": end,
            "latency_ms": latency_ms,
        }

    def push_eval_to_gcp(self, data_row):
        client = logging.Client()
        # Name of the log (you can find this in Logs Explorer)
        logger = client.logger("dcs_chatbot")

        # Important: Format the trace resource name so GCP links them
        # Format: projects/[PROJECT_ID]/traces/[TRACE_ID]
        trace_resource = f"projects/{setting.project_id}/traces/{data_row['trace_id']}"

        # Convert the Series/DataRow to a dictionary
        payload = data_row.to_dict()

        # Log the structured data
        logger.log_struct(
            payload,
            severity="INFO",
            trace=trace_resource,
            span_id=str(data_row['span_id'])
        )

    async def run_scheduled_evaluation(self, log_source: str = "agent-activity"):
        """Evaluates logs and writes scores back to GCP."""
        df = await self.fetch_traces_from_gcp()

        if df.empty:
            self.logger.info("No new logs to evaluate.")
            return {"status": "no data"}

        filtered = pd.DataFrame(df[df["span_kind"] == "AGENT"])

        # Clean data for evaluation
        eval_df = filtered.dropna(subset=["input", "output"]).copy()
        
        if eval_df.empty:
            return {"status": "no valid entries"}

        # Define Evaluators
        correctness_eval = CorrectnessEvaluator(llm=self.llm)
        faithfulness_eval = FaithfulnessEvaluator(llm=self.llm)

        bound_correctness = bind_evaluator(
            correctness_eval,
            input_mapping={"input": "input", "output": "output"}
        )
        # bound_faithfulness = bind_evaluator(
        #     faithfulness_eval,
        #     input_mapping={"input": "parsed_input", "output": "parsed_output", "context": "parsed_context"}
        # )

        with suppress_tracing():
            results_df = await async_evaluate_dataframe(eval_df, [bound_correctness], concurrency=10)

            for _, row in results_df.iterrows():
                logger.info(row)
                self.push_eval_to_gcp(row)

        # Update cursor with the most recent log timestamp
        # new_cursor = df["endtime"].max()
        # self._save_cursor(new_cursor)

        return {"processed": len(eval_df), "status": "complete"}
