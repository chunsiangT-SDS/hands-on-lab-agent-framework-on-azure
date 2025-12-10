import asyncio
import os
from agent_framework.azure import AzureAIAgentClient
from agent_framework.observability import get_tracer, setup_observability
from agent_framework import (
    ChatAgent,
    HostedMCPTool,
    GroupChatBuilder,
    AgentRunUpdateEvent,
    SequentialBuilder,
)
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv
from models.issue_analyzer import IssueAnalyzer
from opentelemetry.trace import SpanKind
from opentelemetry.trace.span import format_trace_id

load_dotenv()


async def create_issue_analyzer_agent(chat_client: AzureAIAgentClient) -> ChatAgent:
    return ChatAgent(
        chat_client=chat_client,
        instructions="You are analyzing issues.",
        name="IssueAnalyzerAgent",
        response_format=IssueAnalyzer,
    )


async def create_ms_learn_agent(chat_client: AzureAIAgentClient) -> ChatAgent:
    return ChatAgent(
        chat_client=chat_client,
        name="DocsAgent",
        instructions="You are a helpful assistant that can help with microsoft documentation questions.",
        tools=HostedMCPTool(
            name="Microsoft Learn MCP",
            url="https://learn.microsoft.com/api/mcp",
            description="A Microsoft Learn MCP server for documentation questions",
            approval_mode="never_require",
        ),
    )


async def create_github_agent(chat_client: AzureAIAgentClient) -> ChatAgent:
    return ChatAgent(
        chat_client=chat_client,
        name="GitHubAgent",
        instructions="""
                You are a helpful assistant that can create an issue on the user's GitHub repository.
                To summmarize an issue, use the GitHub MCP tool. 
            """,
        tools=HostedMCPTool(
            name="GitHub MCP",
            url="https://api.githubcopilot.com/mcp",
            description="A GitHub MCP server for GitHub interactions",
            approval_mode="never_require",
            # PAT token, restricting which repos the MCP Server
            headers={
                "Authorization": f"Bearer {os.environ['GITHUB_MCP_PAT']}",
            },
        ),
    )


async def main():
    
    setup_observability(
        applicationinsights_connection_string=os.environ["APPLICATIONINSIGHTS_CONNECTION_STRING"], enable_sensitive_data=True
    )

    settings = {
        "project_endpoint": os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        "model_deployment_name": os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        "credential": AzureCliCredential(),
    }

    with get_tracer().start_as_current_span(
        "Sequential Workflow Scenario", kind=SpanKind.CLIENT
    ) as current_span:
        print(f"Trace ID: {format_trace_id(current_span.get_span_context().trace_id)}")

        async with (
            AzureAIAgentClient(**settings).create_agent(
                name="GitHubAgent",
                instructions=f"""
                        You are a helpful assistant that can create an issue on the user's GitHub repository based on the input provided.
                        To create the issue, use the GitHub MCP tool.
                        You work on this repository: {os.environ["GITHUB_PROJECT_REPO"]}
                    """,
                tools=HostedMCPTool(
                    name="GitHub MCP",
                    url="https://api.githubcopilot.com/mcp",
                    description="A GitHub MCP server for GitHub interactions",
                    approval_mode="never_require",
                    # PAT token, restricting which repos the MCP Server
                    headers={
                        "Authorization": f"Bearer {os.environ['GITHUB_MCP_PAT']}",
                    },
                ),
            ) as github_agent,
            AzureAIAgentClient(**settings).create_agent(
                instructions="""
                                You are analyzing issues. 
                                If the ask is a feature request the complexity should be 'NA'.
                                If the issue is a bug, analyze the stack trace and provide the likely cause and complexity level
                            """,
                name="IssueAnalyzerAgent",
                response_format=IssueAnalyzer,
            ) as issue_analyzer_agent,
            AzureAIAgentClient(**settings).create_agent(
                name="DocsAgent",
                instructions="""
                    You are a helpful assistant that can help with Microsoft documentation questions.
                    Provide accurate and concise information based on the documentation available.
                """,
                tools=HostedMCPTool(
                    name="Microsoft Learn MCP",
                    url="https://learn.microsoft.com/api/mcp",
                    description="A Microsoft Learn MCP server for documentation questions",
                    approval_mode="never_require",
                ),
            ) as ms_learn_agent,
        ):
            
  
            group_workflow = (
                GroupChatBuilder()
                .set_manager(
                    manager=AzureAIAgentClient(**settings).create_agent(
                        name="Issue Creation Group Chat Workflow",
                        instructions="""
                        You are a workflow manager that helps create GitHub issues based on user input.
                        First, analyze the input using the Issue Analyzer Agent to determine the issue type, likely cause, and complexity.
                        If an issue requires additional information from documentation, ask other specialized agents.
                        Finally, create a GitHub issue using the GitHub Agent with the analyzed information.
                    """,
                    ),
                )
                .participants(
                    github_agent=github_agent, issue_analyzer_agent=issue_analyzer_agent
                )
                .build()
            )

            group_workflow_agent = group_workflow.as_agent(
                name="GroupChatWorkflowAgent"
            )
            workflow = (
                SequentialBuilder()
                .participants([ms_learn_agent, group_workflow_agent])
                .build()
            )

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

            print("\nStarting Group Chat Workflow...\n")
            print(f"Input: {task}\n")

            try:
                print("[Agent Framework] Group chat conversation:")
                current_executor = None
                async for event in workflow.run_stream(task):
                    if isinstance(event, AgentRunUpdateEvent):
                        # Print executor name header when switching to a new agent
                        if current_executor != event.executor_id:
                            if current_executor is not None:
                                print()  # Newline after previous agent's message
                            print(f"---------- {event.executor_id} ----------")
                            current_executor = event.executor_id
                        if event.data:
                            print(event.data.text, end="", flush=True)
                print()  # Final newline after conversation

            except Exception as e:
                print(f"Workflow execution failed: {e}")


if __name__ == "__main__":
    asyncio.run(main())
