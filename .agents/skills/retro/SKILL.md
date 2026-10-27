---
name: retro
description: "Look back over a cycle (refinement, issues, build) and suggest improvements to the skills and the agent's environment."
disable-model-invocation: true
---

The user has asked for a **retrospective**. You are suggesting improvements to the **skills** and the coding agent's **environment** so the next cycle runs better. You suggest; the user picks; you change nothing until they do.

## Steps

1. **Gather the cycle.** Default to the session's project's latest cycle unless the user names another cycle. Read its spec, every issue (with its `## Comments`: the implementer's choices and open questions), its `feedback.md`, the project's `docs/review.md`, and the commits made for it in the project's repo (`git -C <repo> log` over the cycle's dates).

2. **Read the sessions.** A cycle spans several sessions: the refinement, then one per issue. Run `python3 .agents/skills/retro/digest.py --since <first day of the cycle>` for a compact digest of each one: the user's messages, the skills invoked, and the denied or failed tool calls. Read the full log of a session (its path is in the digest's header) only where the digest shows something worth a closer look. Logs are deleted after about 30 days, so a retro belongs soon after the build.

3. **Look for candidates** in these categories.

- **Skills**: did a skill do the wrong thing, miss a step, ask the user something it shouldn't (implementation runs without the user), or get worked around? Did the refinement leave a question that implementation then had to guess? Did a spec or issue lack what the implementer needed? _Use when_ the cycle's sessions show friction at a skill's step. The fix is an edit to that skill. Skills live in this workflow repo (`.agents/skills/`), shared by every project: say so when a change would affect the others, and commit it here.
- **Workflow**: was a step of the cycle missing, in the wrong order, or done twice? _Use when_ the cycle itself caused rework. The fix is an edit to `.agents/context/workflow.md`, or to the project's own context (committed in its repo) when only that project is affected.
- **Navigation**: how easy was it for the agent to find the right files? Are there hidden dependencies between files? Would a **navigation pointer** make it easier? _Use when_ a session took a long time to find a piece of information.
- **Automated checks**: are there checks that could catch errors the agent made? Read the project's own check command first, so a check that exists but is unwired or broken is the finding, not a reinvention. _Use when_ the agent made a mistake a check could have caught.
- **Coding standards**: should the **reviewer** (`code-review`) be given a new rule, or an existing rule removed or clarified? A **mechanical** violation (a fixed pattern, a banned API, a file-location rule) gets a deterministic check instead. Keep written standards for genuine **judgement calls**. _Use when_ the review failed to catch a mistake.
- **AGENTS.md**: should steering instructions move out to a skill, a doc or a check? _Use when_ `AGENTS.md` is getting large.
- **Tool economy**: did the agent make expensive tool calls that could be streamlined? _Use when_ the digest shows many repeated or failing calls.
- **No-ops**: instructions in steering files or skills that don't change the agent's behaviour. _Use when_ they've grown large.
- **Information access**: was a crucial piece of information unavailable to the agent? _Use when_ a session guessed or asked for something it could have read.

4. **Present the candidates** in order of severity. For each one: what happened (quote the user or the log, with the session and time), the change you suggest, and the file it would change. Then ask which to adopt, and make only those changes.

## Reference

### Implementation vs review

All work goes through two stages: implementation and review. The implementation agent has the most **context pressure**: it explores, writes code, and debugs failures. The review agent has the least: it receives a diff. So the reviewer, not the implementer, is the one to impose coding standards.

### Files

- `AGENTS.md` (and `CLAUDE.md`, a link to it), here and in each project: loaded into every agent's context. Use it sparingly, mostly for **navigation pointers** to other files.
- Skills (this repo's `.agents/skills/`): their descriptions are always in context, their bodies only when used. Keep each one to the steps of its stage; project details belong in the docs they point to.
- Docs: reference files, pointed to by other files. Look for an existing doc before writing a new one.
- The project's `CODING_STANDARDS.md`: read during review, not implementation.

### Writing for agents

Short, direct, and plain. Say what to do and when. One instruction per sentence; no rationale the agent doesn't need to act on.
