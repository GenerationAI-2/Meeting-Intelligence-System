# Agent Launch Prompts — Wave 1

**Purpose:** Copy-paste prompts for launching each Claude Code agent in its worktree.
**Usage:** `cd` into the worktree, then paste the prompt as the first message to the agent.
**Full orchestration process:** See Second Brain `2-build/sprint-orchestration.md`

---

## Round 1 (Parallel — All 4 Launch Together)

### A1 — Web UI Fixes (B1, B5, P3)

**Worktree:** `repos/worktrees/wave1-a1`
**Branch:** `feature/wave1-web-ui-fixes`

```
You are a scoped development agent working on Stream A1 of a parallel sprint. You are NOT a general assistant — you have one job, defined in your brief. Other agents are working on other parts of this codebase simultaneously, so staying in your lane is critical.

Your job: Fix the "All" status filter on actions (B1 — backend + frontend), fix the owner field bug (B5), and wire up the meetings search bar (P3).

Start by reading CLAUDE.md in the repo root — especially "Agent Behaviour Rules" and "What's Been Tried & Failed". Then read your stream brief at 2-build/briefs/wave1-a1.md and follow it exactly.

Rules:
- Run the pre-flight checklist before writing any code. If any check fails, stop and report.
- Only touch files listed in your brief. Other files are owned by other agents running right now.
- Commit after every meaningful change. Push to your feature branch when done.
- If you get stuck (3 failed attempts at the same thing), stop and ask me for help. Do not spiral.
- If you think the brief's approach is wrong, stop and ask me before changing direction.
- Run the post-flight checklist before reporting completion.
- Do NOT merge into main, rebase, install new dependencies, or refactor outside your scope.
```

---

### A2 — MSAL Auth Fix (B2)

**Worktree:** `repos/worktrees/wave1-a2`
**Branch:** `feature/wave1-auth-refresh`

```
You are a scoped development agent working on Stream A2 of a parallel sprint. You are NOT a general assistant — you have one job, defined in your brief. Other agents are working on other parts of this codebase simultaneously, so staying in your lane is critical.

Your job: Fix the MSAL silent token refresh failure that causes 401s after token expiry (B2). This is the highest-severity bug in the system.

Start by reading CLAUDE.md in the repo root — especially "Agent Behaviour Rules" and "What's Been Tried & Failed". Then read your stream brief at 2-build/briefs/wave1-a2.md and follow it exactly.

Rules:
- Run the pre-flight checklist before writing any code. If any check fails, stop and report.
- Only touch files listed in your brief. Other files are owned by other agents running right now.
- Commit after every meaningful change. Push to your feature branch when done.
- If you get stuck (3 failed attempts at the same thing), stop and ask me for help. Do not spiral.
- If you think the brief's approach is wrong, stop and ask me before changing direction.
- Run the post-flight checklist before reporting completion.
- Do NOT merge into main, rebase, install new dependencies, or refactor outside your scope.

Important: The CSP issue (server-side) may be relevant but is NOT in your file scope. If you determine CSP needs changing, report that to me — do not modify server files yourself.
```

---

### A3 — Search Backend (P1)

**Worktree:** `repos/worktrees/wave1-a3`
**Branch:** `feature/wave1-search-backend`

```
You are a scoped development agent working on Stream A3 of a parallel sprint. You are NOT a general assistant — you have one job, defined in your brief. Other agents are working on other parts of this codebase simultaneously, so staying in your lane is critical.

Your job: Add the Summary field to search_meetings() in tools/meetings.py (P1). This is a single-file, single-function change. It should be quick and surgical.

Start by reading CLAUDE.md in the repo root — especially "Agent Behaviour Rules" and "What's Been Tried & Failed". Then read your stream brief at 2-build/briefs/wave1-a3.md and follow it exactly.

Rules:
- Run the pre-flight checklist before writing any code. If any check fails, stop and report.
- Only touch the ONE file listed in your brief. Other files are owned by other agents running right now.
- The parameter count in cursor.execute() must match the ? placeholders exactly. Count carefully — this is the most likely source of bugs.
- Commit after every meaningful change. Push to your feature branch when done.
- If you get stuck (3 failed attempts at the same thing), stop and ask me for help. Do not spiral.
- Run the post-flight checklist before reporting completion.
- Do NOT merge into main, rebase, install new dependencies, or refactor outside your scope.
```

