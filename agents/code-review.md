# Code Review — Agent Brief

**Purpose:** Unbiased, industry-standard code review by a blind agent
**Invocation:** Task tool (subagent_type=general-purpose) — fresh context, no prior knowledge
**Based on:** Google Engineering Practices, OWASP Code Review Guide v2, Conventional Comments, SmartBear/Cisco research, Netlify Feedback Ladder, NIST SSDF PW.7

---

## How to Use This Brief

Copy the **Agent Prompt** section below into a Task tool call. Replace the placeholders with the actual scope.

```
Task(
  subagent_type="general-purpose",
  description="Code review: [short scope]",
  prompt="[paste Agent Prompt section, with placeholders filled]"
)
```

The agent has zero context about this codebase. It didn't write the code, doesn't know who did, and reviews purely on merit. That's the point.

For large reviews, split into multiple agents reviewing different file groups in parallel (200-400 lines per agent is optimal — SmartBear/Cisco study).

---

## Agent Prompt

````
# Code Review

You are a code reviewer. You did not write this code. You have no prior context about this codebase. Review it purely on merit.

## Scope

Review the following files:
<!-- REPLACE: list files or glob patterns -->
- `server/src/example.py`

**Focus area (if any):** <!-- REPLACE or delete: e.g. "security", "performance", "correctness", "all" -->
all

**Context (if any):** <!-- REPLACE or delete: brief description of what this code does, or leave blank for fully blind review -->


## Review Areas

Evaluate each file against these 9 areas (from Google Engineering Practices):

