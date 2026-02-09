# CLAUDE.md Template for Code Repositories

*Copy this file to the root of any code repository and rename to `CLAUDE.md`. Fill in the sections below.*

---

# [Project Name] - Agent Context

**Last Updated:** [Date]
**Project Status:** [SHAPE / BUILD / SHIP / CLOSE]
**Owner:** Caleb Lucas

---

## What This Is

[One paragraph: What does this tool/system do? What problem does it solve?]

---

## Quick Start

```bash
# How to run this locally
[commands here]
```

**Required environment variables:**
- `VAR_NAME` — [what it's for]

---

## Architecture

[2-3 sentences: How is this structured? What are the main components?]

```
/src
├── [folder] — [what it does]
├── [folder] — [what it does]
└── [file]   — [what it does]
```

---

## Key Files

| File | Purpose |
|------|---------|
| `[path]` | [what it does] |
| `[path]` | [what it does] |

---

## Patterns & Conventions

- [Convention 1 — e.g., "All API calls go through /lib/api.py"]
- [Convention 2 — e.g., "Environment config in .env, never hardcoded"]
- [Convention 3]

---

## What's Been Tried & Failed

| Approach | Why It Failed | Date |
|----------|---------------|------|
| [approach] | [reason] | [date] |

---

## Current State

**What's working:**
- [feature/capability]

**What's in progress:**
- [feature/capability]

**Known issues:**
- [issue]

---

## Technical Debt

- [ ] [thing that needs fixing but is parked]
- [ ] [thing that needs fixing but is parked]

---

## Dependencies

| Package | Version | Why |
|---------|---------|-----|
| [name] | [version] | [reason for choosing] |

---

## Agent Instructions

When working in this codebase:

1. **Read this file first** before making changes
2. **Don't review code unless asked** — context window is expensive
3. **Follow existing patterns** — check the Patterns section above
4. **Update this file** when you make significant changes
5. **Log decisions** in the project's `decisions.md` file

**Before writing code:**
- Confirm you understand the architecture
- Check "What's Been Tried & Failed" to avoid repeating mistakes
- Start in Plan Mode — outline approach before implementing

---

## Links

- **Project folder:** [path to Second Brain project folder]
- **Shape document:** [link]
- **Decision log:** [link]

---

## Skills Used

This repo uses skills from Second Brain. If you improve a pattern, update the source.

| Skill | Path | Last Synced |
|-------|------|-------------|
| [skill-name] | `Second Brain/Project Management/Skills/[skill-name]/SKILL.md` | [date] |

---

## Session End — Skill Sync

Before ending any session, ask:

1. **Did I learn a reusable pattern?** → Update the relevant skill
2. **Did I find a better way to do something the skill describes?** → Update the skill
3. **Did I discover API/tool behaviour that differs from docs?** → Add to skill
4. **Is there a new pattern worth capturing?** → Create new skill using `Templates/skill-template.md`

**Update the skill in Second Brain, not here.** This file references skills; it doesn't duplicate them.

**Triggers that should prompt skill updates:**
- "This worked better than expected"
- "I wouldn't do it that way again"
- "This pattern would work for other projects"

---

*This file is the technical context for agents. Keep it current.*
