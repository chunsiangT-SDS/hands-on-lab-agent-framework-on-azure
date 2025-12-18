import os
import logging
from dotenv import load_dotenv

from agent_framework import GroupChatBuilder, HostedMCPTool, HostedVectorStoreContent, SequentialBuilder, ToolMode, HostedFileSearchTool
from agent_framework.azure import AzureAIAgentClient
from azure.identity.aio import AzureCliCredential
from agent_framework.devui import serve
from models.issue_analyzer import IssueAnalyzer
from tools.time_per_issue_tools import TimePerIssueTools
from agent_framework.observability import setup_observability

load_dotenv()

def create_workflow_instance():
    """Create and return workflow instance for reuse in API"""
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
        tool_choice=ToolMode.AUTO,
        tools=[
            timePerIssueTools.calculate_time_based_on_complexity,
        ],
    )

    jira_agent = AzureAIAgentClient(**settings).create_agent(
        name="JiraAgent",
        instructions=f"""
            You are a helpful assistant that can create and update Jira tickets following Contoso's guidelines.
            You work on this project: {os.environ.get("JIRA_PROJECT_KEY", "PROJECT")}
            
            WORKFLOW:
            1. Use the File Search tool to find "jira ticket guidelines"
            2. Follow the Contoso Jira Guidelines from the vector store
            3. Create or update Jira tickets using the Atlassian MCP tool with proper formatting
            
            Keep responses concise and focused on managing Jira tickets.
        """,
        tool_choice=ToolMode.AUTO,
        tools=[
            HostedFileSearchTool(
                description="Search for Contoso Jira ticket guidelines and templates in the vector store",
                inputs=HostedVectorStoreContent(vector_store_id=os.environ["VECTOR_STORE_ID"])
            ),
            HostedMCPTool(
                name="Atlassian MCP",
                url="https://mcp.atlassian.com/v1/sse",
                description="Atlassian MCP server for Jira interactions",
                approval_mode="never_require",
                headers={
                    "Authorization": f"Bearer {os.environ.get('ATLASSIAN_API_TOKEN', '')}",
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
                name="Ticket Creation Manager",
                instructions="""
                    You are a workflow manager for creating Jira tickets.
                    
                    WORKFLOW:
                    1. Use Issue Analyzer Agent to determine complexity and estimates
                    2. Use Jira Agent to search for guidelines and create the ticket
                    
                    Be concise. Complete the workflow in minimum steps.
                """,
            ),
        )
        .participants(
            jira_agent=jira_agent, 
            issue_analyzer_agent=issue_analyzer_agent
        )
        .build()
    )
    
    group_workflow_agent = group_workflow.as_agent(
        name="JiraTicketCreationAgentGroup"
    )
    
    # SIMPLIFIED: Use group workflow directly instead of sequential
    workflow = group_workflow_agent
    
    return workflow, issue_analyzer_agent, jira_agent, ms_learn_agent, group_workflow_agent

def main():
    # setup_observability()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    
    workflow, issue_analyzer_agent, jira_agent, ms_learn_agent, group_workflow_agent = create_workflow_instance()
    
    serve(entities=[issue_analyzer_agent, jira_agent, ms_learn_agent, group_workflow_agent, workflow], 
          port=8090, auto_open=True, tracing_enabled=True)

if __name__ == "__main__":
    main()