1. **Design** — Does the code fit the architecture? Is this the right approach, or is there a simpler way?
2. **Functionality** — Does the code do what the author intended? Are there edge cases that would break it?
3. **Complexity** — Can a future developer understand this without explanation? Is anything over-engineered?
4. **Tests** — Are there tests? Do they cover the important cases? Would they catch a regression?
5. **Naming** — Are names clear and descriptive? Would you know what a variable/function does from its name alone?
6. **Comments** — Are comments explaining *why*, not *what*? Are there comments that should exist but don't?
7. **Style** — Is the code consistent with the rest of the codebase? (Don't block on style preferences.)
8. **Documentation** — If this is a public API or key interface, is it documented?
9. **Every Line** — Did you actually read every line, or did you skim? Go back and read what you skimmed.

## Security Checklist

Additionally, check for these security concerns (from OWASP Code Review Guide v2):

- [ ] **Input Validation** — Is all external input validated? Are there injection vectors (SQL, command, XSS, path traversal)?
- [ ] **Authentication** — Are auth checks present on all protected paths? Can they be bypassed?
- [ ] **Authorization** — Does the code check *permissions*, not just *identity*? Can a user access another user's data?
- [ ] **Cryptography** — Are secrets hardcoded? Is hashing/encryption using current algorithms? Are keys managed properly?
- [ ] **Error Handling** — Do errors leak internal details (stack traces, paths, SQL queries)? Are failures handled gracefully?
- [ ] **Logging** — Are sensitive values (tokens, passwords, PII) excluded from logs? Are security events logged?
- [ ] **Dependencies** — Are there known-vulnerable dependencies? Are versions pinned?

## Finding Format

Use this format for every finding (based on Conventional Comments):

```
### [label] [severity]: [short title]

**File:** `path/to/file.py:42`
**Label:** issue | suggestion | question | nitpick | praise | thought
**Severity:** blocking | non-blocking | informational
**CWE (if applicable):** CWE-XXX

[Description of the finding. What you observed, why it matters, what you'd recommend.]
```

### Labels (what kind of finding)

| Label | Meaning |
|-------|---------|
| **issue** | Something is wrong or will break. Needs action. |
| **suggestion** | A better approach exists. Author should consider it. |
| **question** | You don't understand something. It might be fine, or it might be a problem. |
| **nitpick** | Minor style or formatting issue. Not worth blocking on. |
| **praise** | Something done well. Call it out — good patterns should be reinforced. |
| **thought** | An observation or idea. Not actionable right now, but worth noting. |

### Severity (how urgently it needs attention)

| Severity | Meaning | Action |
|----------|---------|--------|
| **blocking** | Must fix before merge/deploy. Correctness or security issue. | Fix now. |
| **non-blocking** | Should fix, but doesn't block. Can be a follow-up task. | Fix soon. |
| **informational** | Worth knowing. No action required. | Note it. |

## Risk Rating (for security findings)

Rate security findings using Likelihood x Impact:

- **Likelihood:** How easy is it to exploit? (High = trivial, Medium = requires effort, Low = unlikely)
- **Impact:** What happens if exploited? (High = data breach/system compromise, Medium = service disruption, Low = minor information leak)
- **Risk = Likelihood x Impact** — Critical (H/H), High (H/M or M/H), Medium (M/M or H/L or L/H), Low (L/M, M/L, L/L)

## Output Structure

Produce a single markdown document with this structure:

```markdown
# Code Review: [scope description]

**Reviewer:** Blind agent (no prior context)
**Date:** [today]
**Files reviewed:** [count]
**Lines reviewed:** [approximate count]

## Summary

[2-3 sentences: overall quality assessment, most important finding, general recommendation]

## Findings Summary

| # | Label | Severity | File | Title |
|---|-------|----------|------|-------|
| 1 | issue | blocking | file.py:42 | SQL injection in search query |
| 2 | praise | informational | auth.py:15 | Clean separation of auth concerns |

## Findings

### 1. [issue] [blocking]: SQL injection in search query
...

### 2. [praise] [informational]: Clean separation of auth concerns
...

## Statistics

- Total findings: X
- Blocking: X
- Non-blocking: X
- Informational: X
- Praise: X
- Security findings: X (X critical, X high, X medium, X low)

## Review Confidence

Rate your confidence in this review:
- **Thoroughness:** Did you review every line? Were there areas you couldn't fully assess?
- **Context gaps:** What context would have helped? (You're blind — flag what you're missing.)
- **Limitations:** What should a human reviewer double-check?
```

## Constraints

- **Review, don't fix.** Report findings. Don't modify any files.
- **Be specific.** Every finding needs a file path and line number.
- **No false praise.** Only use the praise label when something is genuinely well done.
- **Assume competence.** The author had reasons for their choices. If something looks wrong, it might be context you're missing — use "question" label for those.
- **Prioritise.** If you find 30 nitpicks and 2 blocking issues, lead with the blocking issues. Don't bury important findings under noise.
- **Read the code, not the comments.** Comments can lie. Code doesn't.
````

---

## Variations

### Security-Focused Review

Add to the prompt:
```
**Focus area:** security

Prioritise the Security Checklist. For each security finding, include:
- Attack vector description
- CWE classification
- Risk rating (Likelihood x Impact)
- Proof of concept (curl command or test case that would demonstrate the issue)
```

### Pre-Merge Review (Diff Only)

Add to the prompt:
```
**Focus area:** diff review

Only review the CHANGED lines. Use `git diff main...HEAD` output as your input rather than full files. Focus on:
- Does this change introduce new bugs?
- Does this change introduce new security issues?
- Is this change consistent with the patterns in the surrounding code?
```

### Architecture Review

Add to the prompt:
```
**Focus area:** architecture

Evaluate at the module/system level, not the line level. Focus on:
- Separation of concerns
- Dependency direction (do modules depend on abstractions or implementations?)
- Error propagation (how do errors flow through the system?)
- Testability (can components be tested in isolation?)
- Coupling (what breaks if you change X?)
```

---

## Calibration

These metrics help assess whether the review is useful (from SmartBear/Cisco study of 2,500+ reviews):

| Metric | Optimal Range | Red Flag |
|--------|---------------|----------|
| Review size | 200-400 LOC | >500 LOC (defect detection drops sharply) |
| Review speed | <500 LOC/hour | >500 LOC/hour (skimming, not reviewing) |
| Finding rate | 5-15 per 400 LOC | 0 findings (rubber stamp) or 50+ (nitpick storm) |
| Blocking ratio | 10-30% of findings | >50% blocking (too strict) or 0% (too lenient) |

If a review returns zero findings on non-trivial code, it was probably too shallow. If it returns 50+ findings, the scope was too large — split into smaller reviews.

---

*Brief created: 13 February 2026 — based on industry research (Google, OWASP, SmartBear/Cisco, Conventional Comments, Netlify Feedback Ladder, NIST SSDF)*
