"""
Sentry-Jira Integration Agent
Analyzes Sentry issues and updates Jira tickets with root cause analysis

Complete workflow:
1. Extract Sentry URL from Jira ticket description
2. Fetch Sentry issue details via Sentry API/MCP
3. Analyze with LLM for root cause and fixes
4. Post structured comment to Jira
5. Update Jira priority based on severity
"""

import os
import re
import json
import base64
import asyncio
import httpx
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum
from dotenv import load_dotenv

from agent_framework import ChatMessage, ToolMode
from agent_framework.azure import AzureAIAgentClient
from azure.identity.aio import AzureCliCredential

load_dotenv()


class Severity(Enum):
    """Issue severity for priority mapping"""
    CRITICAL = "Highest"  # Production-breaking, data loss
    HIGH = "High"         # Feature degradation, frequent errors
    MEDIUM = "Medium"     # Minor bugs, edge cases
    LOW = "Low"           # Cosmetic issues, rare occurrences


# Sentry URL extraction pattern (verified from real tickets)
SENTRY_URL_PATTERN = r'https://(?P<org>[\w-]+)\.sentry\.io/issues/(?P<issue_id>\d+)'


@dataclass
class SentryIssueInfo:
    """Extracted Sentry issue information"""
    org_slug: str
    issue_id: str
    issue_url: str


@dataclass
class SentryIssueData:
    """Full Sentry issue data for analysis"""
    issue_key: str
    title: str
    culprit: str
    platform: str
    occurrences: int
    users_impacted: int
    first_seen: str
    last_seen: str
    status: str
    error_message: str
    stacktrace: str
    tags: Dict[str, str] = field(default_factory=dict)
    url: str = ""
    
    def to_analysis_prompt(self) -> str:
        """Format for LLM analysis"""
        return f"""## Sentry Issue: {self.issue_key}

**Error**: {self.title}
**Culprit**: {self.culprit}
**Platform**: {self.platform}
**URL**: {self.url}

### Impact
- Occurrences: {self.occurrences}
- Users Impacted: {self.users_impacted}
- First Seen: {self.first_seen}
- Last Seen: {self.last_seen}
- Status: {self.status}

### Error Details
```
{self.error_message}
```

### Stack Trace
```
{self.stacktrace}
```

### Tags
{json.dumps(self.tags, indent=2)}"""


@dataclass
class AnalysisResult:
    """Structured analysis result from LLM"""
    root_causes: List[str]
    impact_assessment: str
    recommended_fixes: List[str]
    recommended_priority: str
    raw_analysis: str


@dataclass
class JiraConfig:
    """Jira configuration"""
    cloud_id: str = "53c4a0e6-1418-4427-8db5-d27cfe9b1751"
    jira_url: str = "https://remarkgroup.atlassian.net"
    jira_project: str = "MAFB"


def get_atlassian_auth_header() -> str:
    """Get Basic Auth header for Atlassian REST API"""
    email = os.environ.get("ATLASSIAN_EMAIL", "")
    api_token = os.environ.get("ATLASSIAN_API_TOKEN", "")
    credentials = f"{email}:{api_token}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return f"Basic {encoded}"


def extract_sentry_info(description: str) -> Optional[SentryIssueInfo]:
    """Extract Sentry issue info from Jira ticket description."""
    match = re.search(SENTRY_URL_PATTERN, description)
    if match:
        return SentryIssueInfo(
            org_slug=match.group('org'),
            issue_id=match.group('issue_id'),
            issue_url=match.group(0)
        )
    return None


async def fetch_sentry_issue(org_slug: str, issue_id: str) -> SentryIssueData:
    """
    Fetch Sentry issue details.
    
    In production, this uses the Sentry MCP via VS Code.
    For the agent workflow, we pass the data from the MCP call.
    """
    # This function will be called with data from Sentry MCP
    # The actual MCP call happens at the workflow orchestration level
    raise NotImplementedError("Use fetch_sentry_issue_from_mcp_response instead")


