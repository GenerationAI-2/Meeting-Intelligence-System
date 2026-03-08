# DOC1 — Quick Start Guide

**Meeting Intelligence**
**Version:** 1.0 — 28 February 2026
**Prepared by:** Generation AI

---

## Welcome

Meeting Intelligence captures your meetings, actions, and decisions in one place. You can interact with it two ways: through Claude using natural language, or through the web UI.

This guide covers everything you need to get started.

---

## Step 1 — Sign In to the Web UI

Your Generation AI contact will provide your instance URL.

1. Open the URL in your browser
2. Click **Sign In with Microsoft**
3. Authenticate with your organisation's Microsoft account
4. On first login, you may be asked to approve app permissions — click **Accept**

Once signed in, you'll see the main dashboard with your meetings, actions, and decisions.

---

## Step 2 — Generate Your Personal Access Token

You need a token to connect Claude. This is a one-time self-service step:

1. In the web UI, go to **Settings** (user menu in the top right)
2. Under **Personal Access Tokens**, click **Create Token**
3. Copy the token immediately — it will only be shown once

Your connection URL combines your instance URL with your token:

```
https://<your-instance-url>/mcp?token=<your-token>
```

Keep this URL safe — treat it like a password. If you ever need to regenerate it, come back to Settings and create a new token. You can revoke old tokens from the same page.

---

## Step 3 — Connect Claude

1. Go to **Settings** in Claude.ai
2. Under **Integrations**, click **Add custom MCP connector**
3. Paste your connection URL from Step 2
4. Claude now has access to your Meeting Intelligence tools

That's it. You can start talking to Claude naturally about your meetings, actions, and decisions.

---

## What You Can Do

### Via AI Assistant (Natural Language)

Once connected, just talk to Claude naturally. It has access to 23 tools across meetings, actions, decisions, and workspaces. Examples:

**Meetings**
- "What meetings did I have this week?"
- "Search my meetings for anything about the budget"
- "Create a meeting record for today's standup"

**Actions**
- "What are my open action items?"
- "Show me actions due this week"
- "Mark the API documentation action as complete"
- "Create an action for Sarah to review the contract by Friday"

**Decisions**
- "What decisions have we made recently?"
- "Log a decision that we're going with Option B for the rebrand"

**Workspaces**
- "Which workspace am I in?"
- "Switch to the marketing workspace"

### Via Web UI

The web UI gives you a visual interface for the same data:

| Page | What it does |
|------|-------------|
| **Meetings** | View, search, and filter meetings by date, attendee, or tag |
| **Actions** | Track action items with status (Open / Complete / Parked), filter by owner |
| **Decisions** | Browse decisions linked to meetings |
| **Settings** | Manage your personal access tokens |
| **Workspace Admin** | Manage workspaces and members (admin only) |

---

## Workspaces

Your data is organised into workspaces. Think of them as separate projects or teams — each workspace has its own meetings, actions, and decisions, completely isolated from other workspaces.

You'll start with a default workspace. If you need additional workspaces (e.g., per project or per team), ask your organisation admin or Generation AI contact.

**Switching workspaces:**
- **Web UI:** Use the workspace dropdown in the top navigation bar
- **Claude:** Say "switch to the [name] workspace"

---

## Roles and Permissions

Your access level depends on your role in each workspace:

| Permission | Viewer | Member | Chair | Org Admin |
|-----------|--------|--------|-------|-----------|
| View meetings, actions, decisions | Yes | Yes | Yes | Yes |
| Create new records | | Yes | Yes | Yes |
| Edit your own records | | Yes | Yes | Yes |
| Edit anyone's records | | | Yes | Yes |
| Delete records | | | Yes | Yes |
| Manage workspace members | | | Yes | Yes |
| Create/archive workspaces | | | | Yes |

---

## Managing Your Team (Chairs and Admins)

If you're a workspace chair or organisation admin, you can manage members:

1. Go to **Workspace Admin** in the sidebar
2. Select your workspace
3. Click **Add Member**
4. Enter their email address and assign a role

Members added here will be able to sign in with their Microsoft account and access the workspace immediately.

---

## Tips

- **Actions without meetings:** You can create standalone action items that aren't linked to any meeting. Just ask Claude or use the Actions page.
- **Tags:** Tag your meetings for easy filtering later (e.g., "standup", "client", "planning").
- **Token security:** Treat your connection URL like a password. If you think it's been compromised, revoke the token in Settings and create a new one.

---

## Getting Help

Contact your Generation AI representative:

- **Email:** caleb.lucas@generationai.co.nz
- **Support hours:** Monday to Friday, 8am to 6pm NZST

---

*For technical details, see the full documentation suite maintained by Generation AI.*
