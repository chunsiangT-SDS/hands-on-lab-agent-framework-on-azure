"""
Sentry-Jira Agent HTTP Server
=============================

FastAPI server exposing the multi-agent workflow via HTTP webhooks.

Endpoints:
- POST /webhook/sentry       - Triggered by Sentry alerts
- POST /webhook/jira         - Triggered by Jira issue events
- POST /analyze              - Manual trigger via Postman
- GET  /health               - Health check

Usage:
    uv run uvicorn agents.server:app --host 0.0.0.0 --port 8000 --reload
"""

import os
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Import the multi-agent workflow
from agents.sentry_jira_multi_agent import (
    process_sentry_issue,
    parse_sentry_mcp_response,
    SentryIssueData,
)

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class SentryWebhookEvent(BaseModel):
    """Sentry webhook event payload"""
    event_id: str
    project: str
    project_slug: Optional[str] = None
    title: str
    message: Optional[str] = None
    level: str = "error"
    platform: str = "unknown"
    culprit: Optional[str] = None
    url: Optional[str] = None
    web_url: Optional[str] = None


class SentryWebhookData(BaseModel):
    """Sentry webhook data container"""
    event: Optional[SentryWebhookEvent] = None
    issue: Optional[Dict[str, Any]] = None
    triggered_rule: Optional[str] = None


class SentryWebhookPayload(BaseModel):
    """Full Sentry webhook payload"""
    action: str = "triggered"
    data: SentryWebhookData
    actor: Optional[Dict[str, Any]] = None
    installation: Optional[Dict[str, Any]] = None


class JiraWebhookIssue(BaseModel):
    """Jira issue in webhook"""
    id: str
    key: str
    self: Optional[str] = None
    fields: Optional[Dict[str, Any]] = None


class JiraWebhookPayload(BaseModel):
    """Jira webhook payload"""
    webhookEvent: str
    issue: JiraWebhookIssue
    user: Optional[Dict[str, Any]] = None
    changelog: Optional[Dict[str, Any]] = None


class ManualAnalyzeRequest(BaseModel):
    """Manual analysis request for Postman testing"""
    jira_issue_key: str = Field(..., example="MAFB-11")
    sentry_issue_id: Optional[str] = Field(None, example="BRMS-LOCAL-1Q")
    sentry_org: Optional[str] = Field(None, example="scor-digital-solutions")
    sentry_data_raw: Optional[str] = Field(
        None, 
        description="Raw Sentry MCP response text (for testing without live Sentry)"
    )


class AnalysisResponse(BaseModel):
    """Response from analysis endpoint"""
    status: str
    issue_key: str
    triage: Optional[Dict[str, Any]] = None
    analysis: Optional[Dict[str, Any]] = None
    jira: Optional[Dict[str, Any]] = None
    message: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


# =============================================================================
# APP SETUP
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    logger.info("🚀 Sentry-Jira Agent Server starting...")
    logger.info(f"   Jira Cloud: remarkgroup.atlassian.net")
    logger.info(f"   Azure AI: {os.environ.get('AZURE_AI_PROJECT_ENDPOINT', 'Not configured')[:50]}...")
    yield
    logger.info("👋 Sentry-Jira Agent Server shutting down...")


app = FastAPI(
    title="Sentry-Jira Agent API",
    description="AI-powered Sentry issue analysis and Jira enrichment",
    version="1.0.0",
    lifespan=lifespan,
)


# =============================================================================
# ENDPOINTS
# =============================================================================

@app.get("/")
async def root():
    """API information"""
    return {
        "service": "Sentry-Jira Agent",
        "version": "1.0.0",
        "endpoints": {
            "POST /webhook/sentry": "Receive Sentry alert webhooks",
            "POST /webhook/jira": "Receive Jira issue webhooks",
            "POST /analyze": "Manual analysis trigger (Postman)",
            "GET /health": "Health check",
        },
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "sentry-jira-agent",
        "timestamp": datetime.utcnow().isoformat(),
        "config": {
            "azure_ai": bool(os.environ.get("AZURE_AI_PROJECT_ENDPOINT")),
            "atlassian": bool(os.environ.get("ATLASSIAN_API_TOKEN")),
            "github": bool(os.environ.get("GITHUB_REPO_OWNER")),
        }
    }


