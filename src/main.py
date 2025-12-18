import os
from agent_framework import GroupChatBuilder, HostedMCPTool, HostedVectorStoreContent, SequentialBuilder, ToolMode, HostedFileSearchTool
from agent_framework.azure import AzureAIAgentClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv
from agent_framework.devui import serve
from models.issue_analyzer import IssueAnalyzer
from tools.time_per_issue_tools import TimePerIssueTools
from agent_framework.observability import setup_observability
import logging

load_dotenv()

def main():
    # setup_observability()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    
    settings = {
        "project_endpoint": os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        "model_deployment_name": os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        "credential": AzureCliCredential(),
    }
    timePerIssueTools = TimePerIssueTools()
    issue_analyzer_agent = AzureAIAgentClient(**settings).create_agent(
        instructions="""
            You are analyzing issues. 
            If the ask is a feature request the complexity should be 'NA'.
            If the issue is a bug, analyze the stack trace and provide the likely cause and complexity level.

            CRITICAL: You MUST use the provided tools for ALL calculations:
            1. First determine the complexity level
            2. Use the available tools to calculate time and cost estimates based on that complexity
            3. Never provide estimates without using the tools first

            Your response should contain only values obtained from the tool calls.
        """,
        name="IssueAnalyzerAgent",
        # response_format=IssueAnalyzer,
        tool_choice=ToolMode.AUTO,
        tools=[
            timePerIssueTools.calculate_time_based_on_complexity,
        ],
    )

    github_agent = AzureAIAgentClient(**settings).create_agent(
        name="GitHubAgent",
        instructions=f"""
            You are a helpful assistant that can create GitHub issues following Contoso's guidelines.
            You work on this repository: {os.environ["GITHUB_PROJECT_REPO"]}
            
            CRITICAL WORKFLOW:
            1. ALWAYS use the File Search tool FIRST to search for "github issues guidelines" or "issue template" to find the proper formatting and structure
            2. Follow the Contoso GitHub Issues Guidelines found in the vector store
            3. Use the retrieved guidelines to format the issue properly with correct structure, labels, and format
            4. Then use the GitHub MCP tool to create the issue with the properly formatted content
            
            IMPORTANT: You MUST search for guidelines BEFORE creating any issue to ensure compliance with company standards.
        """,
        tool_choice=ToolMode.AUTO,
        tools=[
            HostedFileSearchTool(
                description="Search for Contoso GitHub issues guidelines and templates in the vector store",
                inputs=HostedVectorStoreContent(vector_store_id=os.environ["VECTOR_STORE_ID"])
            ),
            HostedMCPTool(
                name="GitHub MCP",
                url="https://api.githubcopilot.com/mcp",
                description="A GitHub MCP server for GitHub interactions",
                approval_mode="never_require",
                # PAT token, restricting which repos the MCP Server
                headers={
                    "Authorization": f"Bearer {os.environ['GITHUB_MCP_PAT']}",
                },
            )
        ]

    )

    ms_learn_agent = AzureAIAgentClient(**settings).create_agent(
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
    )

    group_workflow = (
        GroupChatBuilder()
        .set_manager(
            manager=AzureAIAgentClient(**settings).create_agent(
                name="Issue Creation Group Chat Workflow",
                instructions="""
                    You are a workflow manager that helps create GitHub issues based on user input following Contoso's standards.
                    
                    WORKFLOW STEPS:
                    1. First, analyze the input using the Issue Analyzer Agent to determine the issue type, likely cause, and complexity
                    2. For GitHub issue creation, ALWAYS instruct the GitHub Agent to:
                       - Search for guidelines FIRST using the File Search tool
                       - Follow the retrieved Contoso guidelines for proper formatting
                       - Create the issue using the GitHub MCP tool with the proper structure
                    3. If additional documentation is needed, consult other specialized agents
                    
                    Ensure the GitHub Agent follows the company guidelines by explicitly requesting it to search for them.
                """,
            ),
        )
        .participants(
            github_agent=github_agent, issue_analyzer_agent=issue_analyzer_agent
        )
        .build()
    )
    
    group_workflow_agent = group_workflow.as_agent(
        name="IssueCreationAgentGroup"
    )
    workflow = (
        SequentialBuilder()
        .participants([ms_learn_agent, group_workflow_agent])
        .build()
    )

    serve(entities=[issue_analyzer_agent, github_agent, ms_learn_agent, group_workflow_agent, workflow], port=8090, auto_open=True, tracing_enabled=True)


if __name__ == "__main__":
    main()
