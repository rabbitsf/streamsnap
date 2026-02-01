# CLAUDE.md — AI Development Rules (Read First)

This project uses an **external memory + canonical implementation** workflow.
AI assistance is allowed only when these rules are followed.

---

## Core principles (non-negotiable)

IMPORTANT: Always restate the goal before doing anything.

1. **Single Source of Truth**
   - Every behavior must have exactly one canonical implementation.
   - All triggers (UI, shortcuts, APIs, scripts, jobs) must call into it.

2. **Reuse Over Duplication**
   - Never copy logic to “just make it work”.
   - If similar code exists, reuse or refactor instead of re-implementing.

3. **Artifacts vs. Generators**
   - Generated files (artifacts) must NOT be edited directly.
   - Always modify the canonical generator/template and regenerate outputs.

4. **Search Beyond First Match**
   - Do not stop at the first grep/search result.
   - Explicitly check multiple plausible locations before deciding where to change code.

---

## Required workflow for every change

### Before making code changes
- Read `docs/PROJECT_GUIDE.md`
- Restate the goal in terms of **behavior**, not files
- Identify the **canonical implementation**
- List at least two other locations you checked
- Decide: reuse existing code or extend canonical code

### After making code changes
- Ensure all relevant triggers route to the canonical implementation
- Update `docs/PROJECT_GUIDE.md` if any of the following changed:
  - canonical locations
  - responsibilities of modules / templates / generators
  - new entrypoints, shortcuts, or workflows
- Regenerate artifacts if generators/templates were modified

---

## Documentation rules

- **CLAUDE.md**
  - Defines permanent rules and invariants
  - Changes rarely
  - Updated only when a new rule applies to *all future work*

- **docs/PROJECT_GUIDE.md**
  - Living system map and external memory
  - Records *what exists*, *where*, and *why*
  - Updated whenever the system structure or behavior changes

---

## If rules conflict or are unclear
- Stop and ask for clarification
- Do NOT guess or invent new structure

