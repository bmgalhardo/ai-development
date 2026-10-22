---
name: to-spec
description: "Turn the live conversation into an implementation-ready spec and publish it to the configured project issue tracker. No design interview or prior draft required."
disable-model-invocation: true
---

This skill synthesizes the live conversation and codebase understanding into a spec and publishes it directly to the configured issue tracker. Review records feedback in `review.md`; `grill-me` is pure conversation and writes nothing. There is no persisted interview handoff or required draft. Do NOT run another design interview.

Use the live chat as the source of the interview's decisions and wording. Consult `review.md` for supporting context and references, not as a substitute for missing interview answers. Preserve agreed choices, remove superseded ones, and do not turn unresolved ideas into requirements. If the necessary conversation is unavailable or a decision remains unresolved, identify the missing context or refinement instead of claiming the spec is complete. A missing draft is normal.

Before consolidating, verify that `/grill-me` reached an empty frontier and the user explicitly confirmed shared understanding. If that handoff is absent, stop and return to `/grill-me`; do not publish an implementation-ready spec from a partial interview. If the user changes workflow or terminology during grilling, resume the product-decision frontier afterward.

The issue tracker should have been provided to you. Follow its publishing conventions; do not assume a local filename in the skill. The tracker is local Markdown in this repo's `.scratch/<game>/`, as defined in `.agents/context/issue-tracker.md`. The spec starts with a `**Repo:**` line naming the game's repo. If revising an already-published spec for this work, update that tracker entry using the live conversation.

## Process

1. Explore the game's repo to understand the current state of the codebase, if you haven't already. Use the project's domain glossary vocabulary throughout the spec, and respect the decisions in the domain docs in the area you're touching.

2. Sketch out the seams at which you're going to test the feature. Existing seams should be preferred to new ones. Use the highest seam possible. If new seams are needed, propose them at the highest point you can. The fewer seams across the codebase, the better - the ideal number is one.

Check with the user that these seams match their expectations.

3. Write the spec from the conversation using the template below, then publish it to the configured issue tracker. Keep every agreed choice and the agreed wording of each doc change in it (or attached supporting material), naming the doc file each goes into: the docs describe only what's built, so the issues copy their parts in as they build them. Never write design choices into the docs from here. Name the mock and the variant the user picked for every part with a look: the mock is the agreed design, and implementers and reviewers match it. Make agreed rules explicit for anything a worker can't ask about; flag missing decisions for refinement. Give every known performance risk a target number (for example, "the worst case under N s on desktop"), agreed with the user. Apply the domain context's glossary and decision-log updates at this publication step, never as a prerequisite handoff from grilling.

<spec-template>

## Problem Statement

The problem that the user is facing, from the user's perspective.

## Solution

The solution to the problem, from the user's perspective.

## User Stories

A LONG, numbered list of user stories. Each user story should be in the format of:

1. As an <actor>, I want a <feature>, so that <benefit>

<user-story-example>
1. As a mobile bank customer, I want to see balance on my accounts, so that I can make better informed decisions about my spending
</user-story-example>

This list of user stories should be extremely extensive and cover all aspects of the feature.

## Implementation Decisions

A list of implementation decisions that were made. This can include:

- The modules that will be built/modified
- The interfaces of those modules that will be modified
- Technical clarifications from the developer
- Architectural decisions
- Schema changes
- API contracts
- Specific interactions

Do NOT include specific file paths or code snippets. They may end up being outdated very quickly.

Exception: if a prototype produced a snippet that encodes a decision more precisely than prose can (state machine, reducer, schema, type shape), inline it within the relevant decision and note briefly that it came from a prototype. Trim to the decision-rich parts, not a working demo, just the important bits.

## Testing Decisions

A list of testing decisions that were made. Include:

- A description of what makes a good test (only test external behavior, not implementation details)
- Which modules will be tested
- Prior art for the tests (i.e. similar types of tests in the codebase)

## Out of Scope

A description of the things that are out of scope for this spec.

## Further Notes

Any further notes about the feature.

</spec-template>
