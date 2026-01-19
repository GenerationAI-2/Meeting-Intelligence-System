# Meeting Intelligence System (Live)

A "Hybrid" production application combining a **React Frontend**, a **FastAPI Backend**, and a **Model Context Protocol (MCP) Server** into a single secure deployment on Azure Container Apps.

**Live URL:** 🟢 [https://meeting-intelligence.gentlemoss-914366f8.australiaeast.azurecontainerapps.io](https://meeting-intelligence.gentlemoss-914366f8.australiaeast.azurecontainerapps.io)

---
## 🚀 Features

*   **Hybrid Architecture**: Frontend and Backend served from a single secure container (No CORS issues).
*   **Dual Authentication**:
    *   **Web UI**: Secured by Microsoft Entra ID (MSAL).
    *   **MCP Server**: Secured by Static Bearer Token (Path-Based Propagation).
*   **Claude Integration**: Full support for Claude.ai "Custom Connectors" and Claude Desktop.
*   **Managed Identity**: Secure passwordless connection to Azure SQL Database.

---
## 🔌 How to Connect Claude.ai (Web)

1.  Open [Claude.ai](https://claude.ai) and start a new chat.
2.  Click the **Connection Icon** (🔌 / "Add custom connector").
3.  **Name**: `Meeting Intelligence`
4.  **URL**: Paste exactly this URL (includes your secure token):
    ```
    https://meeting-intelligence.gentlemoss-914366f8.australiaeast.azurecontainerapps.io/sse?token=e5ba95c8bd0fef507c42ddf1a07fee4251c4404c667b6574eecd6219209105e8
    ```
5.  **OAuth**: Leave fields blank.
6.  Click **Connect**. ✅

---
## 🛠️ Deployment

The system is deployed to **Azure Container Apps** using a custom script that handles:
1.  Building the React Frontend (Vite).
2.  Packaging it into the Python Backend container.
3.  Pushing to Azure Container Registry (ACR).
4.  Forcing an update on the Container App (with cache busting).

**To Deploy Updates:**
```bash
./deploy.sh
```
*Note: The script automatically injects a `CACHEBUST` argument to ensure Azure pulls the absolute latest code.*

---
## 💻 Local Development

1.  **Backend**
    ```bash
    cd server
    uv venv
    source .venv/bin/activate
    uv pip install -r requirements.txt
    python -m src.main --http  # Runs on http://localhost:8000
    ```

2.  **Frontend**
    ```bash
    cd web
    npm install
    npm run dev  # Runs on http://localhost:5173
    ```

3.  **Claude Desktop**
    Add to `claude_desktop_config.json`:
    ```json
    "mcpServers": {
      "meeting-intelligence": {
        "command": "python",
        "args": ["-m", "src.main"],
        "cwd": "/absolute/path/to/meeting-intelligence/server",
        "env": {
          "AZURE_SQL_SERVER": "...",
          "MCP_AUTH_TOKEN": "..."
        }
      }
    }
    ```

---
## 📂 Project Structure

```
meeting-intelligence/
├── deploy.sh            # Master deployment script
├── schema.sql           # Database schema
├── server/
│   ├── Dockerfile       # Multi-stage build (Node -> Python)
│   ├── src/
│   │   ├── main.py      # Entry point (HTTP + MCP logic)
│   │   ├── api.py       # FastAPI REST Endpoints
│   │   ├── mcp_server.py # MCP Tool Definitions
│   │   └── database.py  # SQL Connection (Managed Identity)
└── web/                 # React SPA (Vite + Tailwind + MSAL)
```
