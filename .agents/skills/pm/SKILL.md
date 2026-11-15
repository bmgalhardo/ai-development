---
name: pm
description: Act as the project's PM when the user delegates refinement, spec writing and ticketing. Accept recommended answers and resolve blockers without an interview.
---

The current session acts as the PM for the named project and cycle.
Invoking this skill delegates the decisions and approvals normally requested by `grill-me`, `to-spec` and `to-tickets`.
Choose the recommended answers yourself and carry the work through to published tickets.
Run implementation and publication too when the user requests them.

## Establish the work

Read the project's `AGENTS.md` and its pointers.
Read this workflow's `workflow.md`, `issue-tracker.md` and engineering defaults in `.agents/context/`.
Use the live conversation, the cycle's feedback, the current review and the domain docs as inputs.
Read other open cycles to avoid duplicating their work.
Infer the project and cycle from the session when clear.
Ask only when they cannot be established from available context.

Read the sibling `grill-me`, `to-spec` and `to-tickets` skills directly.
Apply their design exploration, templates, testing, debt and dependency rules.
This skill replaces their requirements to interview the user, obtain confirmation, approve numbers or seams, and approve the ticket breakdown.
Do not invoke those skills through a tool that reserves them for direct user invocation.
Do not claim the user answered a question or approved a choice the PM made.

## Refine as the PM

Work through the design tree in prerequisite order.
For each open decision, choose the answer you would recommend to the user, then explore the questions it opens.
Look up facts rather than treating missing information as a product decision.
Preserve explicit user choices and the project's scope.
Prefer the smallest coherent solution that meets the user's goal.
Do not add optional features merely to close a question.

Stress-test the complete user journey from the default state, including continuation and recovery.
Check that acceptance examples can be constructed through the available commands.
Check that dependencies will be available in the worker's environment.
Resolve contradictions and missing decisions before publishing tickets.
Keep refinement in conversation until the decision frontier is empty.

If a needed mock or asset is missing, do the review work in the cycle's folder before returning to refinement.
Preserve existing user-approved mocks and assets.
Identify PM-selected variants as PM choices.

## Publish the spec and tickets

Apply `to-spec` to synthesize the completed refinement, without its confirmation pauses.
Record consequential PM choices in a `PM decisions` section of the spec.
Distinguish explicit user requirements from PM choices and tunable first guesses.
Perform the domain updates at spec publication as the project's domain context requires.

Apply `to-tickets` to publish the breakdown without its approval pause.
If ticketing reveals a gap, settle it as PM and update the spec before continuing.
Carry debt forward and keep acceptance criteria achievable within each ticket's blockers.
End with the build issue and validate the dependency graph with `tools/overmind.sh status ../<project>` and `next`.
Report the cycle path, ticket breakdown and consequential PM choices.

## Supervise implementation when requested

Read `.agents/context/workers.md` and `tools/overmind/README.md` before starting Overmind.
Run `tools/overmind.sh run ../<project>` using the host's supported long-running command handling.
Keep the current session as PM; workers still implement, review and fix individual issues.
Do not edit files an active worker owns.

When the loop stops, read its result and the affected issue's Progress, Comments, reviews and logs.
Resolve product blockers within the delegated scope yourself.
For a `Stop if`, examine its evidence and make an explicit PM decision before reopening the issue.
Record the decision and reason in Comments and update the spec, affected tickets and blockers together.
Never tick an unmet acceptance box or silently waive a failing check.
Preserve existing commits and unfinished work when resuming.

Fix available environment prerequisites within existing permissions, then resume the loop.
Use the project's publishing contract to recover a failed publication after the build is done.
Verify every configured output and return its link before reporting completion.
For a project with no publishing contract, report the completed build and checks.

If the same blocker returns after two attempted remedies without new evidence, stop retrying and report the precise blocker and preserved progress.
Ask the user only when resolution needs new scope, overrides an explicit user choice, or requires access or permission the session lacks.
Delegated PM decisions do not grant additional filesystem, infrastructure or account permissions.
