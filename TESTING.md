# Meeting Intelligence System — Testing Guide

Start testing now that you are authenticated with `az login`.

## 1. Start the Server (Local - with uv)

We use `uv` for dependency management to handle Python versions automatically.

```bash
# Terminal 1: Install dependencies and prep environment
cd server
cp .env.template .env
# Ensure .env has: FIREFLIES_API_KEY=your_key
# Ensure .env has: AZURE_SQL_SERVER=genai-sql-server.database.windows.net
# Ensure .env has: AZURE_SQL_DATABASE=meeting-intelligence

# Install dependencies (automatically installs Python 3.12+)
uv pip install -r requirements.txt
```

## 2. Verify Database Connection (Custom Script)

Run a quick script to ensure Entra ID auth works before connecting Claude.

```bash
# Create check_db.py
cat > check_db.py <<EOF
from src.database import get_db
try:
    with get_db() as cursor:
        cursor.execute("SELECT 1")
        print("✅ Database connection successful!")
except Exception as e:
    print(f"❌ Connection failed: {e}")
EOF

# Run check
uv run python -m check_db
```

## 3. Configure Claude Desktop

Add this to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "meeting-intelligence": {
      "command": "uv",
      "args": ["run", "python", "-m", "src.main"],
      "cwd": "/Users/caleblucas/Live Projects/meeting-intelligence/server",
      "env": {
        "AZURE_SQL_SERVER": "genai-sql-server.database.windows.net",
        "AZURE_SQL_DATABASE": "meeting-intelligence",
        "FIREFLIES_API_KEY": "your-actual-key-here"
      }
    }
  }
}
```
*Note: Using `uv run` ensures the correct Python version and dependencies are used automatically.*

## 4. Test Commands in Claude

Once Claude Desktop restarts, try:
1. "Who are you?" (Should mention Meeting Intelligence capabilities)
2. "List my recent meetings" (Tests `list_meetings` + DB auth)
3. "Create a test meeting called 'MCP Kickoff' for today" (Tests writes)
4. "Create an action for Caleb to test deployment by tomorrow" (Tests action creation)

## Production Deployment Config (Reference)

For Claude.ai Connector setup later:
- **URL**: `https://<your-app-url>/sse`
