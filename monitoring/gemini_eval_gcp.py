"""Scheduled evaluator: reads pipeline_summary log entries from Cloud Logging and scores them with Gemini."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import google.cloud.logging
from google.cloud.logging import DESCENDING
from google.genai import Client as GenaiClient

from libs.config import get_settings
from libs.logger import logger as app_logger

_EVAL_PROMPT = """\
You are evaluating an AI chatbot response for an Australian government services chatbot.

User question: {question}
Bot answer: {answer}
Grounding context (source documents): {context}

Rate the response on two dimensions and reply with ONLY valid JSON, no other text:
{{
  "correctness": <float 0.0-1.0>,
  "faithfulness": <float 0.0-1.0>
}}

correctness: Does the answer correctly address the question? (1.0 = fully correct, 0.0 = wrong/misleading)
faithfulness: Is the answer supported by the grounding context? (1.0 = fully grounded, 0.0 = hallucinated; if no context → use 0.5)
"""


class GeminiADKGcpLogsEvaluator:
    def __init__(self, project_id: Optional[str] = None, cursor_file: Optional[str] = None):
        # Connects to GCP Cloud Logging and initialises the Gemini client and cursor path.
        s = get_settings()
        self.project_id = project_id or s.project_id
        if not self.project_id or self.project_id == "my-gcp-project":
            raise ValueError("GCP project_id is required (set GOOGLE_CLOUD_PROJECT env var).")
        self.logging_client = google.cloud.logging.Client(project=self.project_id)
        self.genai_client = GenaiClient()
        self.cursor_file = Path(cursor_file or s.eval_cursor_file)

    def _load_cursor(self) -> Optional[str]:
        # Loads the last-processed log timestamp from the cursor file.
        if self.cursor_file.exists():
            return json.loads(self.cursor_file.read_text()).get("last_timestamp")
        return None

    def _save_cursor(self, ts: str) -> None:
        # Persists the latest processed timestamp so the next run skips already-evaluated entries.
        self.cursor_file.write_text(json.dumps({"last_timestamp": ts}))

    async def fetch_pipeline_summaries(self, limit: int = 100) -> list[dict[str, Any]]:
        """Fetches pipeline_summary structured log entries since the last cursor position."""
        last_ts = self._load_cursor()
        flt = 'jsonPayload.pipeline_summary.input!=""'
        if last_ts:
            flt += f' AND timestamp > "{last_ts}"'
        entries = await asyncio.to_thread(
            lambda: list(
                self.logging_client.list_entries(
                    filter_=flt, order_by=DESCENDING, page_size=limit
                )
            )
        )
        rows = []
        for entry in entries:
            payload = entry.payload if isinstance(entry.payload, dict) else {}
            summary = payload.get("pipeline_summary") or {}
            if not summary.get("input") or not summary.get("output"):
                continue
            rows.append({
                "log_id": entry.insert_id,
                "timestamp": entry.timestamp.isoformat(),
                "input": summary.get("input", ""),
                "output": summary.get("output", ""),
                "context": summary.get("context", ""),
                "session_id": summary.get("session_id", ""),
                "was_blocked": bool(summary.get("was_blocked", False)),
            })
        return rows

    async def _score_entry(self, entry: dict[str, Any]) -> dict[str, Any]:
        # Scores a single pipeline entry for correctness and faithfulness using Gemini.
        prompt = _EVAL_PROMPT.format(
            question=entry["input"],
            answer=entry["output"],
            context=entry["context"] or "(none provided)",
        )
        try:
            response = await asyncio.to_thread(
                self.genai_client.models.generate_content,
                model="gemini-2.5-flash",
                contents=prompt,
            )
            scores = json.loads(response.text.strip())
            return {
                "correctness": float(scores.get("correctness", 0.5)),
                "faithfulness": float(scores.get("faithfulness", 0.5)),
            }
        except Exception as exc:
            app_logger.warning(
                f"[Eval] Gemini scoring failed for log_id={entry['log_id']}: {exc}"
            )
            return {"correctness": None, "faithfulness": None}

    async def run_scheduled_evaluation(self) -> dict:
        # Fetches unseen pipeline entries, scores each with Gemini, and writes results to Cloud Logging.
        entries = await self.fetch_pipeline_summaries()
        if not entries:
            return {"status": "no data", "processed": 0}

        processed = 0
        for entry in entries:
            if entry["was_blocked"]:
                continue  # blocked responses have no valid output to evaluate
            scores = await self._score_entry(entry)
            app_logger.info(
                "evaluation_result",
                extra={
                    "evaluation_result": {
                        "log_id": entry["log_id"],
                        "session_id": entry["session_id"],
                        "correctness": scores["correctness"],
                        "faithfulness": scores["faithfulness"],
                        "eval_timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                },
            )
            processed += 1

        if entries:
            self._save_cursor(max(e["timestamp"] for e in entries))
        return {"processed": processed, "status": "complete"}
