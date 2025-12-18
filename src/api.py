from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import os
import sys
import logging
from dotenv import load_dotenv

# Add the src directory to the Python path
sys.path.insert(0, os.path.dirname(__file__))

from main import create_workflow_instance

load_dotenv()
logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="GitHub Issue Creator API",
    description="AI-powered GitHub issue creation workflow with Sentry webhook integration",
    version="1.0.0"
)

# Sentry Webhook Models
class SentryException(BaseModel):
    type: str
    value: str
    stacktrace: Optional[Dict[str, Any]] = None

class SentryEvent(BaseModel):
    event_id: str
    title: str
    message: Optional[str] = ""
    level: str
    platform: str
    culprit: Optional[str] = None
    exception: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    tags: Optional[List[List[str]]] = None
    web_url: Optional[str] = None

class SentryWebhookData(BaseModel):
    event: SentryEvent
    triggered_rule: Optional[str] = None

class SentryWebhook(BaseModel):
    action: str
    data: SentryWebhookData
    installation: Optional[Dict[str, Any]] = None

# Original Issue Request Model
class IssueRequest(BaseModel):
    description: str
    issue_type: Optional[str] = "bug"
    stack_trace: Optional[str] = None

class IssueResponse(BaseModel):
    status: str
    result: dict
    message: str

@app.post("/api/sentry/webhook")
async def sentry_webhook(webhook: SentryWebhook):
    """Handle Sentry webhook and create GitHub issue"""
    try:
        event = webhook.data.event
        
        # Extract error details
        error_type = "Unknown"
        error_message = event.title or event.message
        stack_trace = ""
        
        # Extract exception details
        if event.exception and "values" in event.exception:
            exceptions = event.exception["values"]
            if exceptions:
                first_exception = exceptions[0]
                error_type = first_exception.get("type", "Unknown")
                error_message = first_exception.get("value", error_message)
                
                # Extract stack trace
                if "stacktrace" in first_exception and "frames" in first_exception["stacktrace"]:
                    frames = first_exception["stacktrace"]["frames"]
                    stack_lines = []
                    for frame in frames:
                        filename = frame.get("filename", "unknown")
                        lineno = frame.get("lineno", "?")
                        function = frame.get("function", "?")
                        stack_lines.append(f"  at {function} ({filename}:{lineno})")
                    stack_trace = "\n".join(stack_lines)
        
        # Build description
        description = f"""
**Sentry Alert**: {webhook.data.triggered_rule or "Error Reported"}

**Error Type**: {error_type}
**Error Message**: {error_message}
**Level**: {event.level}
**Platform**: {event.platform}
**Event ID**: {event.event_id}

**Culprit**: {event.culprit or "N/A"}

**Stack Trace**:
```
{stack_trace or "No stack trace available"}
```

**Sentry Link**: {event.web_url or "N/A"}

**Tags**:
{chr(10).join([f"- {tag[0]}: {tag[1]}" for tag in (event.tags or [])]) or "No tags"}
"""

        logging.info(f"Processing Sentry webhook for event: {event.event_id}")
        
        workflow, _, _, _, _ = create_workflow_instance()
        
        # Run the workflow
        result = await workflow.run(description)
        
        return IssueResponse(
            status="success",
            result=result if isinstance(result, dict) else {"output": str(result)},
            message=f"GitHub issue created for Sentry event {event.event_id}"
        )
        
    except Exception as e:
        logging.error(f"Error processing Sentry webhook: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/issues/create", response_model=IssueResponse)
async def create_issue(request: IssueRequest):
    """Create a GitHub issue using AI workflow (manual API)"""
    try:
        logging.info(f"Received request: {request.description}")
        
        workflow, _, _, _, _ = create_workflow_instance()
        
        input_text = request.description
        if request.stack_trace:
            input_text += f"\n\nStack Trace:\n{request.stack_trace}"
        
        result = await workflow.run(input_text)
        
        return IssueResponse(
            status="success",
            result=result if isinstance(result, dict) else {"output": str(result)},
            message="Issue created successfully"
        )
    except Exception as e:
        logging.error(f"Error creating issue: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "github-issue-creator"}

@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "message": "GitHub Issue Creator API",
        "endpoints": {
            "sentry_webhook": "/api/sentry/webhook",
            "create_issue": "/api/issues/create",
            "health": "/health",
            "docs": "/docs"
        }
    }

@app.post("/api/sentry/webhook/test")
async def test_sentry_webhook(request: Request):
    """Test endpoint to see raw Sentry payload"""
    body = await request.json()
    logging.info(f"Received Sentry test payload: {body}")
    return {"message": "Payload received", "data": body}