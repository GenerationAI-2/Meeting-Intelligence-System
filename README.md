# Meeting Intelligence

Meeting intelligence system with MCP server for Claude and React web interface.

## Project Structure

```
meeting-intelligence/
├── server/          # MCP Server (Python/FastAPI)
├── web/             # React Web UI
└── schema.sql       # Database schema
```

## Quick Start

### 1. Database Setup

Run `schema.sql` on your Azure SQL Database to create the tables.

### 2. MCP Server

```bash
cd server
cp .env.template .env
# Edit .env with your credentials
pip install -r requirements.txt
python -m src.main
```

### 3. Claude Desktop Integration

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "meeting-intelligence": {
      "command": "python",
      "args": ["-m", "src.main"],
      "cwd": "/path/to/meeting-intelligence/server",
      "env": {
        "AZURE_SQL_SERVER": "your-server.database.windows.net",
        "AZURE_SQL_DATABASE": "meeting-intelligence",
        "FIREFLIES_API_KEY": "your-actual-key-here"
      }
    }
  }
}
```

### 4. Web Interface

```bash
cd web
npm install
npm run dev
```

## Available Tools

| Category | Tools |
|----------|-------|
| Meetings | list_meetings, get_meeting, search_meetings, create_meeting, update_meeting |
| Actions | list_actions, get_action, create_action, update_action, complete_action, park_action, delete_action |
| Decisions | list_decisions, create_decision |
| Fireflies | search_fireflies_transcripts, import_fireflies_transcript |

## Deployment

See [DEPLOYMENT.md](./DEPLOYMENT.md) for full details on the Azure Container Apps setup.

**Quick Redeploy:**
```bash
./deploy.sh
```

**Live URL:** `https://meeting-intelligence.gentlemoss-914366f8.australiaeast.azurecontainerapps.io`
