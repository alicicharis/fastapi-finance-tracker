---
name: curate
description: Audit, prune, merge, and reconcile .claude/references/ files and the CLAUDE.md references table
---

# Curate Knowledge Base

Maintain the project knowledge base so it stays accurate, deduplicated, and in sync with the codebase. Run this periodically or when reference files feel stale or bloated.

If `$ARGUMENTS` is provided, treat it as a scope hint (e.g., "stock", "auth") and focus only on matching reference files. Otherwise, audit everything.

## 1. Inventory

Scan `.claude/references/` and build a list of all reference files with:

- File name and size
- Last modified date (use `git log -1 --format='%ai'` per file)
- Top-level headings (to understand scope)

Also read the REFERENCE DOCUMENTATION section in `CLAUDE.md` and note which files are listed there.

Output a summary table to the user before proceeding.

## 2. Detect Staleness

For each reference file, check whether the knowledge is still valid:

- **Key Files sections**: Verify that every file path mentioned still exists. Flag any that don't.
- **Patterns & Conventions**: Grep for usage of the described patterns in the codebase. If a pattern has zero matches, flag it as potentially stale.
- **Key Decisions**: Check if the decision's context still applies (e.g., does the code still use the chosen approach, or has it been refactored away?).

Classify each file as:

- **Current** — content matches codebase
- **Partially stale** — some items are outdated
- **Fully stale** — most content no longer applies

## 3. Evaluate Usefulness

For each item in each reference file, ask: **"Would an LLM benefit from knowing this before working in this domain, or could it figure it out by reading the code?"**

Flag items as **low-value** if they:

- Catalog which functions, exports, or routes exist in which files — an agent can read the files directly
- Restate how a framework or library works — an agent can read the docs
- Describe straightforward CRUD or boilerplate patterns that are self-evident from the code
- Document implementation details that are obvious from reading the relevant source files

Flag items as **high-value** if they:

- Explain a non-obvious decision and the reasoning behind it (especially rejected alternatives)
- Warn about a gotcha or pitfall that would cost debugging time
- Describe a project-specific convention that deviates from framework defaults
- Capture context that lives outside the code (business constraints, compliance requirements, stakeholder decisions)

For partially stale or low-value-heavy files, consider whether the file still justifies its existence or should be pruned entirely.

## 4. Detect Overlaps & Misnamed Files

Compare reference files pairwise by their headings and content topics. Flag files that:

- Cover the same domain (e.g., `stock-operations.md` and `inventory-management.md`)
- Have duplicate or near-duplicate entries across files
- Could be logically merged into a single, more coherent document

Suggest specific merges with a proposed file name.

Also check whether each file's **name** still reflects its actual scope. Compare the file name against the headings and content inside it. If the content has grown beyond what the name implies (e.g., a file named `foo-crud.md` now covers events, subscriptions, and processing beyond basic CRUD), flag it with a rename suggestion. Prefer broader, shorter names that won't become stale as knowledge expands.

## 5. Propose Changes

Present all findings to the user as a structured action plan:

```
### Staleness
- `file.md`: [current | partially stale | fully stale]
  - Stale items: [list specific items]

### Low-Value Items
- `file.md`: [list items flagged as low-value and why]

### Overlaps
- `file-a.md` + `file-b.md` → merge into `proposed-name.md`
  - Reason: [why they overlap]

### Renames
- `old-name.md` → `new-name.md`
  - Reason: [content has outgrown the current name]

### CLAUDE.md Sync
- Missing from CLAUDE.md: [files that exist but aren't referenced]
- Orphaned in CLAUDE.md: [entries pointing to files that don't exist]

### Recommended Actions
1. [action] — [reason]
2. ...
```

**Do NOT execute any changes yet.** Wait for user approval.

## 6. Execute Approved Changes

After the user confirms (they may approve all, some, or modify the plan), execute only what was approved:

- **Rename files**: Use `git mv` to rename files so history is preserved. Update any references in `CLAUDE.md` accordingly.
- **Merge files**: Combine content intelligently — deduplicate, reconcile conflicting statements (prefer the more recent or code-verified version), and maintain the standard reference doc structure (Overview, Key Decisions, Patterns & Conventions, Gotchas & Pitfalls, Key Files).
- **Prune stale content**: Remove items flagged as stale. If an entire file is fully stale, delete it.
- **Reconcile CLAUDE.md**: Update the REFERENCE DOCUMENTATION section to match the current state of `.claude/references/`. Add missing entries, remove orphaned ones.

## 7. Summary

Tell the user:

- Files merged, pruned, or deleted
- Items removed as stale (count and brief description)
- CLAUDE.md changes made
- Current state of `.claude/references/` (file count, total knowledge items)
