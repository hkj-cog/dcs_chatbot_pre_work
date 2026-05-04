
import asyncio
from monitoring.gemini_eval import GeminiADKEvaluator
from monitoring.gemini_eval_gcp import GeminiADKGcpLogsEvaluator


async def main():
    # evaluator = GeminiADKEvaluator(project_id="dcs-chat")
    evaluator = GeminiADKGcpLogsEvaluator(project_id="cog01hygeb83z4tne1xxrhezf82e2")
    result = await evaluator.run_scheduled_evaluation("dcs_chatbot")
    print(result)

if __name__ == "__main__":
    asyncio.run(main())
