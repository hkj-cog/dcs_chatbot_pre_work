"""LangChain / Vertex AI chain helpers shared across guardrail judges."""

import asyncio
import re

from langchain_core.prompts import PromptTemplate
from langchain_google_vertexai import ChatVertexAI

_VERDICT_TOKEN_RE = re.compile(r"^[A-Z][A-Z_]*$")  # single verdict token: UNBIASED, IN_SCOPE, etc.


def llm_chain(model_id: str, location: str, prompt_template: str):
    """Builds a LangChain prompt | ChatVertexAI chain (temperature=0)."""
    llm = ChatVertexAI(model=model_id, temperature=0, location=location)
    prompt = PromptTemplate.from_template(prompt_template)
    return prompt | llm


async def invoke_chain(chain, **kwargs) -> str:
    """Calls a chain and returns the result uppercased. Use for verdict-only judges."""
    result = await asyncio.to_thread(chain.invoke, kwargs)
    content = result.content
    if isinstance(content, list):
        content = " ".join(str(c) for c in content)
    return content.strip().upper()


async def invoke_chain_raw(chain, **kwargs) -> str:
    """Calls a chain and preserves original casing. Use when the LLM returns rewritten content."""
    result = await asyncio.to_thread(chain.invoke, kwargs)
    content = result.content
    if isinstance(content, list):
        content = " ".join(str(c) for c in content)
    return content.strip()


def parse_composite_verdict(output: str, key: str) -> str:
    """Extracts the verdict for a specific key from a composite judge response."""
    for line in output.splitlines():
        if line.strip().upper().startswith(f"{key}:"):
            return line.split(":", 1)[1].strip().upper()
    return ""


def validate_composite_verdict_format(output: str, expected_keys: list) -> None:
    """Asserts verdict lines match expected keys with single-token values; raises ValueError otherwise."""
    lines = [ln.strip() for ln in output.splitlines() if ln.strip()]
    if len(lines) != len(expected_keys):
        raise ValueError(
            f"Composite judge returned {len(lines)} lines, "
            f"expected {len(expected_keys)}: {output[:120]!r}"
        )
    for line, key in zip(lines, expected_keys):
        if not line.startswith(f"{key}:"):
            raise ValueError(
                f"Expected verdict line starting with '{key}:', got: {line!r}"
            )
        value = line.split(":", 1)[1].strip()
        if not _VERDICT_TOKEN_RE.match(value):
            raise ValueError(
                f"Verdict value for '{key}' is not a single token: {value!r}"
            )
