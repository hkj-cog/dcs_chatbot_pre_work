from phoenix.client import Client

client = Client()
spans_df = client.spans.get_spans_dataframe(project_identifier="dcs-chat")
agent_spans = spans_df[spans_df["span_kind"] == "AGENT"]
agent_spans

from phoenix.evals.llm import LLM

llm = LLM(
    provider="openai",
    model="gpt-4o",
    client="openai",
)

from phoenix.evals.metrics import CorrectnessEvaluator

correctness_eval = CorrectnessEvaluator(llm=llm)

print(correctness_eval.describe())

from phoenix.evals import bind_evaluator, evaluate_dataframe
from phoenix.trace import suppress_tracing

bound_evaluator = bind_evaluator(
    evaluator=correctness_eval,
    input_mapping={
        "input": "attributes.input.value",
        "output": "attributes.output.value",
    },
)

with suppress_tracing():
    results_df = evaluate_dataframe(agent_spans, [bound_evaluator])
print(results_df)

