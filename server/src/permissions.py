"""Meeting Intelligence — Permission Enforcer

Stateless permission checks based on WorkspaceContext.
Raises HTTPException 403 if denied. Returns None if allowed.
"""

from fastapi import HTTPException
from .workspace_context import WorkspaceContext


def check_permission(ctx: WorkspaceContext, operation: str, entity: dict = None) -> None:
    """
    Check if current user can perform the operation in their active workspace.

    Operations: 'read', 'create', 'update', 'delete', 'manage_members', 'manage_workspace'
    Entity: dict with at least 'created_by' key for ownership checks. None for list/create ops.

    Raises HTTPException 403 if denied. Returns None if allowed.
    """

    # Org admin bypasses RBAC checks within a workspace they have access to.
    # Note: org admin does NOT get implicit data access to all workspaces.
    # They must be explicitly added as a member to access a workspace's data.
    # org_admin only governs admin API operations (workspace CRUD, member management).
    if ctx.is_org_admin:
        return

    role = ctx.role  # viewer | member | chair

    # Archived workspace: read-only for everyone
    if ctx.active.is_archived and operation != 'read':
        raise HTTPException(403, f"Workspace '{ctx.active.workspace_display_name}' is archived (read-only)")

    # Read: all roles
    if operation == 'read':
        return

    # Create: member + chair
    if operation == 'create':
        if role == 'viewer':
            raise HTTPException(403, "Viewers cannot create items")
        return

    # Update: member (own only) + chair (any)
    if operation == 'update':
        if role == 'viewer':
            raise HTTPException(403, "Viewers cannot edit items")
        if role == 'member' and entity and entity.get('created_by') != ctx.user_email:
            raise HTTPException(403, "Members can only edit their own items")
        return

    # Delete: chair only
    if operation == 'delete':
        if role in ('viewer', 'member'):
            raise HTTPException(403, "Only chairs can delete items")
        return

    # Manage members: chair only
    if operation == 'manage_members':
        if role != 'chair':
            raise HTTPException(403, "Only chairs can manage workspace members")
        return

    # Manage workspace (create/archive): org admin only (already handled above)
    if operation == 'manage_workspace':
        raise HTTPException(403, "Only org admins can manage workspaces")