def parse_sentry_mcp_response(mcp_response: str) -> SentryIssueData:
    """
    Parse the Sentry MCP response into structured data.
    
    The MCP returns a markdown-formatted string, so we extract key fields.
    """
    # Extract issue key (e.g., BRMS-LOCAL-1Q)
    issue_key_match = re.search(r'# Issue ([A-Z0-9-]+)', mcp_response)
    issue_key = issue_key_match.group(1) if issue_key_match else "UNKNOWN"
    
    # Extract description/title
    desc_match = re.search(r'\*\*Description\*\*: (.+)', mcp_response)
    title = desc_match.group(1) if desc_match else "Unknown error"
    
    # Extract culprit
    culprit_match = re.search(r'\*\*Culprit\*\*: (.+)', mcp_response)
    culprit = culprit_match.group(1) if culprit_match else "Unknown"
    
    # Extract platform
    platform_match = re.search(r'\*\*Platform\*\*: (.+)', mcp_response)
    platform = platform_match.group(1) if platform_match else "unknown"
    
    # Extract occurrences
    occ_match = re.search(r'\*\*Occurrences\*\*: (\d+)', mcp_response)
    occurrences = int(occ_match.group(1)) if occ_match else 0
    
    # Extract users impacted
    users_match = re.search(r'\*\*Users Impacted\*\*: (\d+)', mcp_response)
    users_impacted = int(users_match.group(1)) if users_match else 0
    
    # Extract dates
    first_seen_match = re.search(r'\*\*First Seen\*\*: (.+)', mcp_response)
    first_seen = first_seen_match.group(1) if first_seen_match else ""
    
    last_seen_match = re.search(r'\*\*Last Seen\*\*: (.+)', mcp_response)
    last_seen = last_seen_match.group(1) if last_seen_match else ""
    
    # Extract status
    status_match = re.search(r'\*\*Status\*\*: (.+)', mcp_response)
    status = status_match.group(1) if status_match else "unknown"
    
    # Extract error message (from Error section)
    error_match = re.search(r'### Error\n+```\n(.+?)\n```', mcp_response, re.DOTALL)
    error_message = error_match.group(1).strip() if error_match else title
    
    # Extract stacktrace
    stack_match = re.search(r'\*\*Full Stacktrace:\*\*\n.*?```\n(.+?)```', mcp_response, re.DOTALL)
    stacktrace = stack_match.group(1).strip() if stack_match else ""
    
    # Extract URL
    url_match = re.search(r'\*\*URL\*\*: (https://[^\s]+)', mcp_response)
    url = url_match.group(1) if url_match else ""
    
    # Extract key tags
    tags = {}
    tag_patterns = [
        (r'\*\*environment\*\*: (.+)', 'environment'),
        (r'\*\*platform\*\*: (.+)', 'platform'),
        (r'\*\*transaction\*\*: (.+)', 'transaction'),
    ]
    for pattern, key in tag_patterns:
        match = re.search(pattern, mcp_response)
        if match:
            tags[key] = match.group(1)
    
    return SentryIssueData(
        issue_key=issue_key,
        title=title,
        culprit=culprit,
        platform=platform,
        occurrences=occurrences,
        users_impacted=users_impacted,
        first_seen=first_seen,
        last_seen=last_seen,
        status=status,
        error_message=error_message,
        stacktrace=stacktrace,
        tags=tags,
        url=url,
    )


