"""
Sentry-Jira Multi-Agent Workflow
================================

Three specialized agents work together:

1. TRIAGE AGENT - Quick severity assessment (5 seconds)
   Input: Sentry error data
   Output: Priority (Highest/High/Medium/Low), urgency flag

2. ANALYSIS AGENT - Root cause identification (10-15 seconds)
   Input: Sentry data + GitHub code context
   Output: Root cause, affected component, fix approach

3. SUMMARY AGENT - L2-friendly output (5 seconds)
   Input: Triage + Analysis results
   Output: Concise Jira comment for quick review
"""

import os
import re
import json
import base64
import asyncio
import httpx
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from enum import Enum
from dotenv import load_dotenv

from agent_framework import ChatMessage, ToolMode
from agent_framework.azure import AzureAIAgentClient
from azure.identity.aio import AzureCliCredential

load_dotenv()


# =============================================================================
# DATA MODELS
# =============================================================================

class Priority(Enum):
    HIGHEST = "Highest"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


@dataclass
class SentryIssueInfo:
    """Extracted from Jira description"""
    org_slug: str
    issue_id: str
    issue_url: str


@dataclass
class SentryIssueData:
    """Parsed Sentry issue data"""
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


@dataclass
class TriageResult:
    """Output from Triage Agent"""
    priority: Priority
    is_urgent: bool
    severity_reason: str  # One line explanation


@dataclass
class AnalysisResult:
    """Output from Analysis Agent"""
    root_cause: str       # One line
    affected_file: str    # File path
    fix_suggestion: str   # One line action
    confidence: str       # High/Medium/Low


@dataclass
class CodeContext:
    """GitHub code context"""
    file_path: str
    content: str
    language: str


# =============================================================================
# CONFIGURATION
# =============================================================================

# Match both numeric IDs (82134814) and short codes (BRMS-LOCAL-1Q)
SENTRY_URL_PATTERN = r'https://(?P<org>[\w-]+)\.sentry\.io/issues/(?P<issue_id>[\w-]+)'


@dataclass
class JiraConfig:
    cloud_id: str = "53c4a0e6-1418-4427-8db5-d27cfe9b1751"
    jira_url: str = "https://remarkgroup.atlassian.net"
    jira_project: str = "MAFB"


@dataclass
class SentryConfig:
    """Sentry API configuration"""
    auth_token: str = ""
    
    def __post_init__(self):
        self.auth_token = os.environ.get("SENTRY_AUTH_TOKEN", "")
    
    @property
    def is_configured(self) -> bool:
        return bool(self.auth_token)


# =============================================================================
# SENTRY REST API
# =============================================================================

async def fetch_sentry_issue_from_api(
    org_slug: str,
    issue_id: str,
    config: Optional[SentryConfig] = None,
    region_url: Optional[str] = None,
) -> Optional[SentryIssueData]:
    """
    Fetch Sentry issue details via REST API.
    
    Sentry API Docs: https://docs.sentry.io/api/events/retrieve-an-issue/
    
    Args:
        org_slug: Organization slug (e.g., 'scor-digital-solutions')
        issue_id: Issue ID (numeric like '82134814' or short code like 'BRMS-LOCAL-1Q')
        config: Sentry configuration with auth token
        region_url: Regional API URL (e.g., 'https://de.sentry.io' for EU)
    
    Returns:
        SentryIssueData or None if fetch failed
    """
    if config is None:
        config = SentryConfig()
    
    if not config.is_configured:
        print("  ⚠️ SENTRY_AUTH_TOKEN not configured")
        return None
    
    # Use regional URL if provided, otherwise default to sentry.io
    # For EU organizations, use https://de.sentry.io
    # Can also be detected from SENTRY_REGION env var
    if region_url is None:
        region_url = os.environ.get("SENTRY_REGION_URL", "https://sentry.io")
    
    # Sentry API endpoint using organization slug
    url = f"{region_url}/api/0/organizations/{org_slug}/issues/{issue_id}/"
    
    headers = {
        "Authorization": f"Bearer {config.auth_token}",
        "Content-Type": "application/json",
    }
    
    async with httpx.AsyncClient() as client:
        try:
            print(f"  Fetching from Sentry API: {url}")
            response = await client.get(url, headers=headers, timeout=30.0)
            
            if response.status_code == 200:
                data = response.json()
                return parse_sentry_api_response(data)
            elif response.status_code == 401:
                print(f"  ❌ Sentry API: Unauthorized - check SENTRY_AUTH_TOKEN")
                return None
            elif response.status_code == 404:
                # Try alternate endpoint (direct issue lookup)
                alt_url = f"{region_url}/api/0/issues/{issue_id}/"
                print(f"  Trying alternate endpoint: {alt_url}")
                alt_response = await client.get(alt_url, headers=headers, timeout=30.0)
                if alt_response.status_code == 200:
                    data = alt_response.json()
                    return parse_sentry_api_response(data)
                print(f"  ❌ Sentry API: Issue not found - {issue_id}")
                return None
            else:
                print(f"  ❌ Sentry API: {response.status_code} - {response.text[:200]}")
                return None
                
        except Exception as e:
            print(f"  ❌ Sentry API error: {e}")
            return None


