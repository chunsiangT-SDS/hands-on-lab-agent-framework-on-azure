# Sentry-Jira Agent Workflow Plan

## Overview

This document outlines the plan for building an agent workflow that automates the analysis of Sentry issues and updates corresponding Jira tickets with root cause analysis and potential solutions.

## Workflow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                    SENTRY-JIRA AGENT                                    │
│                                    WORKFLOW DIAGRAM                                     │
└─────────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────┐         ┌──────────────────┐         ┌─────────────────────────┐
│  Sentry Alert   │         │  Issue Created   │         │  Jira Automation Rule   │
│  (Production)   │────────▶│  in SI project   │────────▶│  When Issue Created +   │
│                 │         │  (e.g., SI-3568) │         │  Description contains   │
└─────────────────┘         │                  │         │  'sentry.io'            │
                            │  Description:    │         └─────────┬──────────────┘
                            │  - Sentry URL    │                   │
                            │  - Stack trace   │                   │ HTTP POST
                            │  - Labels        │                   ▼
                            └──────────────────┘         ┌─────────────────────────┐
                                                         │  Azure VM Endpoint      │
                                                         │  mafb@20.255.50.129     │
                                                         │  (Agent Workflow)       │
                                                         └─────────┬──────────────┘
                                                                   │
                        ┌──────────────────────────────────────────┼──────────────────────────────────────┐
                        │                                          │                                      │
                        ▼                                          ▼                                      ▼
        ┌──────────────────────────┐      ┌────────────────────────────┐      ┌──────────────────────────────┐
        │ Step 1: Parse Sentry URL │      │ Step 2: Fetch Sentry Data  │      │ Step 3: Get Code Context     │
        │ from ticket description  │      │ via Sentry MCP             │      │ via GitHub MCP               │
        │                          │      │                            │      │                              │
        │ Extract:                 │      │ - Issue details            │      │ - Find relevant code         │
        │ • org_slug               │      │ - Stack trace              │      │ - Retrieve file content      │
        │ • issue_id               │      │ - Error frequency          │      │ - Understand context         │
        │ • issue_url              │      │ - Affected users (if Seer) │      │ - Identify potential fixes   │
        └──────────────┬───────────┘      └────────────┬───────────────┘      └──────────────┬───────────────┘
                       │                               │                                      │
                       └───────────────────┬───────────┴──────────────────────┬───────────────┘
                                           │                                  │
                                           ▼                                  ▼
                        ┌──────────────────────────────────────────────────────────────────┐
                        │   Step 4: LLM Analysis & Root Cause Determination               │
                        │   (Microsoft Agent Framework)                                    │
                        │                                                                 │
                        │   Inputs:                         Output:                       │
                        │   • Sentry data                   • Potential root causes       │
                        │   • Stack trace                   • Potential fixes             │
                        │   • Code context (optional)       • Impact assessment           │
                        │   • Jira issue key (MAFB-*)       • Recommended priority       │
                        └──────────────────────┬─────────────────────────────────────────┘
                                               │
                                               ▼
                        ┌──────────────────────────────────────────────────────────────────┐
                        │     Step 5: Update MAFB Jira Ticket via Atlassian MCP           │
                        │                                                                 │
                        │     Actions:                                                    │
                        │     • addCommentToJiraIssue()  → Structured analysis            │
                        │     • editJiraIssue()          → Update priority                │
                        │     • transitionJiraIssue()    → Move to "In Analysis" (opt)    │
                        │                                                                 │
                        │     Comment includes:                                           │
                        │     - Impact Assessment (severity, users, events)               │
                        │     - Potential Root Causes (with confidence)                   │
                        │     - Potential Fixes (immediate/short/long-term)               │
                        │     - Recommended Priority                                      │
                        └──────────────────────────────────────────────────────────────────┘
                                               │
                                               ▼
                        ┌──────────────────────────────────────────────────────────────────┐
                        │   L2 Support Team Reviews & Assigns Work                        │
                        │   - MAFB ticket updated with analysis                           │
                        │   - Priority adjusted based on impact                           │
                        │   - Ready for triage/assignment                                 │
                        └──────────────────────────────────────────────────────────────────┘