@app.post("/webhook/sentry", response_model=AnalysisResponse)
async def sentry_webhook(payload: SentryWebhookPayload, background_tasks: BackgroundTasks):
    """
    Handle Sentry alert webhooks.
    
    Configure in Sentry: Settings → Integrations → Webhooks
    URL: http://your-server:8000/webhook/sentry
    
    Sentry sends alerts when issues occur. This endpoint:
    1. Extracts issue details from the webhook
    2. Looks for linked Jira ticket (if any)
    3. Runs AI analysis
    4. Updates Jira with findings
    """
    logger.info(f"📥 Sentry webhook received: {payload.action}")
    
    try:
        # Extract issue info from Sentry payload
        issue_data = payload.data.issue or {}
        event_data = payload.data.event
        
        sentry_issue_id = issue_data.get("id") or (event_data.event_id if event_data else None)
        sentry_url = issue_data.get("web_url") or (event_data.web_url if event_data else None)
        
        if not sentry_issue_id:
            return AnalysisResponse(
                status="skipped",
                issue_key="N/A",
                message="No issue ID in webhook payload"
            )
        
        logger.info(f"   Sentry Issue: {sentry_issue_id}")
        logger.info(f"   URL: {sentry_url}")
        
        # For Sentry webhooks, we need to find the linked Jira ticket
        # This would typically come from Sentry's Jira integration
        # For now, we'll return the Sentry data for manual processing
        
        # Build a SentryIssueData from the webhook
        title = issue_data.get("title") or (event_data.title if event_data else "Unknown Error")
        platform = issue_data.get("platform") or (event_data.platform if event_data else "unknown")
        
        return AnalysisResponse(
            status="received",
            issue_key=str(sentry_issue_id),
            message=f"Sentry alert received: {title}. Use /analyze endpoint with Jira issue key to process.",
            triage={"pending": True},
            analysis={"pending": True},
        )
        
    except Exception as e:
        logger.error(f"❌ Sentry webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/webhook/jira", response_model=AnalysisResponse)
async def jira_webhook(payload: JiraWebhookPayload):
    """
    Handle Jira issue webhooks.
    
    Configure in Jira: Settings → System → Webhooks
    URL: http://your-server:8000/webhook/jira
    Events: issue_created, issue_updated
    
    When a Jira ticket is created (e.g., by Sentry integration):
    1. Extract Sentry URL from description
    2. Fetch Sentry issue details
    3. Run AI analysis
    4. Update Jira with findings
    """
    logger.info(f"📥 Jira webhook received: {payload.webhookEvent}")
    logger.info(f"   Issue: {payload.issue.key}")
    
    try:
        issue_key = payload.issue.key
        fields = payload.issue.fields or {}
        
        # Get description to find Sentry URL
        description = fields.get("description", "")
        
        # For ADF format, extract text content
        if isinstance(description, dict):
            # ADF format - extract text
            description = extract_text_from_adf(description)
        
        logger.info(f"   Description preview: {str(description)[:100]}...")
        
        # Build payload for processing
        process_payload = {
            "issue": {
                "key": issue_key,
                "fields": {
                    "description": description
                }
            }
        }
        
        # For now, we need the Sentry MCP response
        # In production, this would fetch from Sentry API
        # Return pending status for manual completion
        
        return AnalysisResponse(
            status="received",
            issue_key=issue_key,
            message=f"Jira issue {issue_key} received. Use /analyze endpoint with sentry_data_raw to complete analysis.",
        )
        
    except Exception as e:
        logger.error(f"❌ Jira webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/analyze", response_model=AnalysisResponse)