def parse_sentry_api_response(data: Dict[str, Any]) -> SentryIssueData:
    """
    Parse Sentry REST API response into SentryIssueData.
    
    API Response structure:
    {
        "id": "12345",
        "shortId": "BRMS-LOCAL-1Q",
        "title": "NoMethodError: undefined method...",
        "culprit": "Api::V2::Sessions::PdfsController#show",
        "platform": "ruby",
        "count": "150",
        "userCount": 25,
        "firstSeen": "2025-12-09T09:09:30.000Z",
        "lastSeen": "2025-12-18T10:00:00.000Z",
        "status": "unresolved",
        "metadata": {
            "type": "NoMethodError",
            "value": "undefined method `[]' for nil:NilClass"
        },
        "permalink": "https://org.sentry.io/issues/12345/",
        ...
    }
    """
    # Extract basic info
    issue_key = data.get("shortId", data.get("id", "UNKNOWN"))
    
    # Build title from metadata
    metadata = data.get("metadata", {})
    error_type = metadata.get("type", "")
    error_value = metadata.get("value", "")
    title = data.get("title", f"{error_type}: {error_value}")
    
    # Extract counts
    occurrences = int(data.get("count", 0))
    users_impacted = int(data.get("userCount", 0))
    
    # Build error message
    error_message = f"{error_type}: {error_value}" if error_type else title
    
    # Extract stacktrace from latest event if available
    stacktrace = ""
    if "lastEvent" in data:
        event = data["lastEvent"]
        stacktrace = extract_stacktrace_from_event(event)
    
    return SentryIssueData(
        issue_key=issue_key,
        title=title,
        culprit=data.get("culprit", "Unknown"),
        platform=data.get("platform", "unknown"),
        occurrences=occurrences,
        users_impacted=users_impacted,
        first_seen=data.get("firstSeen", ""),
        last_seen=data.get("lastSeen", ""),
        status=data.get("status", "unknown"),
        error_message=error_message,
        stacktrace=stacktrace,
        url=data.get("permalink", ""),
    )


def extract_stacktrace_from_event(event: Dict[str, Any]) -> str:
    """Extract stacktrace from Sentry event data"""
    stacktrace_lines = []
    
    # Try to get exception data
    entries = event.get("entries", [])
    for entry in entries:
        if entry.get("type") == "exception":
            values = entry.get("data", {}).get("values", [])
            for exc in values:
                frames = exc.get("stacktrace", {}).get("frames", [])
                # Reverse to show most recent first
                for frame in reversed(frames[-10:]):  # Last 10 frames
                    filename = frame.get("filename", "?")
                    lineno = frame.get("lineNo", "?")
                    function = frame.get("function", "?")
                    context_line = frame.get("context_line", "").strip()
                    
                    line = f"  at {function} ({filename}:{lineno})"
                    if context_line:
                        line += f"\n    {context_line}"
                    stacktrace_lines.append(line)
    
    return "\n".join(stacktrace_lines)


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_atlassian_auth_header() -> str:
    """Basic Auth for Jira REST API"""
    email = os.environ.get("ATLASSIAN_EMAIL", "")
    api_token = os.environ.get("ATLASSIAN_API_TOKEN", "")
    credentials = f"{email}:{api_token}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return f"Basic {encoded}"


