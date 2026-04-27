"""GCP Cloud Logging-based scheduled evaluator (alternative to the Phoenix one)."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import google.cloud.logging
import pandas as pd
from google.cloud.logging import DESCENDING
from phoenix.evals.evaluators import bind_evaluator, evaluate_dataframe
from phoenix.evals.llm import LLM
from phoenix.evals.metrics.correctness import CorrectnessEvaluator
from phoenix.evals.metrics.faithfulness import FaithfulnessEvaluator

from libs.config import get_settings


class GeminiADKGcpLogsEvaluator:
    def __init__(self, project_id: Optional[str] = None, cursor_file: Optional[str] = None):
        s = get_settings()
        self.project_id = project_id or s.project_id
        if not self.project_id or self.project_id == "my-gcp-project":
            raise ValueError("GCP project_id is required (set GOOGLE_CLOUD_PROJECT env var).")
        self.logging_client = google.cloud.logging.Client(project=self.project_id)
        self.logger = logging.getLogger("evaluator")
        self.llm = LLM(provider="google", model="gemini-1.5-flash", client="google-genai")
        self.cursor_file = Path(cursor_file or s.eval_cursor_file)

    def _load_cursor(self) -> Optional[str]:
        if self.cursor_file.exists():
            return json.loads(self.cursor_file.read_text()).get("last_timestamp")
        return None

    def _save_cursor(self, ts: str) -> None:
        self.cursor_file.write_text(json.dumps({"last_timestamp": ts}))

    def _parse(self, entry) -> dict:
        payload = entry.payload if isinstance(entry.payload, dict) else {}
        return {
            "log_id": entry.insert_id,
            "timestamp": entry.timestamp.isoformat(),
            "parsed_input": payload.get("input"),
            "parsed_output": payload.get("output"),
            "parsed_context": payload.get("context"),
        }

    async def fetch_logs(self, log_name: str, limit: int = 100) -> pd.DataFrame:
        last_ts = self._load_cursor()
        flt = f'logName="projects/{self.project_id}/logs/{log_name}"'
        if last_ts:
            flt += f' AND timestamp > "{last_ts}"'
        # list_entries is a blocking GCP SDK call — offload to a thread to avoid blocking the loop.
        entries = await asyncio.to_thread(
            lambda: list(self.logging_client.list_entries(filter_=flt, order_by=DESCENDING, page_size=limit))
        )
        return pd.DataFrame(self._parse(e) for e in entries)

    async def run_scheduled_evaluation(self, log_source: str = "agent-activity") -> dict:
        df = await self.fetch_logs(log_source)
        if df.empty:
            return {"status": "no data"}
        eval_df = df.dropna(subset=["parsed_input", "parsed_output"]).copy()
        if eval_df.empty:
            return {"status": "no valid entries"}

        bound_correctness = bind_evaluator(
            CorrectnessEvaluator(llm=self.llm),
            input_mapping={"input": "parsed_input", "output": "parsed_output"},
        )
        bound_faithfulness = bind_evaluator(
            FaithfulnessEvaluator(llm=self.llm),
            input_mapping={
                "input": "parsed_input", "output": "parsed_output", "context": "parsed_context",
            },
        )

        results_df = evaluate_dataframe(eval_df, [bound_correctness, bound_faithfulness])
        for _, row in results_df.iterrows():
            self.logger.info(
                "Evaluation Result",
                extra={
                    "json_fields": {
                        "original_log_id": row["log_id"],
                        "correctness_score": row.get("correctness"),
                        "faithfulness_score": row.get("faithfulness"),
                        "eval_timestamp": datetime.now(timezone.utc).isoformat(),
                        "type": "evaluation_annotation",
                    }
                },
            )

        self._save_cursor(df["timestamp"].max())
        return {"processed": len(eval_df), "status": "complete"}