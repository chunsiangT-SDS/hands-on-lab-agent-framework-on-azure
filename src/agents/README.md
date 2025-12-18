# Sentry-Jira Agent - User Guide

## Overview

This agent automatically analyzes Sentry production errors and enriches Jira tickets with AI-powered insights. It's designed for L2 support teams who need quick, actionable information.

```
Sentry Error → AI Analysis → Jira Comment + Priority Update
```

## Quick Start

### 1. Start the Server

```bash
cd src
uv run uvicorn agents.server:app --host 0.0.0.0 --port 8000
```

### 2. Test with Postman

Import the Postman collection: `agents/postman_collection.json`

Or use curl:

```bash
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "jira_issue_key": "MAFB-11",
    "sentry_org": "scor-digital-solutions",
    "sentry_issue_id": "BRMS-LOCAL-1Q",
    "sentry_data_raw": "# Issue BRMS-LOCAL-1Q\n\n**Description**: NoMethodError...\n**Occurrences**: 100\n**Users Impacted**: 50\n..."
  }'
```

### 3. Check the Result

The agent will:
- ✅ Post a concise comment to the Jira ticket
- ✅ Update the Jira priority based on severity

---

## API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/` | GET | API info |
| `/health` | GET | Health check |
| `/analyze` | POST | **Main endpoint** - trigger analysis |
| `/webhook/sentry` | POST | Receive Sentry alerts |
| `/webhook/jira` | POST | Receive Jira webhooks |
| `/docs` | GET | Swagger UI |

---

## Analyze Request Format

### Required Fields

```json
{
  "jira_issue_key": "MAFB-11",
  "sentry_data_raw": "# Issue KEY\n\n**Description**: Error message..."
}
```

### Optional Fields

```json
{
  "sentry_org": "scor-digital-solutions",
  "sentry_issue_id": "BRMS-LOCAL-1Q"
}
```

### Full Example

```json
{
  "jira_issue_key": "MAFB-11",
  "sentry_org": "scor-digital-solutions",
  "sentry_issue_id": "BRMS-LOCAL-1Q",
  "sentry_data_raw": "# Issue BRMS-LOCAL-1Q in **scor-digital-solutions**\n\n**Description**: NoMethodError: undefined method `[]' for nil:NilClass\n**Culprit**: Api::V2::Sessions::PdfsController#show\n**Occurrences**: 1\n**Users Impacted**: 0\n**Status**: unresolved\n**Platform**: ruby\n**URL**: https://scor-digital-solutions.sentry.io/issues/BRMS-LOCAL-1Q\n\n### Error\n\n```\nNoMethodError: undefined method `[]' for nil:NilClass\n      rules = subset[\"rules\"] || []\n```\n\n**Full Stacktrace:**\n```\n    from app/components/questions_component.rb:22\n    from app/controllers/api/v2/sessions/pdfs_controller.rb:17\n```"
}
```

---

## Response Format

```json
{
  "status": "success",
  "issue_key": "MAFB-11",
  "triage": {
    "priority": "Low",
    "is_urgent": false,
    "reason": "Single occurrence, no users affected"
  },
  "analysis": {
    "root_cause": "The code attempts to call [] on a nil object",
    "file": "app/components/questions_component.rb:22",
    "fix": "Add a nil check before accessing the object",
    "confidence": "High"
  },
  "jira": {
    "comment": "success",
    "priority": "success"
  },
  "timestamp": "2025-12-18T09:05:20.390839"
}
```

---

## Jira Comment Format

The agent posts concise, L2-friendly comments:

```
🤖 Sentry Auto-Analysis

🟢 Priority: Low | Single occurrence, no users affected

📍 Root Cause: The code attempts to call [] on a nil object
📁 File: app/components/questions_component.rb:22
🔧 Fix: Add a nil check before accessing the object
📊 Confidence: High

━━━━━━━━━━━━━━━━━━━━
📈 Stats: 1 events | 0 users
🔗 Sentry: https://org.sentry.io/issues/...
⏰ Analyzed: 2025-12-18
```

---

## Environment Variables

Create a `.env` file in the `src` directory:

```bash
# Required - Azure AI
AZURE_AI_PROJECT_ENDPOINT=https://your-project.services.ai.azure.com
AZURE_AI_MODEL_DEPLOYMENT_NAME=chatmodel

# Required - Atlassian (Jira)
ATLASSIAN_EMAIL=your-email@company.com
ATLASSIAN_API_TOKEN=your-api-token

# Optional - GitHub (for code context)
GITHUB_REPO_OWNER=your-org
GITHUB_REPO_NAME=your-repo
GITHUB_TOKEN=ghp_xxxx
```

---

## Deployment to Azure VM

### SSH to the VM

```bash
ssh mafb@20.255.50.129
```

### Deploy the Code

```bash
# On the VM
cd ~/sentry-jira-agent
git pull origin main

# Install dependencies
uv sync

# Set environment variables
cp .env.example .env
nano .env  # Edit with your credentials

# Start the server
uv run uvicorn agents.server:app --host 0.0.0.0 --port 8000
```

### Run as a Background Service (Optional)

```bash
# Using nohup
nohup uv run uvicorn agents.server:app --host 0.0.0.0 --port 8000 > agent.log 2>&1 &

# Or using screen
screen -S sentry-agent
uv run uvicorn agents.server:app --host 0.0.0.0 --port 8000
# Ctrl+A, D to detach
```

### Test the Deployed Endpoint

```bash
curl http://20.255.50.129:8000/health
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     HTTP Server (FastAPI)                   │
│                     POST /analyze                           │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  1. Parse Sentry Data                                       │
│     Extract: title, stack trace, occurrences, users         │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  2. GitHub Context (Optional)                               │
│     Fetch source code for files in stack trace              │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  3. Triage Agent (Azure AI)                                 │
│     Quick severity → Priority + Urgency (5 seconds)         │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  4. Analysis Agent (Azure AI)                               │
│     Root cause → File + Fix + Confidence (10 seconds)       │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  5. Jira Update (REST API)                                  │
│     • Add concise comment                                   │
│     • Update priority                                       │
└─────────────────────────────────────────────────────────────┘
```

---

## Troubleshooting

### "No Sentry URL found"
- Ensure `sentry_org` and `sentry_issue_id` are provided, OR
- The `sentry_data_raw` contains a valid Sentry URL

### "Azure AI authentication failed"
- Run `az login` to refresh Azure CLI credentials
- Ensure `AZURE_AI_PROJECT_ENDPOINT` is correct

### "Jira comment failed"
- Verify `ATLASSIAN_EMAIL` and `ATLASSIAN_API_TOKEN`
- Check the Jira issue key exists (e.g., MAFB-11)

### Server not starting
- Check port 8000 is not in use: `lsof -i :8000`
- Kill existing process: `pkill -f uvicorn`

---

## Files

```
src/agents/
├── __init__.py                 # Module exports
├── server.py                   # FastAPI HTTP server
├── sentry_jira_multi_agent.py  # Multi-agent workflow
├── postman_collection.json     # Postman collection
└── README.md                   # This file
```

---

## Support

For issues or questions, contact the development team or check the full planning document: `sentry-jira-agent-plan.md`
