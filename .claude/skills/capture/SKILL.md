---
name: capture
description: Capture knowledge from completed work into the project knowledge base
---

# Capture Knowledge

After completing implementation work, extract and persist valuable knowledge so future conversations have full context. The goal is to save things that would genuinely save a future LLM time and frustration — not to document what the code already says.

## 1. Gate Check — Is Capture Warranted?

Before doing anything, evaluate whether this conversation produced knowledge worth persisting. The litmus test: **would a future agent working in this codebase waste significant time without this knowledge?**

Capture is warranted when the work involved:

- A **hard-won discovery** — the agent (or user) struggled, looped, or hit dead ends before finding the right approach. This is the #1 signal. If it took multiple attempts to figure out, the next agent will hit the same wall.
- A **non-obvious project-specific decision** — a real choice between alternatives where the reasoning isn't evident from the code alone (business constraints, performance tradeoffs, compliance requirements)
- A **gotcha or pitfall** that cost debugging time — something that looks like it should work but doesn't, and why
- A **project-specific convention** that deviates from the framework/library defaults

**Skip capture entirely** (and tell the user "nothing worth capturing") if the work was:

- A straightforward bug fix, typo, or config change
- Following an already-documented pattern
- Routine CRUD / boilerplate with no surprises
- Work where all context is already in the code, commit message, or PR description
- Standard usage of a framework or library — even if you learned how it works during the session, that's documentation, not project knowledge

If `$ARGUMENTS` is provided, use it as a hint — but still apply this gate.

## 2. Analyze What Was Done

Review the current conversation to identify knowledge worth saving. Pay special attention to:

- **Struggle points** — where did the agent loop, backtrack, or try multiple approaches? What was the wrong path and why didn't it work? What finally worked and why? This is the highest-value knowledge because it prevents future agents from repeating the same mistakes.
- **Project-specific decisions** — choices between alternatives where the reasoning matters. Focus on the _why_, not the _what_ — the code shows what was chosen, the reference doc should explain why.
- **Non-obvious behaviors** — things about this specific codebase or its dependencies that surprised you and would surprise the next agent.

### The "Framework Docs" Test

Before capturing any item, apply this test: **Could an agent learn this by reading the framework's documentation or the code itself?**

If yes, don't capture it. For example:

- "TanStack Router uses `validateSearch` for type-safe search params" — this is framework docs, skip it
- "We use `.catch()` on all Zod search param schemas" — this is just describing what the code does, skip it
- "Search params must use `.catch()` because the app crashes on back-navigation in Safari without it — we spent 2 hours debugging this and the error is a silent hydration mismatch with no stack trace" — THIS is worth capturing

The difference: the first two are _what_ and _how_ (readable from code/docs). The third is _why this specific project does it this way_ and _what happens if you don't_.

### Filtering Rules

- **No framework tutorials**: Don't explain how a library works. Only capture your project's specific, non-obvious choices about how to use it — and only when the reasoning isn't obvious from the code.
- **No code reproduction**: Reference file paths. Never paste implementation that exists in the codebase.
- **Topic coherence**: Route each item to the correct topic file based on domain, not based on when it was discovered.
- **Verify against final state**: Cross-reference against actual code changes (read the files). Don't capture intermediate approaches that were abandoned.

## 3. Categorize Knowledge by Topic

Group into **domain topics** (not phases or time periods). Derive topics from the actual domains in the project — e.g., auth, API design, data model, deployments. Whatever makes sense for this specific codebase.

## 4. Write or Update Reference Documents

Check `.claude/references/` for existing files on the same topic.

- **Existing file**: Merge in new knowledge. Don't duplicate.
- **No file + substantial knowledge** (2-3+ meaningful items): Create a new one with a descriptive kebab-case name.
- **No file + thin knowledge**: Append to a related file, or skip.

Never name files after phases or time periods. Name them after the domain.

**Structure each doc like this:**

```markdown
# [Topic Title]

## Key Decisions

- **Decision**: What was chosen
  - **Why**: The reasoning (business constraint, performance, compatibility...)
  - **Alternatives considered**: What was rejected and why

## Gotchas & Hard-Won Knowledge

- **Problem**: What went wrong or was confusing
  - **Symptoms**: What it looked like (error messages, unexpected behavior)
  - **Root cause**: Why it happened
  - **Solution**: What fixed it
  - **How to avoid**: What to do (or not do) next time

## Project Conventions

- Convention and when it applies — only if it deviates from defaults
```

Only include sections that have content. The "Gotchas & Hard-Won Knowledge" section is the most valuable — prioritize it. Skip "Overview" sections that just describe what the code does (an agent can read the code). Skip "Key Files" sections (an agent can find files).

## 5. Update CLAUDE.md

**Conventions**: Only add things applicable to all future work, not already covered, and genuinely useful as a rule.

**References table**: Update if you created or renamed reference docs.

Skip this step if nothing qualifies.

## 6. Summary

Tell the user:

- What reference doc(s) were created or updated
- The most important knowledge captured — focus on what will save the most time for future agents
- If you skipped capture, explain why briefly
