"""Phoenix-based scheduled evaluator for AGENT spans (Correctness + Faithfulness).

Works with both Phoenix Cloud (set PHOENIX_API_KEY) and self-hosted Phoenix
(leave PHOENIX_API_KEY empty)."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
from openinference.instrumentation import suppress_tracing
from phoenix.client import AsyncClient
from phoenix.evals.evaluators import bind_evaluator, evaluate_dataframe
from phoenix.evals.llm import LLM
from phoenix.evals.metrics.correctness import CorrectnessEvaluator
from phoenix.evals.metrics.faithfulness import FaithfulnessEvaluator
from phoenix.evals.utils import to_annotation_dataframe

from libs.config import get_settings
from libs.logger import logger


def _build_phoenix_async_client() -> AsyncClient:
    """
    Build an AsyncClient that targets the configured Phoenix backend.

    Strategy:
      1. Try keyword args (newer phoenix-client builds support `endpoint=` / `headers=`).
      2. Fall back to env vars (`PHOENIX_COLLECTOR_ENDPOINT`, `PHOENIX_CLIENT_HEADERS`)
         which all phoenix-client versions read on startup.
    """
    s = get_settings()

    # Always set env vars as a safety net — the client picks them up on construction.
    if s.phoenix_endpoint:
        os.environ.setdefault("PHOENIX_COLLECTOR_ENDPOINT", s.phoenix_endpoint)
    if s.phoenix_api_key and "PHOENIX_CLIENT_HEADERS" not in os.environ:
        os.environ["PHOENIX_CLIENT_HEADERS"] = f"api_key={s.phoenix_api_key}"

    # Try to pass kwargs explicitly first; gracefully fall back if the installed
    # version doesn't support them.
    kwargs: dict = {}
    if s.phoenix_endpoint:
        kwargs["endpoint"] = s.phoenix_endpoint
    if s.phoenix_api_key:
        kwargs["headers"] = {"api_key": s.phoenix_api_key}

    try:
        return AsyncClient(**kwargs)
    except TypeError:
        return AsyncClient()


class GeminiADKEvaluator:
    def __init__(
        self,
        project_id: str = "",
        location: str = "us-central1",
        cursor_file: Optional[str] = None,
    ):
        s = get_settings()
        self.llm = LLM(provider="google", model="gemini-2.5-flash", client="google-genai")
        self.px_client = _build_phoenix_async_client()
        self.cursor_file = Path(cursor_file or s.eval_cursor_file)
        self.project_id = project_id
        self.location = location

    # ----- cursor -----
    def _load_cursor(self) -> dict:
        if self.cursor_file.exists():
            return json.loads(self.cursor_file.read_text())
        return {"last_timestamp": None, "last_span_id": None}

    def _save_cursor(self, timestamp: str, span_id: str) -> None:
        self.cursor_file.write_text(
            json.dumps({"last_timestamp": timestamp, "last_span_id": span_id}, indent=2)
        )

    # ----- parsing helpers -----
    @staticmethod
    def _is_valid_string(val: object) -> bool:
        return isinstance(val, str) and bool(val.strip())

    def _parse_output_json(self, val: object) -> Optional[str]:
        if not isinstance(val, str) or not val.strip().startswith("{"):
            return None
        try:
            data: dict = json.loads(val)
            parts = data.get("content", {}).get("parts", [])
            return " ".join(p.get("text", "") for p in parts if "text" in p).strip() or None
        except (json.JSONDecodeError, AttributeError):
            return None

    def _parse_agent_context(self, val: object) -> Optional[str]:
        if isinstance(val, str):
            try:
                val = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                return None
        if not isinstance(val, dict):
            return None
        try:
            supports = val.get("grounding_metadata", {}).get("grounding_supports", [])
            texts = [s.get("segment", {}).get("text", "") for s in supports if "segment" in s]
            return " ".join(t for t in texts if t) or None
        except (AttributeError, KeyError):
            return None

    def _extract(self, agent_spans: pd.DataFrame) -> pd.DataFrame:
        df = agent_spans.copy()
        df["parsed_input"] = df.get("attributes.input.value")
        if "attributes.eval" in df.columns:
            df["parsed_input"] = df["attributes.eval"].apply(
                lambda v: v.get("input") if isinstance(v, dict) else None
            ).fillna(df["parsed_input"])
        df["parsed_output"] = df["attributes.output.value"].apply(self._parse_output_json)
        df["parsed_context"] = df["attributes.output.value"].apply(self._parse_agent_context)
        df = df.dropna(subset=["parsed_input", "parsed_output"])
        if df.empty:
            return df
        mask_in = df["parsed_input"].apply(self._is_valid_string).to_numpy(dtype=bool)
        mask_out = df["parsed_output"].apply(self._is_valid_string).to_numpy(dtype=bool)
        return pd.DataFrame(df[mask_in & mask_out])

    async def _get_unprocessed_spans(self, project_name: str) -> pd.DataFrame:
        cursor = self._load_cursor()
        start_time = (
            datetime.fromisoformat(cursor["last_timestamp"]) if cursor.get("last_timestamp") else None
        )
        spans_df = await self.px_client.spans.get_spans_dataframe(
            project_identifier=project_name, start_time=start_time, limit=1000,
        )
        if spans_df.empty:
            return spans_df
        spans_df = spans_df.sort_values("start_time")
        last_span = cursor.get("last_span_id")
        if last_span:
            idx = spans_df[spans_df["context.span_id"] == last_span].index
            if len(idx) > 0:
                spans_df = spans_df.loc[idx[0]:].iloc[1:]
        return spans_df

    async def run_scheduled_evaluation(self, project_name: Optional[str] = None) -> dict:
        project_name = project_name or get_settings().phoenix_project_name
        spans_df = await self._get_unprocessed_spans(project_name)
        if spans_df.empty:
            logger.info("No new spans to process", extra={"project": project_name})
            return {"processed": 0, "status": "no new spans"}

        agent_spans = spans_df[spans_df["span_kind"] == "AGENT"]
        if agent_spans.empty:
            last = spans_df.iloc[-1]
            self._save_cursor(last["start_time"].isoformat(), last["context.span_id"])
            return {"processed": 0, "status": "no agent spans"}

        parsed = self._extract(agent_spans)
        if parsed.empty:
            last = spans_df.iloc[-1]
            self._save_cursor(last["start_time"].isoformat(), last["context.span_id"])
            return {"processed": 0, "status": "no valid spans"}

        correctness = bind_evaluator(
            evaluator=CorrectnessEvaluator(llm=self.llm),
            input_mapping={"input": "parsed_input", "output": "parsed_output"},
        )
        faithfulness = bind_evaluator(
            evaluator=FaithfulnessEvaluator(llm=self.llm),
            input_mapping={
                "input": "parsed_input",
                "output": "parsed_output",
                "context": "parsed_context",
            },
        )

        with suppress_tracing():
            results_df = evaluate_dataframe(parsed, [faithfulness, correctness])

        annotations = to_annotation_dataframe(dataframe=results_df)
        await self.px_client.spans.log_span_annotations_dataframe(dataframe=annotations)

        last = spans_df.iloc[-1]
        self._save_cursor(last["start_time"].isoformat(), last["context.span_id"])
        logger.info(
            "Phoenix evaluation complete",
            extra={"processed": len(parsed), "project": project_name},
        )
        return {"processed": len(parsed), "status": "complete"}