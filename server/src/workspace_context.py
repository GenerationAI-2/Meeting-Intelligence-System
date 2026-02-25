"""Meeting Intelligence — Workspace Context

Immutable dataclasses that carry workspace identity through the request lifecycle.
Resolved once per request and never mutated.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class WorkspaceMembership:
    """One user's membership in one workspace."""
    workspace_id: int
    workspace_name: str          # slug: 'board', 'ceo', 'ops'
    workspace_display_name: str  # 'Board', 'CEO Office', 'Operations'
    db_name: str                 # actual Azure SQL database name
    role: str                    # 'viewer', 'member', 'chair'
    is_default: bool             # is this the user's default workspace?
    is_archived: bool            # archived workspaces are read-only


@dataclass(frozen=True)
class WorkspaceContext:
    """Resolved per-request. Immutable for the duration of the request."""
    user_email: str
    is_org_admin: bool
    memberships: list[WorkspaceMembership]    # all workspaces user belongs to
    active: WorkspaceMembership               # the workspace for this request

    @property
    def role(self) -> str:
        """Shortcut: role in the active workspace."""
        return self.active.role

    @property
    def db_name(self) -> str:
        """Shortcut: database name of the active workspace."""
        return self.active.db_name

    def can_write(self) -> bool:
        """Can the user write in the active workspace? Based on role, not org_admin."""
        if self.active.is_archived:
            return False
        return self.active.role in ('member', 'chair')

    def is_chair_or_admin(self) -> bool:
        """Can the user manage/delete in the active workspace? Based on role."""
        return self.active.role == 'chair'


def make_legacy_context(user_email: str) -> WorkspaceContext:
    """Create a WorkspaceContext for single-database (pre-workspace) mode.

    Grants org_admin privileges so all permission checks pass.
    Uses azure_sql_database as the single workspace database.
    """
    from .config import get_settings
    settings = get_settings()
    legacy_membership = WorkspaceMembership(
        workspace_id=0,
        workspace_name="default",
        workspace_display_name="Default",
        db_name=settings.azure_sql_database,
        role="chair",
        is_default=True,
        is_archived=False,
    )
    return WorkspaceContext(
        user_email=user_email,
        is_org_admin=True,
        memberships=[legacy_membership],
        active=legacy_membership,
    )
