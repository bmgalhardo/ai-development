---
name: to-tickets
description: Break a plan, spec, or the current conversation into a set of tracer-bullet tickets, each declaring its blocking edges, published to the issue tracker.
disable-model-invocation: true
---

# To Tickets

Break a plan, spec, or conversation into a set of **tickets**: tracer-bullet vertical slices, each declaring the tickets that **block** it.

The issue tracker should have been provided to you.

## Process

### 1. Gather context

Work from whatever is already in the conversation context. If the user passes a reference (a spec path, an issue number or URL) as an argument, fetch it and read its full body and comments.

Before drafting, verify in the live conversation that `/grill-me` reached an empty frontier and the user explicitly confirmed shared understanding. If that confirmation is absent, stop and return to `/grill-me`; do not infer completion from an existing spec or from the user's approval of a ticket breakdown. While reading the spec, flag any missing decision needed to define scope, acceptance or dependencies. If ticket drafting exposes such a gap, pause ticket publication, return that question to `/grill-me`, update the spec from the settled answer, and resume ticketing only after the user confirms the updated understanding.

### 2. Explore the codebase (optional)

If you have not already explored the codebase, do so to understand the current state of the code. Ticket titles and descriptions should use the project's domain glossary vocabulary, and respect the decisions in the domain docs in the area you're touching.

Read unresolved entries in the previous cycle's `debt.md` and its review's Code debt section.
Carry unresolved entries into the new cycle's `debt.md`, preserving their source.
Assign a relevant small prefactor explicitly to the ticket that needs it.
Propose a separate ticket and blocking edges for a wide refactor needed by the planned work.
Leave other debt open; do not silently add it to approved scope.

Look for opportunities to prefactor the code to make the implementation easier. "Make the change easy, then make the easy change."

### 3. Draft vertical slices

Break the work into **tracer bullet** tickets.

<vertical-slice-rules>

- Each slice cuts a narrow but COMPLETE path through every layer (schema, API, UI, tests): vertical, NOT a horizontal slice of one layer
- A completed slice is demoable or verifiable on its own
- Each slice is sized to fit in a single fresh context window
- Any prefactoring should be done first
- A spec's performance target is measured in the first slice that builds the hot path, against the target, as an acceptance criterion. It extrapolates from a sample rather than timing a full worst-case run, and records the result in Comments
- A slice includes the docs for what it builds: it copies its part of the spec's agreed text into the docs in the same commit, so the docs never run ahead of the build

</vertical-slice-rules>

Give each ticket its **blocking edges**: the other tickets that must complete before it can start. A ticket with no blockers can start immediately.

**Wide refactors are the exception to vertical slicing.** A **wide refactor** is one mechanical change (rename a column, retype a shared symbol) whose **blast radius** fans across the whole codebase, so a single edit breaks thousands of call sites at once and no vertical slice can land green. Don't force it into a tracer bullet; sequence it as **expand–contract**. First expand: add the new form beside the old so nothing breaks. Then migrate the call sites over in batches sized by blast radius (per package, per directory), each batch its own ticket blocked by the expand, keeping CI green batch to batch because the old form still exists. Finally contract: delete the old form once no caller remains, in a ticket blocked by every migrate batch. When even the batches can't stay green alone, keep the sequence but let them share an integration branch that all block a final integrate-and-verify ticket; green is promised only there.

### 4. Quiz the user

Present the proposed breakdown as a numbered list. For each ticket, show:

- **Title**: short descriptive name
- **Blocked by**: which other tickets (if any) must complete first
- **What it delivers**: the end-to-end behaviour this ticket makes work

Ask the user:

- Does the granularity feel right? (too coarse / too fine)
- Are the blocking edges correct: does each ticket only depend on tickets that genuinely gate it?
- Should any tickets be merged or split further?

Iterate until the user approves the breakdown.

### 5. Publish the tickets to the issue tracker

Publish the approved tickets to the issue tracker (this repo's `.scratch/<game>/`), one per ticket, in dependency order (blockers first). Each ticket's "Blocked by" lists the tickets it depends on. Use the ticket template below: one ticket per file, never a single combined file.

Work the **frontier**: any ticket whose blockers are all done. For a purely linear chain that means top to bottom.

<ticket-template>

# <NN>: <Ticket title>

**Repo:** the game's repo, relative to the workflow repo (`../<game>`). Workers act there.

**What to build:** the end-to-end behaviour this ticket makes work, from the user's perspective, not a layer-by-layer implementation list.

**Blocked by:** the numbers/titles of the tickets that gate this one, or "None (can start immediately)".

**Status:** open

**Touches:** the main modules and docs this ticket changes, by name, so tickets that don't overlap can be built at the same time.

**Spec:** a link to the spec (`../spec.md`) and the sections this ticket relies on, by heading.

**Mock:** if the ticket has a look: the mock file, by its path from the workflow repo's root (`.scratch/<game>/exploration/cycle/mocks/...`), the variant the user picked, and only the parts this ticket builds, each with where it is in the file (line ranges or element ids, and its CSS rules). The mock is the agreed design; the implementer matches it.

**Assets:** each agreed asset this ticket brings into the game, by its path in `.scratch/<game>/exploration/cycle/assets/` (made in the review; the implementer copies it in, never remakes it).

**Docs to write:** each doc file this ticket updates, with the agreed text to put there, written as built. The implementer copies it in with the code.

- [ ] Acceptance criterion 1
- [ ] Acceptance criterion 2
- [ ] The docs updated for what this builds, in the same commit

</ticket-template>

Keep each ticket self-contained: a worker starts from a fresh context and reads only the ticket and what it points to, so point to sections and parts, never to whole files.

Avoid specific file paths or code snippets: they go stale fast. Exception: if a prototype produced a snippet that encodes a decision more precisely than prose can (state machine, reducer, schema, type shape), inline it and note briefly that it came from a prototype. Trim to the decision-rich parts, not a working demo, just the important bits.
