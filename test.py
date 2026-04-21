
import asyncio
from monitoring.gemini_eval import GeminiADKEvaluator


async def main():
    evaluator = GeminiADKEvaluator(project_id="dcs-chat")
    result = await evaluator.run_scheduled_evaluation()
    print(result)

if __name__ == "__main__":
    asyncio.run(main())
