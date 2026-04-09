from langchain_core.prompts import PromptTemplate
from langchain_google_vertexai import ChatVertexAI

SCORE_PROMPT = """
You are responsible to generate a confidence score between (low, medium, high) based on question, answer and answer context.

Question: {question}
Answer: {answer}
context:{context}

Just output the confidence value
"""


class ConfidenceScorer:
    """
    ConfidenceScorer is a utility class that uses a large language model (LLM)
    to evaluate and score the confidence of an answer based on a question and its context.

    Attributes:
        _chain: A composed LangChain pipeline that formats the input using a prompt template,
                then sends it to the LLM to get a confidence evaluation.
    """

    def __init__(
        self, llm: str = "gemini-2.5-flash-lite-preview-06-17", location: str = "global"
    ):
        """
        Initializes the ConfidenceScorer with a specified LLM model and region.

        Args:
            llm (str): The name of the LLM model to use.
            location (str): The region where the model is deployed (e.g., 'global').
        """
        # Initialize the Vertex AI chat model with specified parameters
        llm = ChatVertexAI(model=llm, temperature=0, location=location)

        # Load the scoring prompt template (assumes SCORE_PROMPT is defined elsewhere)
        prompt = PromptTemplate.from_template(SCORE_PROMPT)

        # Create a chain where the prompt feeds into the LLM
        self._chain = prompt | llm

    def invoke(self, question, answer, context) -> str:
        """
        Invokes the confidence scoring chain with the given question, answer, and context.

        Args:
            question (str): The original question asked.
            answer (str): The answer to evaluate.
            context (str): The context or supporting information related to the question and answer.

        Returns:
            str: The LLM-generated confidence score or evaluation result.
        """
        return self._chain.invoke(
            {"question": question, "answer": answer, "context": context}
        ).content
