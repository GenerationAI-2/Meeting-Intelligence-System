# Meeting Intelligence System - Deployment Guide

## Live Environment
*   **App URL (Web UI & REST API):** `https://meeting-intelligence.gentlemoss-914366f8.australiaeast.azurecontainerapps.io`
*   **MCP SSE Endpoint (Claude):** `https://meeting-intelligence.gentlemoss-914366f8.australiaeast.azurecontainerapps.io/sse`
*   **Resource Group:** `meeting-intelligence-v2-rg`

## Infrastructure
*   **Azure SQL Database:** `meeting-intelligence` on server `genai-sql-server.database.windows.net`
*   **Container App:** `meeting-intelligence` (Python 3.12, 1 Replica)
*   **Authentication:** 
    *   **SQL:** System-Assigned Managed Identity
    *   **API:** Authless (Open for Claude.ai testing)

## Redeployment
To deploy updates to the `server/` or infrastructure code:

```bash
./deploy.sh
```

This script will:
1.  Build the Docker image.
2.  Push to Azure Container Registry.
3.  Update the Container App.

## Environment Variables
The deployed container uses these environment variables:

*   `AZURE_SQL_SERVER`: `genai-sql-server.database.windows.net`
*   `AZURE_SQL_DATABASE`: `meeting-intelligence`
*   `FIREFLIES_API_KEY`: (Injected via Azure Secrets)
*   `MCP_MODE`: `http` (Configures `main.py` to run in HTTP/SSE mode)