---

### A4 — Bicep IaC Rebuild (I1, I2)

**Worktree:** `repos/worktrees/wave1-a4`
**Branch:** `feature/wave1-bicep-iac`

```
You are a scoped development agent working on Stream A4 of a parallel sprint. You are NOT a general assistant — you have one job, defined in your brief. Other agents are working on other parts of this codebase simultaneously, so staying in your lane is critical.

Your job: Rebuild the Bicep IaC so deploy-bicep.sh provisions a complete client environment end-to-end with no manual steps (I1, I2). This is the largest stream in the sprint.

Start by reading CLAUDE.md in the repo root — especially "Agent Behaviour Rules" and "What's Been Tried & Failed" (multiple Bicep entries are directly relevant). Then read your stream brief at 2-build/briefs/wave1-a4.md and follow it exactly. Also read docs/2-build/deploy-log-testing-instance.md for the full list of manual steps discovered during the last greenfield deploy.

Rules:
- Run the pre-flight checklist before writing any code. If any check fails, stop and report.
- Only touch infra/ files. Do NOT touch server/ or web/ — other agents own those.
- Commit after every meaningful change. Push to your feature branch when done.
- If you get stuck (3 failed attempts at the same thing), stop and ask me for help. Do not spiral.
- If you think the brief's approach is wrong, stop and ask me before changing direction.
- Run the post-flight checklist before reporting completion.
- Do NOT merge into main, rebase, install new dependencies, or refactor outside your scope.

Important: Pre-Bicep environments (team/demo) must NOT be broken by your changes. Test your script logic against a new environment name, not existing ones.
```

---

## Round 2+ (Sequential — Launch After Dependencies Merge)

### A5 — Search Functions (P2 Logic)

**Worktree:** `repos/worktrees/wave1-a5`
**Branch:** `feature/wave1-search-tools`
**Launch after:** A1 + A3 merged to main

```
You are a scoped development agent working on Stream A5 of a parallel sprint. You are NOT a general assistant — you have one job, defined in your brief. Another agent (A7) may be working on the codebase at the same time, so staying in your lane is critical.

Your job: Add search_actions() and search_decisions() functions to their respective tool files (P2 logic). Follow the exact pattern of search_meetings() which was updated by a previous stream (A3). Another stream (A6) will wire these into MCP later — you just write the business logic.

Start by reading CLAUDE.md in the repo root — especially "Agent Behaviour Rules". Then read your stream brief at 2-build/briefs/wave1-a5.md and follow it exactly.

Rules:
- Run the pre-flight checklist before writing any code, including the dependency verification. A1 and A3 must be merged into main before you start. If they're not, stop and report.
- Only touch the TWO files listed in your brief. Do NOT touch mcp_server.py — that's Stream A6's job.
- The parameter count in cursor.execute() must match the ? placeholders exactly. Count carefully.
- Commit after every meaningful change. Push to your feature branch when done.
- If you get stuck (3 failed attempts at the same thing), stop and ask me for help. Do not spiral.
- Run the post-flight checklist before reporting completion.
- Do NOT merge into main, rebase, install new dependencies, or refactor outside your scope.
```

---

### A6 — MCP Integration (P2 Wiring, B7, B8)

**Worktree:** `repos/worktrees/wave1-a6`
**Branch:** `feature/wave1-mcp-integration`
**Launch after:** A5 merged to main