async def analyze(request: ManualAnalyzeRequest):
    """
    Manual analysis trigger - use from Postman or for testing.
    
    Example request body:
    ```json
    {
        "jira_issue_key": "MAFB-11",
        "sentry_data_raw": "# Issue BRMS-LOCAL-1Q in **scor-digital-solutions**\\n\\n**Description**: NoMethodError..."
    }
    ```
    
    This is the main endpoint for triggering the full workflow:
    1. Parse Sentry data
    2. Run Triage Agent (quick severity assessment)
    3. Run Analysis Agent (root cause identification)
    4. Post concise comment to Jira
    5. Update Jira priority
    """
    logger.info(f"🔍 Manual analysis request for {request.jira_issue_key}")
    
    try:
        if not request.sentry_data_raw:
            return AnalysisResponse(
                status="error",
                issue_key=request.jira_issue_key,
                message="sentry_data_raw is required. Provide the Sentry MCP response text."
            )
        
        # Build a valid Sentry URL for extraction
        sentry_org = request.sentry_org or "org"
        sentry_id = request.sentry_issue_id or "unknown"
        sentry_url = f"https://{sentry_org}.sentry.io/issues/{sentry_id}/"
        
        # Build payload with properly formatted description
        payload = {
            "issue": {
                "key": request.jira_issue_key,
                "fields": {
                    "description": f"Sentry Issue: {sentry_url}"
                }
            }
        }
        
        # Run the multi-agent workflow
        result = await process_sentry_issue(payload, request.sentry_data_raw)
        
        return AnalysisResponse(
            status=result.get("status", "unknown"),
            issue_key=result.get("issue_key", request.jira_issue_key),
            triage=result.get("triage"),
            analysis=result.get("analysis"),
            jira=result.get("jira"),
            message="Analysis complete" if result.get("status") == "success" else result.get("message"),
        )
        
    except Exception as e:
        logger.error(f"❌ Analysis error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/analyze/raw")
async def analyze_raw(request: Request):
    """
    Raw analysis endpoint - accepts any JSON for debugging.
    Useful when testing webhook payloads.
    """
    body = await request.json()
    logger.info(f"📥 Raw request received: {json.dumps(body, indent=2)[:500]}...")
    return {
        "status": "received",
        "payload_keys": list(body.keys()) if isinstance(body, dict) else "not a dict",
        "message": "Use /analyze endpoint for actual processing"
    }


# =============================================================================
# HELPERS
# =============================================================================

def extract_text_from_adf(adf: Dict[str, Any]) -> str:
    """Extract plain text from Atlassian Document Format"""
    if not adf or not isinstance(adf, dict):
        return ""
    
    texts = []
    
    def traverse(node):
        if isinstance(node, dict):
            if node.get("type") == "text":
                texts.append(node.get("text", ""))
            for child in node.get("content", []):
                traverse(child)
        elif isinstance(node, list):
            for item in node:
                traverse(item)
    
    traverse(adf)
    return " ".join(texts)


# =============================================================================
# SAMPLE PAYLOADS (for reference)
# =============================================================================

SAMPLE_SENTRY_WEBHOOK = """
{
    "action": "triggered",
    "data": {
        "event": {
            "event_id": "abc123",
            "project": "my-project",
            "title": "NoMethodError: undefined method",
            "level": "error",
            "platform": "ruby",
            "culprit": "MyController#show",
            "web_url": "https://org.sentry.io/issues/123/"
        },
        "triggered_rule": "High Priority Alert"
    }
}
"""

SAMPLE_JIRA_WEBHOOK = """
{
    "webhookEvent": "jira:issue_created",
    "issue": {
        "id": "92924",
        "key": "MAFB-11",
        "fields": {
            "summary": "NoMethodError in production",
            "description": "Sentry Issue: https://org.sentry.io/issues/123/"
        }
    }
}
"""

SAMPLE_ANALYZE_REQUEST = """
{
    "jira_issue_key": "MAFB-11",
    "sentry_org": "scor-digital-solutions",
    "sentry_issue_id": "BRMS-LOCAL-1Q",
    "sentry_data_raw": "# Issue BRMS-LOCAL-1Q in **scor-digital-solutions**\\n\\n**Description**: NoMethodError: undefined method..."
}
"""


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