def extract_sentry_info(description: str) -> Optional[SentryIssueInfo]:
    """Extract Sentry URL from Jira description"""
    match = re.search(SENTRY_URL_PATTERN, description)
    if match:
        return SentryIssueInfo(
            org_slug=match.group('org'),
            issue_id=match.group('issue_id'),
            issue_url=match.group(0)
        )
    return None


def parse_sentry_mcp_response(mcp_response: str) -> SentryIssueData:
    """Parse Sentry MCP response into structured data"""
    def extract(pattern: str, default: str = "") -> str:
        match = re.search(pattern, mcp_response)
        return match.group(1) if match else default

    def extract_int(pattern: str, default: int = 0) -> int:
        match = re.search(pattern, mcp_response)
        return int(match.group(1)) if match else default

    # Extract stacktrace (first 20 lines for conciseness)
    stack_match = re.search(r'\*\*Full Stacktrace:\*\*\n.*?```\n(.+?)```', mcp_response, re.DOTALL)
    stacktrace = ""
    if stack_match:
        lines = stack_match.group(1).strip().split('\n')
        # Keep only application code lines (filter out framework code)
        app_lines = [l for l in lines if 'app/' in l or 'src/' in l or 'lib/' in l][:15]
        stacktrace = '\n'.join(app_lines) if app_lines else '\n'.join(lines[:15])

    return SentryIssueData(
        issue_key=extract(r'# Issue ([A-Z0-9-]+)', 'UNKNOWN'),
        title=extract(r'\*\*Description\*\*: (.+)', 'Unknown error'),
        culprit=extract(r'\*\*Culprit\*\*: (.+)', 'Unknown'),
        platform=extract(r'\*\*Platform\*\*: (.+)', 'unknown'),
        occurrences=extract_int(r'\*\*Occurrences\*\*: (\d+)'),
        users_impacted=extract_int(r'\*\*Users Impacted\*\*: (\d+)'),
        first_seen=extract(r'\*\*First Seen\*\*: (.+)'),
        last_seen=extract(r'\*\*Last Seen\*\*: (.+)'),
        status=extract(r'\*\*Status\*\*: (.+)', 'unknown'),
        error_message=extract(r'### Error\n+```\n(.+?)\n```', ''),
        stacktrace=stacktrace,
        url=extract(r'\*\*URL\*\*: (https://[^\s]+)'),
    )


def extract_files_from_stacktrace(stacktrace: str) -> List[str]:
    """Extract file paths from stack trace for GitHub lookup"""
    # Match patterns like: app/components/questions_component.rb:22
    pattern = r'(?:from |in )?(?:app|src|lib)/[\w/]+\.\w+'
    matches = re.findall(pattern, stacktrace)
    # Clean up and deduplicate
    files = list(set(m.replace('from ', '').replace('in ', '') for m in matches))
    return files[:5]  # Top 5 files


# =============================================================================
# AGENT 1: TRIAGE AGENT
# =============================================================================

def create_triage_agent():
    """Quick severity assessment agent"""
    settings = {
        "project_endpoint": os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        "model_deployment_name": os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        "credential": AzureCliCredential(),
    }
    
    return AzureAIAgentClient(**settings).create_agent(
        name="TriageAgent",
        instructions="""You are a quick triage agent for production errors.

Given error data, respond with EXACTLY this JSON format (no markdown, no explanation):
{
  "priority": "Highest|High|Medium|Low",
  "is_urgent": true|false,
  "reason": "One sentence explanation"
}

Priority rules:
- Highest: >100 occurrences OR >10 users OR security/data loss
- High: 10-100 occurrences OR 1-10 users OR critical feature broken
- Medium: <10 occurrences, 0 users, non-critical path
- Low: Single occurrence, no users, edge case

is_urgent = true if: production-breaking, security issue, or data corruption""",
        tool_choice=ToolMode.AUTO,
    )