```

---

## Project-Specific Configuration

| Setting | Value |
|---------|-------|
| **Jira Cloud ID** | `53c4a0e6-1418-4427-8db5-d27cfe9b1751` |
| **Jira Project** | MAFB (target), SI (sample ticket) |
| **Jira URL** | https://remarkgroup.atlassian.net |
| **Trigger Method** | Jira Automation → HTTP Webhook |
| **Sentry Issue Source** | Extracted from ticket description (Sentry auto-creates tickets) |
| **Sentry Org** | `scor-digital-solutions` |
| **Azure VM** | `mafb@20.255.50.129` (SSH access) |

### Trigger Flow

1. **Sentry Alert fires** → Creates Jira ticket automatically (via Sentry-Jira integration)
2. **Jira Automation rule** detects new ticket creation
3. **Automation sends HTTP POST** to our agent workflow endpoint with:
   - `issueKey` (e.g., `MAFB-123`)
   - `issueId`
   - Optionally: description containing Sentry link
4. **Agent workflow** processes and updates the ticket

## MCP Integrations

### 1. Sentry MCP (https://mcp.sentry.dev/mcp)
**Purpose:** Fetch detailed issue data from Sentry
**Status:** ✅ **Required**

**Key Operations:**
- Get issue details (stack trace, error message, metadata)
- Analyze issue with Seer (AI-powered root cause analysis)
- Get event attachments if needed

### 2. GitHub MCP
**Purpose:** Access codebase for context and root cause analysis
**Status:** ✅ **Required** (Essential for accurate root cause determination)

**Key Operations:**
- Search for relevant code files from stack trace
- Retrieve file content and surrounding context
- Understand error location in actual code
- Identify potential fixes in codebase

### 3. Atlassian MCP ⭐ (Primary Focus)
**Purpose:** Update Jira tickets with analysis results
**Status:** ✅ **Required**

---

## Atlassian REST API v3 - Jira Update Implementation

> ✅ **IMPLEMENTED**: Using Atlassian REST API v3 directly instead of MCP for faster iteration during hackathon.
> This provides direct control over authentication (Basic Auth with email:api_token) and request/response handling.

### Available Operations for Updating Jira Tickets

#### 1. Add Comment to Jira Issue
**Endpoint:** `POST /rest/api/3/issue/{issueKey}/comment`

**Authentication:** Basic Auth with email:api_token (Base64 encoded)

**Request Body (ADF - Atlassian Document Format):**
```json
{
  "body": {
    "type": "doc",
    "version": 1,
    "content": [
      {
        "type": "paragraph",
        "content": [
          {
            "type": "text",
            "text": "🔍 Automated Sentry Issue Analysis..."
          }
        ]
      }
    ]
  }
}
```

**Implementation:** Implemented in `sentry_jira_agent.py` as `add_comment_to_jira()`

#### 2. Edit Jira Issue (Update Priority)
**Endpoint:** `PUT /rest/api/3/issue/{issueKey}`

**Implementation:** Implemented in `sentry_jira_agent.py` as `update_jira_priority()`

**Request Body:**
```json
{
  "fields": {
    "priority": {
      "name": "High"
    }
  }
}
```

---

## Appendix: MCP vs REST API Decision

**Why REST API for hackathon:**
- ✅ Simpler authentication (Basic Auth vs OAuth)
- ✅ Direct request/response control
- ✅ No MCP server infrastructure needed
- ✅ Faster iteration and debugging
- ✅ Standard HTTP tools (httpx, Postman)

**MCP advantages (for future):**
- Better abstraction layer
- Unified tool interface
- Better error handling
- Standardized patterns

---

## Appendix: Verified MCP Tools (Reference Only)

---

## Priority Mapping Strategy

Map Sentry issue severity to Jira priority based on complexity analysis:

| Complexity | Jira Priority | Criteria |
|------------|---------------|----------|
| `HIGH` | Highest/Critical | Production-breaking, data loss, security issues |
| `MEDIUM` | High | Feature degradation, performance issues |
| `LOW` | Medium | Minor bugs, cosmetic issues |
| `NA` | Low | Unknown or unclassified |

### Proposed Complexity Enum (Already Exists)
```python
class Complexity(Enum):
    NA = 0      # → Low priority
    LOW = 1    # → Medium priority
    MEDIUM = 2 # → High priority
    HIGH = 3   # → Highest priority
