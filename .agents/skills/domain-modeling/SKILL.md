---
name: domain-modeling
description: Build and sharpen a project's domain model. Use when discussing the project's terminology, writing or editing the glossary, or recording a settled decision in the domain docs.
---

# Domain Modeling

Actively build and sharpen the project's domain model as you design. This is the *active* discipline: challenging terms, inventing edge-case scenarios, and writing the glossary and decisions down the moment they crystallise. (Merely *reading* the glossary for vocabulary is not this skill: that's a one-line habit any skill can do. This skill is for when you're changing the model, not just consuming it.)

## Where the domain docs are

The domain doc should have been provided to you. It says which docs hold the project's domain model, where the glossary lives, and where settled decisions are written. Create the glossary lazily: only when the first term is resolved.

## During the session

When used during `grill-me`, this skill is conversational only: discuss
terms and decisions in chat, and skip all file-writing instructions below.
Review records feedback in `review.md`; `to-spec` later reads the live
conversation and publishes the spec. Outside grilling, follow the domain
context's rules for where and when to persist changes.

### Challenge against the glossary

When the user uses a term that conflicts with the existing language in the glossary, call it out immediately. "Your glossary defines 'cancellation' as X, but you seem to mean Y. Which is it?"

### Prefer the user's words

Before proposing a canonical term, look for the user's own word in the review's Feedback and the docs. If they already use one, it's the term.

### Sharpen fuzzy language

When the user uses vague or overloaded terms, propose a precise canonical term. "You're saying 'account': do you mean the Customer or the User? Those are different things."

### Discuss concrete scenarios

When domain relationships are being discussed, stress-test them with specific scenarios. Invent scenarios that probe edge cases and force the user to be precise about the boundaries between concepts.

### Cross-reference with code

When the user states how something works, check whether the code agrees. If you find a contradiction, surface it: "Your code cancels entire Orders, but you just said partial cancellation is possible. Which is right?"

### Update the glossary inline

When a term is resolved, update the glossary right there. Don't batch these up: capture them as they happen. Use the format in [GLOSSARY-FORMAT.md](./GLOSSARY-FORMAT.md).

The glossary should be totally devoid of implementation details. Do not treat the glossary as a spec, a scratch pad, or a repository for implementation decisions. It is a glossary and nothing else.

### Write decisions down as they settle

Outside grilling, write settled decisions where the domain doc says. In this repo, review feedback and accepted choices go only into `review.md` under Feedback. During `grill-me`, keep them in chat without writing anything. `to-spec` turns the live conversation into the tracker spec, naming the doc file each decision will change. The docs themselves describe only what's built, and the issue that builds a decision writes it into them.

Record the *why* sparingly: only when all three are true:

1. **Hard to reverse**: the cost of changing your mind later is meaningful
2. **Surprising without context**: a future reader will wonder "why did they do it this way?"
3. **The result of a real trade-off**: there were genuine alternatives and you picked one for specific reasons

Then note the rejected alternative and the reason in one or two sentences, where the domain doc says. If any of the three is missing, the decision alone is enough.