async def add_comment_to_jira(
    issue_key: str,
    comment_body: str,
    config: JiraConfig
) -> Dict[str, Any]:
    """Add a comment to a Jira issue using the REST API"""
    url = f"{config.jira_url}/rest/api/3/issue/{issue_key}/comment"
    
    headers = {
        "Authorization": get_atlassian_auth_header(),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    
    # Convert text to proper ADF format
    payload = {
        "body": create_adf_comment(comment_body)
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=payload, timeout=30.0)
        
        if response.status_code in [200, 201]:
            return {"status": "success", "data": response.json()}
        else:
            return {"status": "error", "code": response.status_code, "error": response.text}


async def update_jira_priority(
    issue_key: str,
    priority_name: str,
    config: JiraConfig
) -> Dict[str, Any]:
    """Update the priority of a Jira issue"""
    url = f"{config.jira_url}/rest/api/3/issue/{issue_key}"
    
    headers = {
        "Authorization": get_atlassian_auth_header(),
        "Content-Type": "application/json",
    }
    
    payload = {
        "fields": {
            "priority": {
                "name": priority_name
            }
        }
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.put(url, headers=headers, json=payload)
        
        if response.status_code in [200, 204]:
            return {"status": "success"}
        else:
            return {"status": "error", "error": response.text}


def create_analysis_agent():
    """Create the Sentry issue analysis agent"""
    settings = {
        "project_endpoint": os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        "model_deployment_name": os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        "credential": AzureCliCredential(),
    }
    
    agent = AzureAIAgentClient(**settings).create_agent(
        name="SentryAnalysisAgent",
        instructions="""You are an expert software engineer analyzing production errors from Sentry.

Analyze the provided Sentry issue and provide a structured response with EXACTLY these sections:

## 🎯 Potential Root Cause(s)
List 1-3 potential root causes, ordered by confidence. For each:
- State the cause clearly
- Reference specific file/line from the stack trace
- Explain WHY this is likely the cause

## 📊 Impact Assessment
Summarize:
- Severity level (Critical/High/Medium/Low)
- User impact scope
- Business impact
- Urgency of fix

## 💡 Potential Fix(es)
For each root cause, provide:
1. **Immediate Fix**: Quick code change to resolve the issue
2. **Short-term**: Preventive measures
3. **Long-term**: Architectural improvements (if applicable)

Include specific code snippets where helpful.

## 📈 Recommended Priority
State one of: Highest, High, Medium, or Low

Base this on:
- Error frequency and user impact
- Whether it's a crash vs degradation
- Critical path vs edge case

Be concise but thorough. Focus on actionable insights.""",
        tool_choice=ToolMode.AUTO,
    )
    
    return agent


async def analyze_sentry_issue(sentry_data: SentryIssueData) -> AnalysisResult:
    """Use the LLM agent to analyze a Sentry issue"""
    agent = create_analysis_agent()
    
    prompt = sentry_data.to_analysis_prompt()
    
    async with agent:
        message = ChatMessage(
            "user",
            text=f"""Analyze this Sentry issue and provide your structured analysis:

{prompt}

Remember to include:
1. Potential Root Cause(s) with file/line references
2. Impact Assessment 
3. Potential Fix(es) with code snippets
4. Recommended Priority (Highest/High/Medium/Low)"""
        )
        
        result = await agent.run(messages=[message])
        
        analysis_text = "Unable to generate analysis"
        if result.messages:
            for msg in reversed(result.messages):
                if hasattr(msg, 'text') and msg.text:
                    analysis_text = msg.text
                    break
                elif hasattr(msg, 'contents'):
                    for content in msg.contents:
                        if hasattr(content, 'text'):
                            analysis_text = content.text
                            break
        
        # Extract recommended priority from analysis
        priority = "Medium"  # default
        if "Highest" in analysis_text:
            priority = "Highest"
        elif "High" in analysis_text and "Recommended Priority" in analysis_text:
            priority = "High"
        elif "Low" in analysis_text and "Recommended Priority" in analysis_text:
            priority = "Low"
        
        return AnalysisResult(
            root_causes=[],  # Could parse from analysis_text if needed
            impact_assessment="",
            recommended_fixes=[],
            recommended_priority=priority,
            raw_analysis=analysis_text,
        )


def format_jira_comment(
    sentry_data: SentryIssueData,
    analysis: AnalysisResult,
) -> str:
    """Format the analysis as a Jira comment"""
    today = datetime.now().strftime("%Y-%m-%d")
    
    return f"""🔍 Automated Sentry Issue Analysis

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 Issue Details
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Sentry Issue: {sentry_data.issue_key}
• URL: {sentry_data.url}
• Analysis Date: {today}

📊 Quick Stats
• Platform: {sentry_data.platform}
• Occurrences: {sentry_data.occurrences}
• Users Impacted: {sentry_data.users_impacted}
• Status: {sentry_data.status}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔍 AI Analysis
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{analysis.raw_analysis}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📈 Recommended Jira Priority: {analysis.recommended_priority}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

This analysis was generated automatically by the Sentry-Jira Agent.
Review the recommendations and adjust priority if needed."""


def create_adf_comment(text: str) -> Dict[str, Any]:
    """
    Convert plain text to Atlassian Document Format (ADF).
    Handles line breaks and basic formatting.
    """
    # Split text into paragraphs
    paragraphs = text.split('\n\n')
    
    content = []
    for para in paragraphs:
        if para.strip():
            # Handle lines within paragraph
            lines = para.split('\n')
            para_content = []
            
            for i, line in enumerate(lines):
                if line.strip():
                    para_content.append({
                        "type": "text",
                        "text": line
                    })
                    # Add hard break between lines (not after last)
                    if i < len(lines) - 1:
                        para_content.append({"type": "hardBreak"})
            
            if para_content:
                content.append({
                    "type": "paragraph",
                    "content": para_content
                })
    
    return {
        "type": "doc",
        "version": 1,
        "content": content if content else [{
            "type": "paragraph",
            "content": [{"type": "text", "text": text}]
        }]
    }


async def process_jira_webhook(
    payload: Dict[str, Any],
    sentry_mcp_response: Optional[str] = None
) -> Dict[str, Any]:
    """
    Main entry point for processing Jira webhook payloads.
    This is called when a new Sentry-created ticket is detected.
    
    Args:
        payload: Jira webhook payload with issue details
        sentry_mcp_response: Pre-fetched Sentry MCP response (optional)
    
    Returns:
        Dict with status and workflow results
    """
    issue_key = payload.get("issue", {}).get("key")
    description = payload.get("issue", {}).get("fields", {}).get("description", "")
    
    print(f"\n{'='*70}")
    print(f"📥 SENTRY-JIRA AGENT WORKFLOW")
    print(f"{'='*70}")
    print(f"Processing Jira ticket: {issue_key}")
    
    # Step 1: Extract Sentry URL from description
    print(f"\n[Step 1/5] Extracting Sentry URL...")
    sentry_info = extract_sentry_info(description)
    if not sentry_info:
        return {"status": "error", "message": "No Sentry URL found in description"}
    
    print(f"  ✅ Found Sentry issue: {sentry_info.issue_url}")
    print(f"     Org: {sentry_info.org_slug}")
    print(f"     Issue ID: {sentry_info.issue_id}")
    
    # Step 2: Parse Sentry data
    print(f"\n[Step 2/5] Fetching Sentry issue details...")
    if sentry_mcp_response:
        sentry_data = parse_sentry_mcp_response(sentry_mcp_response)
        print(f"  ✅ Parsed Sentry data:")
        print(f"     Issue: {sentry_data.issue_key}")
        print(f"     Error: {sentry_data.title[:60]}...")
        print(f"     Occurrences: {sentry_data.occurrences}")
        print(f"     Users: {sentry_data.users_impacted}")
    else:
        # If no MCP response provided, we need to fetch it
        # For now, return with instructions
        return {
            "status": "pending_sentry_data",
            "message": "Please provide Sentry MCP response",
            "sentry_info": {
                "org": sentry_info.org_slug,
                "issue_id": sentry_info.issue_id,
                "url": sentry_info.issue_url
            }
        }
    
    # Step 3: Analyze with LLM
    print(f"\n[Step 3/5] Analyzing with AI agent...")
    try:
        analysis = await analyze_sentry_issue(sentry_data)
        print(f"  ✅ Analysis complete")
        print(f"     Recommended Priority: {analysis.recommended_priority}")
    except Exception as e:
        print(f"  ❌ Analysis failed: {e}")
        # Create a fallback analysis
        analysis = AnalysisResult(
            root_causes=[],
            impact_assessment="Analysis failed",
            recommended_fixes=[],
            recommended_priority="Medium",
            raw_analysis=f"Error during analysis: {str(e)}\n\nPlease review the Sentry issue manually."
        )
    
    # Step 4: Format and post comment to Jira
    print(f"\n[Step 4/5] Posting analysis to Jira...")
    config = JiraConfig()
    comment = format_jira_comment(sentry_data, analysis)
    
    comment_result = await add_comment_to_jira(issue_key, comment, config)
    if comment_result["status"] == "success":
        print(f"  ✅ Comment posted successfully")
    else:
        print(f"  ❌ Comment failed: {comment_result.get('error', 'Unknown error')}")
    
    # Step 5: Update priority if different
    print(f"\n[Step 5/5] Updating Jira priority...")
    priority_result = await update_jira_priority(
        issue_key, 
        analysis.recommended_priority, 
        config
    )
    if priority_result["status"] == "success":
        print(f"  ✅ Priority updated to: {analysis.recommended_priority}")
    else:
        print(f"  ⚠️ Priority update failed: {priority_result.get('error', 'Unknown error')}")
    
    print(f"\n{'='*70}")
    print(f"✅ WORKFLOW COMPLETE")
    print(f"{'='*70}\n")
    
    return {
        "status": "success",
        "issue_key": issue_key,
        "sentry_info": {
            "org": sentry_info.org_slug,
            "issue_id": sentry_info.issue_id,
            "url": sentry_info.issue_url
        },
        "analysis": {
            "recommended_priority": analysis.recommended_priority,
        },
        "jira_updates": {
            "comment": comment_result["status"],
            "priority": priority_result["status"]
        }
    }


# Test the workflow
async def test_workflow():
    """Test the complete workflow with sample data"""
    
    # Sample Sentry MCP response (what we get from mcp_sentry-mcp-se_get_issue_details)
    sample_sentry_response = """# Issue BRMS-LOCAL-1Q in **scor-digital-solutions**

**Description**: NoMethodError: undefined method `[]' for nil:NilClass (NoMethodError)
**Culprit**: Api::V2::Sessions::PdfsController#show
**First Seen**: 2025-12-09T09:09:30.000Z
**Last Seen**: 2025-12-09T09:09:30.000Z
**Occurrences**: 1
**Users Impacted**: 0
**Status**: unresolved
**Platform**: ruby
**URL**: https://scor-digital-solutions.sentry.io/issues/BRMS-LOCAL-1Q

### Error

```
NoMethodError: undefined method `[]' for nil:NilClass (NoMethodError)

      rules = subset['rules'] || []
                    ^^^^^^^^^
```

**Full Stacktrace:**
```
    from app/components/questions_component.rb:22:in `block in subsets_with_questions`

    19 │ 

    20 │   def subsets_with_questions

    21 │     subsets_with_rules.map do |subset|

  → 22 │       rules = subset['rules'] || []

    23 │       next if rules.empty?

    from app/controllers/api/v2/sessions/pdfs_controller.rb:17:in `show`
            serve_pdf(session_pdf)

    from app/controllers/api/v2/sessions/pdfs_controller.rb:31:in `serve_pdf`
            session_pdf.create_pdf

    from app/models/session_pdf.rb:42:in `create_pdf`
        .print(session.transformed_result(:document), translations)
```

### Tags
**environment**: production
**platform**: ruby
**transaction**: Api::V2::Sessions::PdfsController#show
"""

    # Simulate a Jira webhook payload
    # NOTE: Use a real issue key from your MAFB project for actual testing
    test_payload = {
        "webhookEvent": "jira:issue_created",
        "issue": {
            "key": "MAFB-11",  # Using existing test issue
            "id": "92924",
            "fields": {
                "summary": "NoMethodError in questions_component.rb",
                "description": "Sentry Issue: [BRMS-LOCAL-1Q](https://scor-digital-solutions.sentry.io/issues/82134814/?referrer=jira_integration)",
                "priority": {"name": "Medium"},
                "project": {"key": "MAFB"}
            }
        }
    }
    
    result = await process_jira_webhook(test_payload, sample_sentry_response)
    print(f"\n📋 Final Result:")
    print(json.dumps(result, indent=2))


async def test_parse_only():
    """Test just the Sentry parsing without LLM"""
    sample_response = """# Issue BRMS-LOCAL-1Q in **scor-digital-solutions**

**Description**: NoMethodError: undefined method `[]' for nil:NilClass (NoMethodError)
**Culprit**: Api::V2::Sessions::PdfsController#show
**First Seen**: 2025-12-09T09:09:30.000Z
**Last Seen**: 2025-12-09T09:09:30.000Z
**Occurrences**: 1
**Users Impacted**: 0
**Status**: unresolved
**Platform**: ruby
**URL**: https://scor-digital-solutions.sentry.io/issues/BRMS-LOCAL-1Q
"""
    
    data = parse_sentry_mcp_response(sample_response)
    print("Parsed Sentry Data:")
    print(f"  Issue Key: {data.issue_key}")
    print(f"  Title: {data.title}")
    print(f"  Culprit: {data.culprit}")
    print(f"  Platform: {data.platform}")
    print(f"  Occurrences: {data.occurrences}")
    print(f"  Users: {data.users_impacted}")
    print(f"  URL: {data.url}")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--parse-only":
        asyncio.run(test_parse_only())
    else:
        asyncio.run(test_workflow())
