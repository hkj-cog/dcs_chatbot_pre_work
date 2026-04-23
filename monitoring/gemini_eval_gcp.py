import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import google.cloud.logging
from google.cloud.logging import DESCENDING
from phoenix.evals.evaluators import bind_evaluator, evaluate_dataframe
from phoenix.evals.llm import LLM
from phoenix.evals.metrics.correctness import CorrectnessEvaluator
from phoenix.evals.metrics.faithfulness import FaithfulnessEvaluator

from libs.config import get_settings

setting = get_settings()

class GeminiADKGcpLogsEvaluator:
    def __init__(self, project_id: str, cursor_file: str = "cursor.json"):
        # 1. Initialize GCP Cloud Logging
        self.logging_client = google.cloud.logging.Client(project=project_id)
        self.logging_client.setup_logging()
        self.logger = logging.getLogger("evaluator")
        
        # 2. Phoenix LLM (Used only for the evaluation logic)
        self.llm = LLM(
            provider="google",
            model="gemini-1.5-flash", # Adjusted to currently available GA model
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

    def _parse_log_entry(self, entry) -> dict:
        """Parses a GCP Log Entry into a format compatible with Phoenix Evaluators."""
        payload = entry.payload if isinstance(entry.payload, dict) else {}
        
        # Adjust these keys based on how your app logs to GCP
        return {
            "log_id": entry.insert_id,
            "timestamp": entry.timestamp.isoformat(),
            "parsed_input": payload.get("input"),
            "parsed_output": payload.get("output"),
            "parsed_context": payload.get("context"),
        }

    async def fetch_logs_from_gcp(self, log_name: str, limit: int = 100) -> pd.DataFrame:
        """Fetches raw logs from GCP Log Explorer instead of Phoenix Client."""
        last_ts = self._load_cursor()
        
        # Filter for specific logs since last run
        filter_str = f'logName="projects/{setting.project_id}/logs/{log_name}"'
        if last_ts:
            filter_str += f' AND timestamp > "{last_ts}"'

        entries = self.logging_client.list_entries(
            filter_=filter_str, 
            order_by=DESCENDING, 
            page_size=limit
        )

        rows = [self._parse_log_entry(e) for e in entries]
        return pd.DataFrame(rows)

    async def run_scheduled_evaluation(self, log_source: str = "agent-activity"):
        """Evaluates logs and writes scores back to GCP."""
        df = await self.fetch_logs_from_gcp(log_source)

        if df.empty:
            self.logger.info("No new logs to evaluate.")
            return {"status": "no data"}

        # Clean data for evaluation
        eval_df = df.dropna(subset=["parsed_input", "parsed_output"]).copy()
        
        if eval_df.empty:
            return {"status": "no valid entries"}

        # Define Evaluators
        correctness_eval = CorrectnessEvaluator(llm=self.llm)
        faithfulness_eval = FaithfulnessEvaluator(llm=self.llm)

        bound_correctness = bind_evaluator(
            correctness_eval,
            input_mapping={"input": "parsed_input", "output": "parsed_output"}
        )
        bound_faithfulness = bind_evaluator(
            faithfulness_eval,
            input_mapping={"input": "parsed_input", "output": "parsed_output", "context": "parsed_context"}
        )

        # Run Evaluation
        results_df = evaluate_dataframe(eval_df, [bound_correctness, bound_faithfulness])

        # 3. Log results back to GCP as "Annotations"
        for _, row in results_df.iterrows():
            self.logger.info(
                f"Evaluation Result for {row['log_id']}",
                extra={
                    "json_fields": {
                        "original_log_id": row["log_id"],
                        "correctness_score": row.get("correctness"),
                        "faithfulness_score": row.get("faithfulness"),
                        "eval_timestamp": datetime.now(timezone.utc).isoformat(),
                        "type": "evaluation_annotation"
                    }
                }
            )

        # Update cursor with the most recent log timestamp
        new_cursor = df["timestamp"].max()
        self._save_cursor(new_cursor)

        return {"processed": len(eval_df), "status": "complete"}
