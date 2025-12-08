import asyncio
import os
from agent_framework.azure import AzureAIAgentClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv

load_dotenv()

async def main():

    settings = {
        "project_endpoint": os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        "model_deployment_name": os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        "async_credential": AzureCliCredential(),
    }
    async with (
        AzureAIAgentClient(**settings).create_agent(
            instructions="""
                            You are analyzing issues. 
                            If the ask is a feature request the complexity should be 'NA'.
                            If the issue is a bug, analyze the stack trace and provide the likely cause and complexity level
                        """,
            name="IssueAnalyzerAgent",
        ) as issue_analyzer_agent,
        
    ):
        task = """An issue in my Azure App Services is causing intermittent 500 errors. 
                    Traceback (most recent call last):
                                File "<string>", line 38, in <module>
                                    main_application()                    ← Entry point
                                File "<string>", line 30, in main_application
                                    results = process_data_batch(test_data)  ← Calls processor
                                File "<string>", line 13, in process_data_batch
                                    avg = calculate_average(batch)        ← Calls calculator
                                File "<string>", line 5, in calculate_average
                                    return total / count                  ← ERROR HERE
                                        ~~~~~~^~~~~~~
                                ZeroDivisionError: division by zero"""

        result = await issue_analyzer_agent.run(task)
        print(result.text)


if __name__ == "__main__":
    asyncio.run(main())
