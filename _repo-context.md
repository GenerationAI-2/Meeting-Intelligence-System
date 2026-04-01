# _repo-context.md — Meeting Intelligence

**Last synced (L2):** 2 Apr 2026
**Last synced (L3):** 2 Apr 2026 (session 2)

---

## Active Build Tasks

Actions from Product Development (queried by Second Brain) that are currently being built. Each entry is a self-contained handoff brief — Claude Code agents have everything they need without accessing any other system.

| Action ID | Summary | Context | Technical Scope | Priority | Status | Date Added |
|-----------|---------|---------|-----------------|----------|--------|------------|
| A119/A120 | Action source meeting name + customer filtering in web UI | Beta users (Sam Fero, 16-person team) report that when viewing actions in the web UI, there is no indication which meeting an action came from. Actions are a flat list with no way to filter by customer or meeting source. This is Sam's strongest UX feedback from Fero Session 2 — without it, the actions list becomes noisy and unusable as volume grows. The `action` table already has a `meeting_id` foreign key, so the data relationship exists — it's just not surfaced in the UI. | **A119 (meeting source):** In the web UI actions list/table, display the source meeting title alongside each action. The `meeting_id` FK exists on the action — join to the meetings table and show `meeting.title`. Add as a visible column or subtitle. **A120 (customer filtering):** Add a filter/dropdown to the actions list that lets users filter actions by meeting or by a grouping (e.g. by meeting tag, or by meeting title prefix). Exact filter mechanism is implementation-flexible — the goal is "show me only actions from Fero meetings" or "show me actions from last Tuesday's standup." Test with the Fero workspace (mi-fero) which has real action data. | NOW — highest UX priority for beta | Pending | 2 Apr 2026 |
| A138 | Action status editable from meetings page | When reviewing a meeting in the web UI, linked actions are displayed — but their status (Open/Complete/Parked) cannot be changed from that view. Users must navigate away to the separate actions tab to update status. Sam flagged this as daily friction: the natural workflow is "review meeting → tick off completed actions" but the UI forces a context switch. | In the web UI meetings detail view (where linked actions are shown), add the ability to update action status inline — either a dropdown, toggle, or click-to-complete control. The `update_action` API endpoint already exists. This is a frontend-only change: wire the existing status update API into the meeting detail view's action list. Ensure optimistic UI update (don't force a page reload). Test with Fero workspace data. | NOW — daily friction for active beta users | Pending | 2 Apr 2026 |

---

## Agent Queue (Level 3)

Tasks handed to Claude Code agents. Second Brain writes tasks here. Claude Code writes completion signals here.

| Action ID | Task Summary | Agent/Repo | Status | Handed Off | Completed | Notes |
|-----------|-------------|------------|--------|------------|-----------|-------|
| A119/A120/A138 | Actions UX — meeting source/filter + inline status | meeting-intelligence | Done | 2 Apr 2026 | 2 Apr 2026 | 258 tests pass. Deployed genai only (rev mi-genai--0000043). Meeting filter covers current page only — acceptable for now. |

---

## Completions (Ready for Caleb)

Build work that's done and ready for Caleb to update in Product Development manually. Caleb clears entries after updating PD.

| Action ID | What Was Done | Commercial Impact | Date Completed |
|-----------|--------------|-------------------|----------------|
| A97 | RBAC org_admin cross-workspace visibility audit — CONFIRMED SAFE. org_admin only bypasses check_permission() for manage_workspace and manage_members. Data ops use membership role. _get_user_memberships() scoped to explicit memberships only. Physical DB isolation (D8) + RBAC workspace boundaries hold. No cross-workspace leakage. Safe to grant client org_admin. | Unblocks org_admin grants for Fero and VK. | 2 Apr 2026 |
| A119/A120/A138 | Actions list now shows source meeting title (clickable), meeting filter dropdown, and inline status update from meeting detail view. Deployed to genai. | Directly addresses Sam Fero's top UX feedback from Session 2. Reduces daily friction for 16-person beta team. | 2 Apr 2026 |

---

## Flags

Anything urgent or cross-cutting. Use `URGENT:` prefix for time-sensitive items.

- A97 RESOLVED 2 Apr — safe to grant client org_admin. No cross-workspace leakage.
- A170 deprioritised — reclassified as data quality issue (free-text owner field). Merged with A132 in SOON backlog. Not Easter-blocking.

---

## Build-Only Tasks (B-series)

Internal technical work with no Product Development parent. Tracked here for visibility.

| Task ID | Summary | Status | Commercial Impact? | Notes |
|---------|---------|--------|--------------------|-------|
| — | — | — | — | — |