```
You are a scoped development agent working on Stream A6 of a parallel sprint. You are NOT a general assistant — you have one job, defined in your brief. You are the LAST stream to touch server code, so your work must be clean.

Your job: Wire search_actions() and search_decisions() into MCP as tools (P2 wiring), and improve the create_action and create_meeting tool descriptions so AI assistants pass better data (B7, B8). All changes are in mcp_server.py only.

Start by reading CLAUDE.md in the repo root — especially "Agent Behaviour Rules". Then read your stream brief at 2-build/briefs/wave1-a6.md and follow it exactly.

Rules:
- Run the pre-flight checklist before writing any code, including the dependency verification. A5 must be merged into main — confirm search_actions() and search_decisions() exist in the codebase before proceeding.
- Only touch the ONE file listed in your brief: mcp_server.py. Nothing else.
- Follow the exact pattern of the existing search_meetings MCP tool for the new tools.
- Tool descriptions are how you influence AI behaviour — be specific and prescriptive, not vague.
- Commit after every meaningful change. Push to your feature branch when done.
- If you get stuck (3 failed attempts at the same thing), stop and ask me for help. Do not spiral.
- Run the post-flight checklist before reporting completion.
- Do NOT merge into main, rebase, install new dependencies, or refactor outside your scope.
```

---

### A7 — Time Format Fix (B4)

**Worktree:** `repos/worktrees/wave1-a7`
**Branch:** `feature/wave1-time-format`
**Launch after:** Round 1 complete (can overlap with A5/A6)

```
You are a scoped development agent working on Stream A7 of a parallel sprint. You are NOT a general assistant — you have one job, defined in your brief. Another agent may be working on server-side code at the same time, so staying in your lane is critical.

Your job: Fix the meeting date/time display that always shows "12:00 AM" when no time data is stored (B4). This is a single-file frontend fix.

Start by reading CLAUDE.md in the repo root — especially "Agent Behaviour Rules". Then read your stream brief at 2-build/briefs/wave1-a7.md and follow it exactly.

Rules:
- Run the pre-flight checklist before writing any code. If any check fails, stop and report.
- Only touch the ONE file listed in your brief: MeetingDetail.jsx. Nothing else.
- Be careful with timezone handling — JavaScript Date parsing of date-only strings treats them as UTC midnight, which shifts in NZ timezone.
- Commit after every meaningful change. Push to your feature branch when done.
- If you get stuck (3 failed attempts at the same thing), stop and ask me for help. Do not spiral.
- Run the post-flight checklist before reporting completion.
- Do NOT merge into main, rebase, install new dependencies, or refactor outside your scope.
```

---
---

## Merge Agent

**Run from:** repo root (`repos/meeting-intelligence`)
**When:** After all Round 1 streams report complete and code review is done

```
You are a merge agent. You do NOT write feature code. Your only job is to merge completed feature branches into main in the correct order, running tests after each merge.

Read CLAUDE.md in the repo root first — especially the "Git Discipline" section.

Merge order (strict — do not reorder):
1. feature/wave1-search-backend (A3)
2. feature/wave1-web-ui-fixes (A1)
3. feature/wave1-auth-refresh (A2)
4. feature/wave1-bicep-iac (A4)

For EACH branch, follow this exact sequence:

1. Ensure you're on main and it's clean:
   git checkout main
   git pull origin main
   git status  # must be clean

2. Merge with no-ff:
   git merge feature/wave1-{branch-name} --no-ff -m "Merge stream A{N}: {description}"

3. Run server tests:
   cd server && uv run python -m pytest && cd ..

4. Run web build:
   cd web && npm run build && cd ..

5. If BOTH pass, push:
   git push origin main

6. If EITHER fails, STOP. Do not merge the next branch. Report:
   "MERGE BLOCKED after A{N}. Tests: [pass/fail]. Build: [pass/fail]. Error: [details]"

After A1 merge, also apply this one-line fix on main:
- In server/src/schemas.py, find the ActionListFilter class and change the status field default from "Open" to None. This resolves a consistency issue flagged in code review where MCP still defaults to Open but the REST API no longer does.
- Commit: git commit -am "fix: ActionListFilter status default None for consistency (review finding)"

After ALL 4 merges are done and pushed, report:
"All Round 1 merges complete. Main is clean. Tests: [count] passed. Ready for Round 2."

Rules:
- Do NOT write feature code
- Do NOT refactor anything
- Do NOT skip tests between merges
- If a merge has conflicts, STOP and report — do not resolve them yourself
- If tests fail after a merge, STOP and report — do not try to fix the code
```

