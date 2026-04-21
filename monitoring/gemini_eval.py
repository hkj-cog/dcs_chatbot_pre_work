import json
from datetime import datetime
from pathlib import Path

import pandas as pd
from openinference.instrumentation import suppress_tracing
from phoenix.client import AsyncClient
from phoenix.evals.evaluators import bind_evaluator, evaluate_dataframe
from phoenix.evals.llm import LLM
from phoenix.evals.metrics.correctness import CorrectnessEvaluator
from phoenix.evals.metrics.faithfulness import FaithfulnessEvaluator
from phoenix.evals.utils import to_annotation_dataframe

from libs import logger


class GeminiADKEvaluator:
    def __init__(self, project_id: str, location: str = "us-central1", cursor_file: str = "cursor.json"):
        self.llm = LLM(
            provider="google",
            model="gemini-2.5-flash",
            client="google-genai",
        )
        self.px_client = AsyncClient()
        self.cursor_file = Path(cursor_file)

    def _load_cursor(self) -> dict:
        if self.cursor_file.exists():
            return json.loads(self.cursor_file.read_text())
        return {"last_timestamp": None, "last_span_id": None}

    def _save_cursor(self, timestamp: str, span_id: str) -> None:
        self.cursor_file.write_text(json.dumps({
            "last_timestamp": timestamp,
            "last_span_id": span_id,
        }, indent=2))

    def _parse_output_json(self, val: object) -> str | None:
        """Extract text from raw ADK output JSON payload."""
        if not isinstance(val, str) or not val.strip().startswith("{"):
            return None
        try:
            data: dict = json.loads(val)
            parts = data.get("content", {}).get("parts", [])
            texts = [p.get("text", "") for p in parts if "text" in p]
            logger.info(f"Parsed output JSON: extracted texts={texts}")
            return " ".join(texts).strip() or None
        except (json.JSONDecodeError, AttributeError):
            return None

    def parse_agent_context(self, val: object) -> str | None:
        if val is None:
            return None
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
            texts = [t for t in texts if t]
            context = " ".join(texts) if texts else None
            return context
        except (AttributeError, KeyError) as e:
            logger.warning(f"Failed to extract agent context: {e}")
        return None

    def _is_valid_string(self, val: object) -> bool:
        return isinstance(val, str) and len(val.strip()) > 0

    def extract_input_output(self, agent_spans: pd.DataFrame) -> pd.DataFrame:
        df: pd.DataFrame = agent_spans.copy()

        def parse_eval_input(val: object) -> str | None:
            if val is None or not isinstance(val, dict):
                return None
            raw = val.get("input", "")
            logger.info(f"Parsing eval input: raw value={raw}")
            return raw or None

        def parse_eval_session(val: object) -> str | None:
            if val is None or not isinstance(val, dict):
                return None
            raw = val.get("session", "")
            logger.info(f"Parsing eval session: raw session={raw}")
            return raw or None

        df["parsed_input"] = df["attributes.eval"].apply(parse_eval_input)
        df["parsed_session_created_on"] = df["attributes.session"].apply(parse_eval_session)
        df["parsed_output"] = df["attributes.output.value"].apply(self._parse_output_json)
        df["parsed_context"] = df["attributes.output.value"].apply(self.parse_agent_context)

        df = pd.DataFrame(df.dropna(subset=["parsed_input", "parsed_output"]))

        if df.empty:
            return df

        input_mask = df["parsed_input"].apply(self._is_valid_string).to_numpy(dtype=bool)
        output_mask = df["parsed_output"].apply(self._is_valid_string).to_numpy(dtype=bool)
        df = pd.DataFrame(df[input_mask & output_mask])

        for _, row in df.iterrows():
            logger.info(
                f"parsed_input={row['parsed_input']} \n "
                f"parsed_output={row['parsed_output']} \n"
                f"parsed_context={row['parsed_context']} \n"
            )

        return df


    async def _get_unprocessed_spans(self, project_name: str) -> pd.DataFrame:
        """Fetch spans that haven't been processed yet."""
        cursor = self._load_cursor()

        start_time = None
        if cursor["last_timestamp"]:
            start_time = datetime.fromisoformat(cursor["last_timestamp"])

        spans_df = await self.px_client.spans.get_spans_dataframe(
            project_identifier=project_name,
            start_time=start_time,
            limit=1000,
        )

        if spans_df.empty:
            return spans_df

        spans_df = spans_df.sort_values("start_time")

        # Skip already-processed span
        if cursor["last_span_id"]:
            cursor_idx = spans_df[
                spans_df["context.span_id"] == cursor["last_span_id"]
            ].index
            if len(cursor_idx) > 0:
                spans_df = spans_df.loc[cursor_idx[0]:].iloc[1:]

        return spans_df

    async def run_scheduled_evaluation(self, project_name: str = "dcs-chat") -> dict:
        """Run evaluation on unprocessed spans. Call this on a schedule."""
        spans_df = await self._get_unprocessed_spans(project_name)

        if spans_df.empty:
            logger.info("No new spans to process")
            return {"processed": 0, "status": "no new spans"}

        filtered = pd.DataFrame(spans_df[spans_df["span_kind"] == "AGENT"])

        if filtered.empty:
            logger.info("No AGENT spans found")
            # Still save cursor to skip these spans next time
            last_row = spans_df.iloc[-1]
            self._save_cursor(
                timestamp=last_row["start_time"].isoformat(),
                span_id=last_row["context.span_id"],
            )
            return {"processed": 0, "status": "no agent spans"}

        agent_spans = self.extract_input_output(filtered)

        if agent_spans.empty:
            logger.info("No valid agent spans after parsing")
            last_row = spans_df.iloc[-1]
            self._save_cursor(
                timestamp=last_row["start_time"].isoformat(),
                span_id=last_row["context.span_id"],
            )
            return {"processed": 0, "status": "no valid spans"}

        correctness_eval = CorrectnessEvaluator(llm=self.llm)
        faithfullness_eval = FaithfulnessEvaluator(llm=self.llm)
        bound_evaluator = bind_evaluator(
            evaluator=correctness_eval,
            input_mapping={
                "input": "parsed_input",
                "output": "parsed_output",
            },
        )

        faithfulness_bound_evaluator = bind_evaluator(
            evaluator=faithfullness_eval,
            input_mapping={
                "input": "parsed_input",
                "output": "parsed_output",
                "context": "parsed_context"
            },
        )


        logger.info(f"data frame: {agent_spans}")
        with suppress_tracing():
            results_df = evaluate_dataframe(agent_spans, [faithfulness_bound_evaluator, bound_evaluator])

        evaluations = to_annotation_dataframe(dataframe=results_df)
        await self.px_client.spans.log_span_annotations_dataframe(dataframe=evaluations)

        # Save cursor after successful processing
        last_row = spans_df.iloc[-1]
        self._save_cursor(
            timestamp=last_row["start_time"].isoformat(),
            span_id=last_row["context.span_id"],
        )

        logger.info(f"Processed {len(agent_spans)} spans")
        return {"processed": len(agent_spans), "status": "complete", "results": results_df}

    # Keep old method for backwards compatibility
    async def evaluate_last_session(self, project_name: str = "dcs-chat") -> pd.DataFrame | None:
        """Deprecated: Use run_scheduled_evaluation instead."""
        result = await self.run_scheduled_evaluation(project_name)
        return result.get("results")
