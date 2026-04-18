# Character Import - Design Document

This directory holds the design and implementation-tracking document for the
"dynamic import" feature: given an arbitrary character sheet document (any
format, any layout), produce a Draft character in the database that the user
can then review and Apply.

The design lives in [`design.md`](./design.md). Each phase has a checklist.
As we implement items, we tick them off. As we discover new cases (especially
during fixture generation), we append new unchecked items rather than rewriting
history.

## How to use this doc

1. Read `design.md` top to bottom before starting a phase.
2. When starting work on a phase, flip items from `[ ]` to `[~]` (in progress)
   and update the status line at the top of the phase.
3. When finishing an item, flip to `[x]` and link to the commit / PR / test file.
4. If the implementation reveals a new case or constraint, **add a new
   unchecked item** rather than silently expanding an existing one. The
   unchecked items are the to-do list; the checked items are the audit trail.
5. Open questions for the user live in the "Open Questions" section at the
   bottom. Move them out when answered (into the relevant phase or constraint).