async def run_triage_agent(sentry_data: SentryIssueData) -> TriageResult:
    """Run the triage agent for quick severity assessment"""
    agent = create_triage_agent()
    
    prompt = f"""Triage this error:
- Error: {sentry_data.title}
- Occurrences: {sentry_data.occurrences}
- Users: {sentry_data.users_impacted}
- Platform: {sentry_data.platform}
- Culprit: {sentry_data.culprit}

Respond with JSON only."""

    async with agent:
        message = ChatMessage("user", text=prompt)
        result = await agent.run(messages=[message])
        
        response_text = ""
        if result.messages:
            for msg in reversed(result.messages):
                if hasattr(msg, 'text') and msg.text:
                    response_text = msg.text
                    break
                elif hasattr(msg, 'contents'):
                    for content in msg.contents:
                        if hasattr(content, 'text'):
                            response_text = content.text
                            break

        # Parse JSON response
        try:
            # Extract JSON from response (might have markdown wrapper)
            json_match = re.search(r'\{[^}]+\}', response_text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return TriageResult(
                    priority=Priority[data.get("priority", "Medium").upper()],
                    is_urgent=data.get("is_urgent", False),
                    severity_reason=data.get("reason", "Unable to determine")
                )
        except (json.JSONDecodeError, KeyError):
            pass
        
        # Fallback
        return TriageResult(
            priority=Priority.MEDIUM,
            is_urgent=False,
            severity_reason="Auto-assigned: unable to parse triage response"
        )


# =============================================================================
# AGENT 2: ANALYSIS AGENT
# =============================================================================

def create_analysis_agent():
    """Deep root cause analysis agent"""
    settings = {
        "project_endpoint": os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        "model_deployment_name": os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        "credential": AzureCliCredential(),
    }
    
    return AzureAIAgentClient(**settings).create_agent(
        name="AnalysisAgent",
        instructions="""You are a senior engineer analyzing production errors.

Given error details and optionally code context, respond with EXACTLY this JSON format:
{
  "root_cause": "One sentence: what's causing this error",
  "affected_file": "path/to/file.ext:line",
  "fix_suggestion": "One sentence: what to do to fix it",
  "confidence": "High|Medium|Low"
}

Focus on:
1. Application code, not framework internals
2. The actual cause, not symptoms
3. Actionable fix, not vague suggestions

Be concise. One sentence per field.""",
        tool_choice=ToolMode.AUTO,
    )


async def run_analysis_agent(
    sentry_data: SentryIssueData,
    code_context: Optional[List[CodeContext]] = None
) -> AnalysisResult:
    """Run the analysis agent for root cause identification"""
    agent = create_analysis_agent()
    
    # Build prompt
    prompt = f"""Analyze this error:

**Error**: {sentry_data.title}
**Culprit**: {sentry_data.culprit}

**Stack Trace** (application code):
```
{sentry_data.stacktrace}
```
"""
    
    if code_context:
        prompt += "\n**Relevant Code**:\n"
        for ctx in code_context[:3]:  # Max 3 files
            prompt += f"\n`{ctx.file_path}`:\n```{ctx.language}\n{ctx.content}\n```\n"
    
    prompt += "\nRespond with JSON only."

    async with agent:
        message = ChatMessage("user", text=prompt)
        result = await agent.run(messages=[message])
        
        response_text = ""
        if result.messages:
            for msg in reversed(result.messages):
                if hasattr(msg, 'text') and msg.text:
                    response_text = msg.text
                    break
                elif hasattr(msg, 'contents'):
                    for content in msg.contents:
                        if hasattr(content, 'text'):
                            response_text = content.text
                            break

        # Parse JSON response
        try:
            json_match = re.search(r'\{[^}]+\}', response_text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return AnalysisResult(
                    root_cause=data.get("root_cause", "Unable to determine"),
                    affected_file=data.get("affected_file", "unknown"),
                    fix_suggestion=data.get("fix_suggestion", "Review stack trace manually"),
                    confidence=data.get("confidence", "Low")
                )
        except (json.JSONDecodeError, KeyError):
            pass
        
        # Fallback
        return AnalysisResult(
            root_cause="Unable to determine root cause automatically",
            affected_file=sentry_data.culprit,
            fix_suggestion="Manual review required",
            confidence="Low"
        )


# =============================================================================
# JIRA COMMENT FORMATTING (Concise L2 Format)
# =============================================================================

def format_concise_jira_comment(
    sentry_data: SentryIssueData,
    triage: TriageResult,
    analysis: AnalysisResult,
) -> str:
    """
    Format a concise, at-a-glance Jira comment for L2 support.
    
    Design goals:
    - Scannable in <10 seconds
    - Key info at the top
    - Action-oriented
    """
    urgent_flag = "🚨 URGENT" if triage.is_urgent else ""
    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    # Priority emoji
    priority_emoji = {
        Priority.HIGHEST: "🔴",
        Priority.HIGH: "🟠", 
        Priority.MEDIUM: "🟡",
        Priority.LOW: "🟢"
    }
    
    return f"""🤖 Sentry Auto-Analysis {urgent_flag}

{priority_emoji.get(triage.priority, "⚪")} Priority: {triage.priority.value} | {triage.severity_reason}

📍 Root Cause: {analysis.root_cause}
📁 File: {analysis.affected_file}
🔧 Fix: {analysis.fix_suggestion}
📊 Confidence: {analysis.confidence}

━━━━━━━━━━━━━━━━━━━━
📈 Stats: {sentry_data.occurrences} events | {sentry_data.users_impacted} users
🔗 Sentry: {sentry_data.url}
⏰ Analyzed: {today}
"""


def create_adf_comment(text: str) -> Dict[str, Any]:
    """Convert text to Atlassian Document Format"""
    paragraphs = text.strip().split('\n\n')
    content = []
    
    for para in paragraphs:
        if para.strip():
            lines = para.split('\n')
            para_content = []
            for i, line in enumerate(lines):
                if line.strip():
                    para_content.append({"type": "text", "text": line})
                    if i < len(lines) - 1:
                        para_content.append({"type": "hardBreak"})
            if para_content:
                content.append({"type": "paragraph", "content": para_content})
    
    return {"type": "doc", "version": 1, "content": content}


# =============================================================================
# JIRA API
# =============================================================================

async def add_comment_to_jira(issue_key: str, comment: str, config: JiraConfig) -> Dict[str, Any]:
    """Post comment to Jira"""
    url = f"{config.jira_url}/rest/api/3/issue/{issue_key}/comment"
    headers = {
        "Authorization": get_atlassian_auth_header(),
        "Content-Type": "application/json",
    }
    payload = {"body": create_adf_comment(comment)}
    
    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=payload, timeout=30.0)
        if response.status_code in [200, 201]:
            return {"status": "success"}
        return {"status": "error", "code": response.status_code, "error": response.text}


async def update_jira_priority(issue_key: str, priority: str, config: JiraConfig) -> Dict[str, Any]:
    """Update Jira issue priority"""
    url = f"{config.jira_url}/rest/api/3/issue/{issue_key}"
    headers = {
        "Authorization": get_atlassian_auth_header(),
        "Content-Type": "application/json",
    }
    payload = {"fields": {"priority": {"name": priority}}}
    
    async with httpx.AsyncClient() as client:
        response = await client.put(url, headers=headers, json=payload, timeout=30.0)
        if response.status_code in [200, 204]:
            return {"status": "success"}
        return {"status": "error", "code": response.status_code, "error": response.text}


# =============================================================================
# GITHUB CODE CONTEXT (Phase 3)
# =============================================================================

@dataclass
class GitHubConfig:
    """GitHub repository configuration"""
    owner: str = ""  # Set from env or config
    repo: str = ""   # Set from env or config
    branch: str = "main"


def get_github_config() -> GitHubConfig:
    """Load GitHub config from environment"""
    return GitHubConfig(
        owner=os.environ.get("GITHUB_REPO_OWNER", ""),
        repo=os.environ.get("GITHUB_REPO_NAME", ""),
        branch=os.environ.get("GITHUB_BRANCH", "main"),
    )


async def fetch_github_file_content(
    file_path: str,
    config: GitHubConfig
) -> Optional[CodeContext]:
    """
    Fetch a single file from GitHub using the REST API.
    
    For VS Code MCP integration, this would use github_repo tool instead.
    """
    if not config.owner or not config.repo:
        return None
    
    # GitHub Contents API
    url = f"https://api.github.com/repos/{config.owner}/{config.repo}/contents/{file_path}"
    headers = {
        "Accept": "application/vnd.github.v3.raw",
        "User-Agent": "SentryJiraAgent/1.0",
    }
    
    # Add auth if token available
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        headers["Authorization"] = f"token {token}"
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=10.0)
            if response.status_code == 200:
                content = response.text
                # Limit to ~50 lines around the relevant section
                lines = content.split('\n')
                if len(lines) > 100:
                    # Just get first 100 lines for context
                    content = '\n'.join(lines[:100]) + "\n... (truncated)"
                
                # Detect language from extension
                ext = file_path.split('.')[-1] if '.' in file_path else ''
                lang_map = {
                    'rb': 'ruby', 'py': 'python', 'js': 'javascript',
                    'ts': 'typescript', 'java': 'java', 'go': 'go',
                }
                
                return CodeContext(
                    file_path=file_path,
                    content=content,
                    language=lang_map.get(ext, ext)
                )
        except Exception as e:
            print(f"  ⚠️ Failed to fetch {file_path}: {e}")
    
    return None