```

### Priority Determination Factors
1. **Error frequency** - How often the error occurs
2. **User impact** - Number of affected users
3. **Error type** - Crash vs warning vs info
4. **Stack trace depth** - Complexity of the issue
5. **Code location** - Critical path vs edge case

---

## Implementation Steps

### Phase 1: Setup & Authentication ✅ COMPLETE
- [x] Configure Atlassian REST API v3 (with Basic Auth)
- [x] Configure Sentry MCP connection
- [x] Configure GitHub MCP connection
- [x] Obtain and store `cloudId` for Jira instance (`53c4a0e6-1418-4427-8db5-d27cfe9b1751`)
- [x] Test basic connectivity to all MCPs
- [x] Created `config.py` with all credentials
- [x] Created `phase_1_setup.py` test script
- [x] **Tested Jira REST API - Successfully created issue in MAFB project**

### Phase 2: Sentry Issue Analysis ✅ COMPLETE
- [x] **Extract Sentry URL from Jira description**
  - Parse description for Sentry links (regex pattern below)
  - Extract organization slug, project slug, and issue ID
- [x] Implement Sentry issue fetching using `mcp_sentry-mcp-se_get_issue_details`
- [x] Extract key data: stack trace, error message, affected users, frequency
- [x] Use LLM to analyze and summarize the issue
- [x] **Tested with real Sentry issue BRMS-LOCAL-1Q** - Full workflow working

**Sentry URL Extraction Pattern:**

> ✅ **VERIFIED** from sample ticket SI-3568

**Sample Description Format:**
```
Sentry Issue: [BRMS-LOCAL-1Q](https://scor-digital-solutions.sentry.io/issues/82134814/?referrer=jira_integration)

```java
NoMethodError: undefined method `[]' for nil:NilClass (NoMethodError)
... stack trace ...
```

This ticket was automatically created by Sentry via [Jira issues for BRMS Local Production](...)
```

**Key Data Points:**
- Sentry Issue Key: `BRMS-LOCAL-1Q`
- Sentry Issue ID: `82134814`
- Sentry Org: `scor-digital-solutions`
- Sentry URL: `https://scor-digital-solutions.sentry.io/issues/82134814/`

```python
import re

# Verified pattern based on SI-3568
SENTRY_URL_PATTERN = r'https://(?P<org>[\w-]+)\.sentry\.io/issues/(?P<issue_id>\d+)'

def extract_sentry_info(description: str) -> dict | None:
    """Extract Sentry issue info from Jira ticket description."""
    match = re.search(SENTRY_URL_PATTERN, description)
    if match:
        return {
            'org_slug': match.group('org'),           # e.g., 'scor-digital-solutions'
            'issue_id': match.group('issue_id'),      # e.g., '82134814'
            'issue_url': match.group(0)               # full URL
        }
    return None

# Example usage:
description = """Sentry Issue: [BRMS-LOCAL-1Q](https://scor-digital-solutions.sentry.io/issues/82134814/?referrer=jira_integration)"""
result = extract_sentry_info(description)
# {'org_slug': 'scor-digital-solutions', 'issue_id': '82134814', 'issue_url': 'https://scor-digital-solutions.sentry.io/issues/82134814'}
```

### Phase 3: Codebase Context ✅ COMPLETE
- [x] Extract file paths from stack trace automatically
- [x] Use GitHub REST API to fetch source code (when configured)
- [x] Pass code context to Analysis Agent for better accuracy
- [x] Implemented `fetch_github_code_context()` function
- **Config:** Set `GITHUB_REPO_OWNER` and `GITHUB_REPO_NAME` env vars to enable

### Phase 4: Jira Integration ✅ COMPLETE
- [x] Obtained `cloudId`: `53c4a0e6-1418-4427-8db5-d27cfe9b1751`
- [x] Implement `add_comment_to_jira()` with ADF formatting
- [x] Implement `update_jira_priority()` via REST API
- [x] Comment template with AI analysis, root causes, fixes, impact
- [x] **Tested on MAFB-11** - Comment posted and priority updated successfully

### Phase 5: Agent Workflow Integration ✅ COMPLETE
- [x] Created `agents/sentry_jira_multi_agent.py` with Microsoft Agent Framework
- [x] **Multi-Agent Architecture:**
  - **Triage Agent**: Quick severity assessment → Priority + Urgency
  - **Analysis Agent**: Root cause identification → File + Fix + Confidence
- [x] Complete workflow: Extract URL → GitHub Context → Triage → Analysis → Jira
- [x] **Concise L2 Format**: At-a-glance output (<10 second scan)
- [x] Added error handling and fallbacks
- [x] **HTTP Webhook Endpoint**: `agents/server.py` (FastAPI)
  - `POST /analyze` - Main endpoint for Postman testing
  - `POST /webhook/sentry` - Sentry alert receiver
  - `POST /webhook/jira` - Jira webhook receiver
  - `GET /health` - Health check
- [x] **Postman Collection**: `agents/postman_collection.json`
- [x] **User Guide**: `agents/README.md`

### Phase 6: Deployment to Azure VM ⏳ PENDING
- [ ] SSH to `mafb@20.255.50.129`
- [ ] Clone/pull repository
- [ ] Install dependencies (`uv sync`)
- [ ] Configure `.env` with production credentials
- [ ] Start server: `uv run uvicorn agents.server:app --host 0.0.0.0 --port 8000`
- [ ] Test endpoint: `curl http://20.255.50.129:8000/health`

---

## Postman Testing (Hackathon Approach)

For the hackathon, we'll use Postman to manually trigger the agent workflow instead of setting up Jira Automation. This allows for faster iteration and testing.

### HTTP Endpoint

**Base URL:** `http://20.255.50.129:8000` (Azure VM)

**Endpoints:**
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/` | GET | API info |
| `/health` | GET | Health check |
| `/analyze` | POST | **Main endpoint** - trigger full analysis |
| `/webhook/sentry` | POST | Receive Sentry alerts |
| `/webhook/jira` | POST | Receive Jira webhooks |
| `/docs` | GET | Swagger UI |

### Request Headers

```
Content-Type: application/json
Authorization: Bearer YOUR_TOKEN (if needed)
```

### Postman Request Body

Use this payload structure when testing in Postman. You can copy a real Jira ticket's description field:

```json
{
  "webhookEvent": "jira:issue_created",
  "issue": {
    "key": "MAFB-123",
    "id": "10000",
    "fields": {
      "summary": "High CPU usage in user authentication service",
      "description": "Sentry Issue: [BRMS-LOCAL-1Q](https://scor-digital-solutions.sentry.io/issues/82134814/?referrer=jira_integration)",
      "priority": {
        "name": "High"
      },
      "project": {
        "key": "MAFB"
      }
    }
  },
  "timestamp": "2025-12-18T10:30:00Z"
}
```

### Testing Steps in Postman

1. **Import the collection**: `agents/postman_collection.json`
2. Open Postman and select "Analyze Sentry Issue - Full Example"
3. Update the `base_url` variable:
   - Local: `http://localhost:8000`
   - Production: `http://20.255.50.129:8000`
4. Click **Send**
5. Expected response: `200 OK` with analysis results

**Alternative: Manual curl test**
```bash
curl -X POST http://20.255.50.129:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "jira_issue_key": "MAFB-11",
    "sentry_org": "scor-digital-solutions",
    "sentry_issue_id": "BRMS-LOCAL-1Q",
    "sentry_data_raw": "# Issue BRMS-LOCAL-1Q\n\n**Description**: NoMethodError..."
  }'
```

### Future: Jira Automation Rule

Once the workflow is stable, this can be automated with a Jira Automation rule:
- **When:** Issue created in MAFB
- **If:** Description contains `sentry.io`
- **Then:** Send HTTP POST to the endpoint above

---

## Comment Template Design

The Jira comment should include three key sections as requested:
1. **Potential Root Cause** - What's causing the issue
2. **Potential Fix** - Recommended solutions
3. **Impact** - Severity and affected users/systems

### Structured Format for L2 Support:

```markdown
## 🔍 Automated Sentry Issue Analysis

**Sentry Issue:** [SENTRY-12345](https://sentry.io/issues/12345)
**Analysis Date:** 2025-12-18

---

### 📊 Impact Assessment
| Metric | Value |
|--------|-------|
| Error Type | `NullPointerException` |
| Events (24h) | 1,234 |
| Users Affected | 567 |
| First Seen | 2025-12-17 |
| Severity | **HIGH** |

---

### 🎯 Potential Root Cause(s)
1. **Missing null check in UserService.getUser()** (Confidence: High)
   - File: `src/services/UserService.java:145`
   - The user object is accessed without validation after database query
   
2. **Database connection timeout** (Confidence: Medium)
   - Related to connection pool exhaustion under high load

---

### 💡 Potential Fix(es)
1. **Immediate**: Add null validation before accessing user object
   ```java
   if (user != null) {
       // process user
   }
   ```
2. **Short-term**: Implement connection pool monitoring
3. **Long-term**: Add retry logic for database operations

---

### 📈 Recommended Priority
**HIGH** - Based on user impact (567 users) and error frequency (1,234 events/24h)

---

*This analysis was generated automatically by the Sentry-Jira Agent*
```

---

## Code Structure Proposal

```
src/
├── agents/
│   └── sentry_jira_agent.py      # Main agent workflow
├── mcp_clients/
│   ├── atlassian_client.py       # Atlassian MCP wrapper
│   ├── sentry_client.py          # Sentry MCP wrapper
│   └── github_client.py          # GitHub MCP wrapper
├── models/
│   ├── issue_analyzer.py         # Existing - complexity enum
│   └── jira_update.py            # New - Jira update models
├── tools/
│   ├── analyze_sentry_issue.py   # Tool for analyzing Sentry issues
│   └── update_jira_ticket.py     # Tool for updating Jira
└── main.py                       # Entry point
```

---

## Next Steps (Immediate Actions)

1. **Test Atlassian MCP connectivity**
   - Call `getAccessibleAtlassianResources` to verify access
   - Note down your `cloudId`

2. **Test comment addition**
   - Use `addCommentToJiraIssue` on a test ticket
   - Verify Markdown rendering

3. **Test priority update**
   - Use `editJiraIssue` to update priority field
   - Confirm field name matches your Jira configuration

4. **Design the agent workflow**
   - Review Microsoft Agent Framework documentation
   - Define the workflow steps and tool integrations

---

## Questions to Resolve

~~1. What triggers the workflow? (Jira webhook, manual trigger, scheduled?)~~
   - ✅ **Jira Automation** → HTTP POST webhook to agent endpoint

~~2. Where will the Sentry issue ID come from? (Custom field in Jira? Description parsing?)~~
   - ✅ **Parse from ticket description** - Sentry auto-creates tickets with issue links

~~3. What Jira project(s) will this apply to?~~
   - ✅ **Project: MAFB** at https://remarkgroup.atlassian.net/jira/software/projects/MAFB

~~4. Are there any Jira field customizations we need to account for?~~
   - ✅ **Priority field** - Map complexity to Jira priority
   - ✅ **Comment structure**: Potential root cause, potential fix, impact

5. Do we need to handle rate limiting for any of the MCPs?
   - ⏳ TBD - Will implement retry logic as a precaution

### New Technical Details to Figure Out

~~6. **Sentry URL parsing**: What format does Sentry use when creating Jira tickets?~~
   - ✅ Verified from SI-3568: `https://{org}.sentry.io/issues/{issue_id}/`

7. **Jira Automation setup**: How to configure the HTTP POST action?
   - Need to define the webhook payload structure

~~8. **Agent deployment**: Where will the agent workflow be hosted?~~
   - ✅ **Azure VM**: `mafb@20.255.50.129` (SSH access)

---

## Resources

- [Sentry MCP Documentation](https://mcp.sentry.dev/mcp)
- [Atlassian Jira REST API v3](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-comments/)
- [Microsoft Agent Framework](https://github.com/microsoft/agents)
- [Model Context Protocol](https://modelcontextprotocol.io/)

---

## Appendix: Verified MCP Tools Available

The following Atlassian MCP tools have been verified as available in VS Code:

| Tool Name | Purpose |
|-----------|---------|
| `mcp_atlassian_atl_addCommentToJiraIssue` | Add comment to a Jira issue |
| `mcp_atlassian_atl_editJiraIssue` | Update issue fields (priority, labels, etc.) |
| `mcp_atlassian_atl_getJiraIssue` | Get issue details |
| `mcp_atlassian_atl_transitionJiraIssue` | Transition issue status |
| `mcp_atlassian_atl_getTransitionsForJiraIssue` | Get available transitions |
| `mcp_atlassian_atl_getAccessibleAtlassianResources` | Get cloudId for API calls |
| `mcp_atlassian_atl_getVisibleJiraProjects` | List accessible projects |
| `mcp_atlassian_atl_createJiraIssue` | Create new issue |
| `mcp_atlassian_atl_getJiraIssueRemoteIssueLinks` | Get remote links (Confluence, etc.) |
| `mcp_atlassian_atl_lookupJiraAccountId` | Lookup user account ID |

The following Sentry MCP tools are available:

| Tool Name | Purpose |
|-----------|---------|
| `mcp_sentry-mcp-se_analyze_issue_with_seer` | AI-powered root cause analysis |
| `mcp_sentry-mcp-se_get_event_attachment` | Download event attachments |
| `activate_sentry_issue_and_trace_management` | Access issue/trace tools |
| `activate_sentry_organization_management` | Access org/project tools |
| `activate_sentry_documentation_access` | Access Sentry docs |
