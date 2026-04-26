# LLM judge for confidence scoring — returns low/medium/high for a question/answer/context triple
import asyncio
import logging
from typing import Optional

from langchain_core.prompts import PromptTemplate
from langchain_google_vertexai import ChatVertexAI

_log = logging.getLogger("dcs_chatbot")

_VALID_SCORES = frozenset({"low", "medium", "high"})

SCORE_PROMPT = """
You are responsible to generate a confidence score based on how well the answer is supported by the context.

Question: {question}
Answer: {answer}
context:{context}

Answer with EXACTLY one word: low, medium, or high
"""


class ConfidenceScorer:
    """LLM judge that returns low/medium/high confidence for a question-answer-context triple."""

    def __init__(
        self, llm: str = "gemini-2.5-flash-lite-preview-06-17", location: str = "australia-southeast1"
    ):
        llm = ChatVertexAI(model=llm, temperature=0, location=location)
        prompt = PromptTemplate.from_template(SCORE_PROMPT)
        self._chain = prompt | llm

    # Runs the LLM confidence scoring chain and returns low/medium/high, or None on unexpected output
    async def invoke(self, question, answer, context) -> Optional[str]:
        result = await asyncio.to_thread(
            self._chain.invoke,
            {"question": question, "answer": answer, "context": context},
        )
        content = result.content
        if isinstance(content, list):
            content = " ".join(str(c) for c in content)
        score = content.strip().lower()
        if score not in _VALID_SCORES:
            _log.warning(
                f"[ConfidenceScorer] Unexpected verdict {score!r} — expected one of "
                f"{sorted(_VALID_SCORES)}. Treating as unscored."
            )
            return None
        return score