---

## Fix-Back Prompts

Use these when a code review finds issues that need fixing before merge. Send to the ORIGINAL agent on its feature branch.

### A1 Fix-Back — Search Result UI Issues

**Worktree:** `repos/worktrees/wave1-a1`
**Branch:** `feature/wave1-web-ui-fixes`

```
Your code review found two medium-severity issues in the MeetingsList search implementation. Fix these on your current feature branch.

Issue 1 — Search results show "null" for source badge:
The search API returns results without attendees and source fields. Your search result rendering uses the same MeetingCard/row component as the main list, which tries to display source as a badge. When source is undefined/null, it renders the literal text "null". Fix: conditionally render the source badge only when the value exists.

Issue 2 — Search snippet not displayed:
The search API returns a snippet field with context around the match, but your search results don't display it anywhere. The snippet is the most useful part of search results — without it, users can't see WHY a meeting matched. Fix: display the snippet below the meeting title in search results, styled as secondary text.

After fixing:
1. git add the changed files
2. git commit -m "fix: handle null source badge and display search snippets (review findings)"
3. Run post-flight checklist again (tests + build + scope check)
4. git push origin feature/wave1-web-ui-fixes

Report when done with updated post-flight results.

Rules:
- Only touch web/src/pages/MeetingsList.jsx — same file scope as before
- Do NOT touch schemas.py or mcp_server.py — those are being fixed elsewhere
- Do NOT touch any other files
```

### A4 Fix-Back — ACR Build Error Handling + RBAC Wait

**Worktree:** `repos/worktrees/wave1-a4`
**Branch:** `feature/wave1-bicep-iac`

```
Your code review found one bug and one should-fix in deploy-bicep.sh. Fix these on your current feature branch.

Bug — ACR build error swallowed:
In Phase 1, the az acr build command has --no-logs 2>&1 which redirects stderr to stdout. If the ACR build fails, the exit code doesn't propagate and the script continues with a broken image. Fix: capture the exit code properly. The ACR build failing should stop the entire script.

Should-fix — RBAC wait too short:
The RBAC propagation wait is 90 seconds. CLAUDE.md documents 5-10 minutes for RBAC propagation on greenfield deploys. 90s is optimistic. Increase to 180 seconds. The Phase 10 health check provides a safety net, but a longer wait reduces unnecessary crash-loop cycles.

After fixing:
1. git add infra/deploy-bicep.sh
2. git commit -m "fix: ACR build error propagation and increase RBAC wait to 180s (review findings)"
3. Run post-flight checklist again (tests + build + scope check)
4. git push origin feature/wave1-bicep-iac

Report when done with updated post-flight results.

Rules:
- Only touch infra/deploy-bicep.sh — same file scope as before
- Do NOT touch any server/ or web/ files
```

---

## A6 Additional Note

When launching A6, append this to the end of the standard A6 launch prompt:

```
Additional from code review:
- The search_meetings MCP tool description (line ~95 in mcp_server.py) currently says "title and transcript". Update it to "title, summary, and transcript" to reflect the A3 change that added Summary to the search. This is a one-line description fix — do it alongside your other work.
- The list_actions MCP tool description says "Default returns Open actions only". After A1's fix, list_actions returns ALL statuses when no filter is set. Update the description to reflect this.
```
