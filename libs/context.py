from contextvars import ContextVar

from opentelemetry.sdk.trace import Span

session_ctx: ContextVar[str | None] = ContextVar("session_ctx", default=None)
user_ctx: ContextVar[str | None] = ContextVar("user_ctx", default=None)
input_ctx: ContextVar[str | None] = ContextVar("input_ctx", default=None)
chain_input_ctx: ContextVar[str | None] = ContextVar("chain_input", default=None)
root_span_ctx: ContextVar[Span | None] = ContextVar("root_span", default=None)


