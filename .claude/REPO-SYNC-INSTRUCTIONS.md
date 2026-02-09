# Repo Sync Instructions

**For agents working inside a code repository (Claude Code, VS Code, etc.)**

This file explains how to keep your repo's context in sync with the Second Brain project management system. Read this if you're working in a repo that's linked to a Second Brain project.

---

## What Is the Second Brain?

The Second Brain is the project management system at `/Second Brain/Project Management/`. It tracks projects from idea through delivery. Every project with code has a folder there containing status, decisions, comms, and a `_repo-context.md` file that summarises your codebase.

**You don't need access to the Second Brain to follow these instructions.** But if you do have access, even better.

---

## Your Responsibilities

### 1. Keep CLAUDE.md Current

Your repo's `CLAUDE.md` is the source of truth for codebase context. The Second Brain pulls from it. If `CLAUDE.md` is stale, everything downstream is stale.

**Update CLAUDE.md when:**
- Architecture changes (new services, removed components, changed patterns)
- Key files are added, renamed, or deleted
- API surface changes (new endpoints, changed contracts)
- Deployment process changes
- Tech debt is added or resolved

**CLAUDE.md should always reflect the current state, not the history.** History goes in git.

### 2. Update _repo-context.md (If You Have Access)

If you can access the Second Brain project folder, update `_repo-context.md` at session end:

```
/Second Brain/Project Management/Projects/[Project Name]/_repo-context.md
```

Update these sections:
- **Recent Changes** — what changed this session
- **Current State** — branch, last deploy, build status
- **Tech Debt / Known Issues** — anything added or resolved
- **Last Synced** — today's date and your agent identifier

### 3. Update _repo-link.md Sync Date (If You Have Access)

```
/Second Brain/Project Management/Projects/[Project Name]/_repo-link.md
```

Set `**Last Synced:**` to today's date and your agent identifier.

---

## What Goes Where

| Information | Lives In | Updated By |
|-------------|----------|------------|
| Codebase architecture, key files, API surface | Repo `CLAUDE.md` | Repo-side agent |
| Codebase snapshot for project context | Project `_repo-context.md` | Either side (whoever has access) |
| Project stage, decisions, blockers, next actions | Project `_status.md` | Cowork-side agent |
| Repo link and sync status | Project `_repo-link.md` | Either side |
| Commit history, code changes | Git | Repo-side agent |
| Meeting notes, comms, proposals | Project `comms/`, `1-kickoff/` etc. | Cowork-side agent |

---

## Session Start (Repo Side)

Before starting work in a repo:

1. Read `CLAUDE.md` — orient yourself
2. If you have Second Brain access, check the project's `_status.md` for current priorities and decisions
3. If `_status.md` has a lock from another agent (<2hr old), operate read-only on project docs

## Session End (Repo Side)

Before ending work in a repo:

1. **Update `CLAUDE.md`** if architecture, key files, API surface, or tech debt changed
2. **If you have Second Brain access:**
   - Update `_repo-context.md` with what changed
   - Update `_repo-link.md` sync date
3. **If you don't have Second Brain access:**
   - Ensure `CLAUDE.md` is current — the Cowork-side agent will pull from it next session

---

## Repo-to-Project Mapping

| Repo | GitHub | Second Brain Project Folder |
|------|--------|-----------------------------|
| meeting-intelligence | GenerationAI-2/Meeting-Intelligence-System | `Projects/GenerationAI - Meeting Intelligence System/` |
| truscreen-surveillance | GenerationAI-2/truscreen-surveillance | `Projects/TruScreen - Brand Surveillance Tool/` |
| website-factory | GenerationAI-2/website-factory | `Projects/Internal - Website Revolution System/` |
| wf-generationai | GenerationAI-2/generationai-website | `Projects/Internal - Website Revolution System/` |
| wf-myadvisor | GenerationAI-2/myadvisor-website | `Projects/Internal - Website Revolution System/` |

---

## Key Rule

**Don't duplicate code into the Second Brain.** The `_repo-context.md` file is a summary — architecture, recent changes, API surface, tech debt. Not source code. If a Cowork agent needs actual code, it reads from the repo directly.

---

*This file is maintained in the Second Brain at `Templates/REPO-SYNC-INSTRUCTIONS.md`. Copy it into any repo that needs it.*
