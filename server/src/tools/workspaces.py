"""Meeting Intelligence — Workspace Tools

Pure functions on WorkspaceContext — no cursor needed since workspace data
is resolved from the control DB during request setup.
"""

from ..workspace_context import WorkspaceContext


def list_workspaces(ctx: WorkspaceContext) -> dict:
    """Return the user's workspace memberships."""
    workspaces = []
    for m in ctx.memberships:
        workspaces.append({
            "id": m.workspace_id,
            "name": m.workspace_name,
            "display_name": m.workspace_display_name,
            "role": m.role,
            "is_default": m.is_default,
            "is_archived": m.is_archived,
            "is_active": (m.workspace_id == ctx.active.workspace_id),
        })
    return {
        "workspaces": workspaces,
        "count": len(workspaces),
        "active_workspace": ctx.active.workspace_name,
    }


def get_current_workspace(ctx: WorkspaceContext) -> dict:
    """Return info about the currently active workspace."""
    return {
        "workspace_id": ctx.active.workspace_id,
        "workspace_name": ctx.active.workspace_name,
        "workspace_display_name": ctx.active.workspace_display_name,
        "db_name": ctx.active.db_name,
        "role": ctx.role,
        "user_email": ctx.user_email,
        "is_org_admin": ctx.is_org_admin,
        "is_archived": ctx.active.is_archived,
        "can_write": ctx.can_write(),
        "is_chair_or_admin": ctx.is_chair_or_admin(),
    }
