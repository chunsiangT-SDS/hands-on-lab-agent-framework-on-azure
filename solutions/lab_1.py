import os
from agent_framework.azure import AzureAIAgentClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv
from agent_framework.devui import serve
import logging

load_dotenv()

def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    
    settings = {
        "project_endpoint": os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        "model_deployment_name": os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        "credential": AzureCliCredential(),
    }
    issue_analyzer_agent = AzureAIAgentClient(**settings).create_agent(
        instructions="""
                        You are analyzing issues. 
                        If the ask is a feature request the complexity should be 'NA'.
                        If the issue is a bug, analyze the stack trace and provide the likely cause and complexity level
                    """,
        name="IssueAnalyzerAgent",
    ) 
    
    serve(entities=[issue_analyzer_agent], port=8090, auto_open=True, tracing_enabled=True)


if __name__ == "__main__":
    main()