async def fetch_github_code_context(
    file_paths: List[str],
    config: Optional[GitHubConfig] = None,
) -> List[CodeContext]:
    """
    Fetch code context from GitHub for files in the stack trace.
    
    This enables the Analysis Agent to see actual source code
    and provide more accurate root cause analysis.
    """
    if config is None:
        config = get_github_config()
    
    if not config.owner or not config.repo:
        print("  ⚠️ GitHub not configured (GITHUB_REPO_OWNER/GITHUB_REPO_NAME)")
        return []
    
    contexts = []
    for file_path in file_paths[:3]:  # Limit to 3 files
        ctx = await fetch_github_file_content(file_path, config)
        if ctx:
            contexts.append(ctx)
            print(f"  ✓ Fetched: {file_path}")
    
    return contexts


# =============================================================================
# MAIN WORKFLOW
# =============================================================================

async def process_sentry_issue(
    payload: Dict[str, Any],
    sentry_mcp_response: Optional[str] = None,
    github_code_context: Optional[List[CodeContext]] = None,
    fetch_github: bool = True,
) -> Dict[str, Any]:
    """
    Main multi-agent workflow:
    1. Extract Sentry URL from Jira description
    2. Fetch Sentry data (from API or provided response)
    3. Fetch GitHub code context (optional)
    4. Run Triage Agent → Priority
    5. Run Analysis Agent → Root cause
    6. Format concise comment
    7. Update Jira
    """
    issue_key = payload.get("issue", {}).get("key")
    description = payload.get("issue", {}).get("fields", {}).get("description", "")
    
    print(f"\n{'='*60}", flush=True)
    print(f"🤖 MULTI-AGENT SENTRY ANALYSIS", flush=True)
    print(f"{'='*60}", flush=True)
    print(f"Jira: {issue_key}", flush=True)
    print(f"Description (first 200 chars): {str(description)[:200]}", flush=True)
    
    # Step 1: Extract Sentry URL
    print(f"[Step 1] Extracting Sentry URL...", flush=True)
    sentry_info = extract_sentry_info(description)
    if not sentry_info:
        print(f"❌ No Sentry URL found in description", flush=True)
        return {"status": "error", "message": "No Sentry URL found"}
    print(f"✓ Sentry URL: {sentry_info.issue_url}", flush=True)
    
    # Step 2: Get Sentry data (either from provided response or fetch from API)
    print(f"[Step 2] Getting Sentry data...", flush=True)
    sentry_data = None
    
    if sentry_mcp_response:
        # Use provided MCP response
        sentry_data = parse_sentry_mcp_response(sentry_mcp_response)
        print(f"✓ Parsed provided Sentry data", flush=True)
    else:
        # Fetch from Sentry REST API
        print(f"[Sentry API] Fetching issue details...", flush=True)
        sentry_data = await fetch_sentry_issue_from_api(
            org_slug=sentry_info.org_slug,
            issue_id=sentry_info.issue_id,
        )
        if sentry_data:
            print(f"  ✓ Fetched from Sentry API", flush=True)
        else:
            print(f"  ❌ Failed to fetch from Sentry API", flush=True)
            return {
                "status": "error", 
                "message": "Failed to fetch Sentry data. Ensure SENTRY_AUTH_TOKEN is configured.",
                "sentry_info": {
                    "org": sentry_info.org_slug,
                    "issue_id": sentry_info.issue_id,
                }
            }
    
    print(f"✓ Error: {sentry_data.title[:50]}...", flush=True)
    print(f"  Occurrences: {sentry_data.occurrences} | Users: {sentry_data.users_impacted}", flush=True)
    
    # Step 3: Fetch GitHub code context (Phase 3)
    print(f"[Step 3] Fetching GitHub code context...", flush=True)
    # Step 3: Fetch GitHub code context (Phase 3)
    if fetch_github and github_code_context is None:
        print(f"[GitHub] Fetching code context...", flush=True)
        file_paths = extract_files_from_stacktrace(sentry_data.stacktrace)
        if file_paths:
            print(f"  Files in stack trace: {file_paths}", flush=True)
            github_code_context = await fetch_github_code_context(file_paths)
        else:
            print("  No application files found in stack trace", flush=True)
    else:
        print("  Skipping GitHub fetch", flush=True)
    
    # Step 4: Triage Agent
    print(f"[Step 4/Agent 1/2] Triage starting...", flush=True)
    triage = await run_triage_agent(sentry_data)
    print(f"  → Priority: {triage.priority.value} {'🚨 URGENT' if triage.is_urgent else ''}", flush=True)
    print(f"  → Reason: {triage.severity_reason}", flush=True)
    
    # Step 5: Analysis Agent (with code context)
    print(f"[Step 5/Agent 2/2] Analysis starting...", flush=True)
    if github_code_context:
        print(f"  Using {len(github_code_context)} file(s) for context", flush=True)
    analysis = await run_analysis_agent(sentry_data, github_code_context)
    print(f"  → Root cause: {analysis.root_cause[:60]}...", flush=True)
    print(f"  → Fix: {analysis.fix_suggestion[:60]}...", flush=True)
    
    # Step 6: Format comment
    print(f"[Step 6] Formatting Jira comment...", flush=True)
    comment = format_concise_jira_comment(sentry_data, triage, analysis)
    
    # Step 7: Update Jira
    print(f"[Step 7] Updating Jira...", flush=True)
    config = JiraConfig()
    
    comment_result = await add_comment_to_jira(issue_key, comment, config)
    priority_result = await update_jira_priority(issue_key, triage.priority.value, config)
    
    print(f"  → Comment: {comment_result['status']}", flush=True)
    print(f"  → Priority: {priority_result['status']}", flush=True)
    
    print(f"\n{'='*60}", flush=True)
    print(f"✅ COMPLETE", flush=True)
    print(f"{'='*60}\n", flush=True)
    
    return {
        "status": "success",
        "issue_key": issue_key,
        "triage": {
            "priority": triage.priority.value,
            "is_urgent": triage.is_urgent,
            "reason": triage.severity_reason,
        },
        "analysis": {
            "root_cause": analysis.root_cause,
            "file": analysis.affected_file,
            "fix": analysis.fix_suggestion,
            "confidence": analysis.confidence,
        },
        "jira": {
            "comment": comment_result["status"],
            "priority": priority_result["status"],
        }
    }


# =============================================================================
# TEST
# =============================================================================

async def test_multi_agent():
    """Test the multi-agent workflow"""
    
    # Sample Sentry MCP response
    sample_sentry = """# Issue BRMS-LOCAL-1Q in **scor-digital-solutions**

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
```

**Full Stacktrace:**
```
    from app/components/questions_component.rb:22:in `block in subsets_with_questions`
      rules = subset['rules'] || []
    from app/controllers/api/v2/sessions/pdfs_controller.rb:17:in `show`
            serve_pdf(session_pdf)
    from app/models/session_pdf.rb:42:in `create_pdf`
        .print(session.transformed_result(:document), translations)
```
"""
    
    # Test payload
    payload = {
        "issue": {
            "key": "MAFB-11",
            "fields": {
                "description": "Sentry Issue: [BRMS-LOCAL-1Q](https://scor-digital-solutions.sentry.io/issues/82134814/)"
            }
        }
    }
    
    result = await process_sentry_issue(payload, sample_sentry)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(test_multi_agent())
