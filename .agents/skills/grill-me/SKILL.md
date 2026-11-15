---
name: grill-me
description: Interview the user about review feedback, a plan, decision, or idea until shared understanding is reached. Keep the interview entirely in conversation; write no files.
disable-model-invocation: true
---

When the user delegates the cycle to `/pm`, use [pm](../pm/SKILL.md) instead of interviewing them.
Its delegated decisions replace this skill's answer and confirmation gates for that run.

Use domain-modeling's conversational techniques throughout the interview: challenge terminology, prefer the user's words, and stress-test decisions with concrete scenarios. Its file-writing steps do not apply here.

The issue tracker should have been provided to you. The main input is the session's project's latest `feedback.md` (in `.scratch/<project>/<cycle>/`); read it, the project's `docs/review.md` and the domain docs. The feedback is the plan to grill. The session may start fresh or continue the review conversation: do not require earlier chat to understand the review, and retain relevant live context when it is available.

This skill is pure conversation. Do not create or update any files: no spec, review notes, glossary, decision log, scratch notes or mocks. Keep the design tree, settled terms, decisions and open questions in the chat. There is no persisted handoff from grilling to `to-spec`; that skill reads the live conversation and publishes the spec to the configured issue tracker. An existing spec is not an interview scratchpad.

Interview the user relentlessly until you reach a shared understanding. Map this as a **design tree**: every decision branches into the decisions that hang off it.

Work the tree in **rounds**. The **frontier** is every decision whose prerequisites are already settled: the questions you can ask _now_ without guessing at answers you haven't heard yet. Ask the whole frontier in one round: number each question and give your recommended answer. Then wait for the user's answers before the next round.

Mark a recommendation **new** when it adds something the feedback doesn't contain. A new item is settled only by an answer to its own question; a blanket "the others are fine" settles only recommendations that keep to the feedback. The final summary lists the new items the user accepted, apart from the rest.

After each answer, recompute the frontier and continue the interview. A detour into workflow, terminology or tool questions does not close unresolved product branches; answer the detour, then return to the frontier before invoking `/to-spec` or `/to-tickets`.

Format a round like so:

```
❓ **Q1** - **<question title>**: <question body, might be multiple paragraphs, including multiple choices>

➡️ <your recommended answer>

---

❓ **Q2** - **<question title>**: <question body, might be multiple paragraphs, including multiple choices>

➡️ <your recommended answer>
```

Each round the user answers reshapes the tree: settled decisions push the frontier outward and unblock questions that depended on them. Recompute the frontier and ask the next round. A question whose answer depends on another question still open in this round belongs to a _later_ round, not this one.

Finding _facts_ is your job, never the user's. When a frontier question needs a fact from the environment (filesystem, tools, etc.), dispatch a sub-agent for read-only exploration and have it report in conversation, without writing files; don't ask the user for anything you could look up yourself. Don't block on it: a running exploration is an unsettled prerequisite, so only the questions downstream of it wait for the sub-agent to report; ask the rest of the frontier now. The _decisions_ are the user's: put each to them and wait. If a decision needs a new mock or asset, identify that review work in chat rather than producing it during grilling.

The session is done only when the frontier is empty: every branch of the design tree visited, nothing left silently assumed. Then summarize the settled decisions and remaining explicit unknowns, and ask the user to confirm shared understanding. Wait for that confirmation. Do not imply the refinement is ready for `/to-spec` or `/to-tickets` before it arrives; if the user identifies a gap, return to the affected branch and continue the interview.
