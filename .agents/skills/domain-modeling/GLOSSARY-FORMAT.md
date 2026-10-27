# Glossary format

## Structure

```md
## Terms

**Batch**:
One source file's rows, ingested together and accepted or rejected as a whole.
_Avoid_: job, load, import

**Rejection**:
A row the pipeline refuses, with its line and reason; the rest of the batch goes on.
_Avoid_: error, failure
```

## Rules

- **Be opinionated.** When multiple words exist for the same concept, pick the best one and list the others under `_Avoid_`.
- **Keep definitions tight.** One or two sentences max. Define what it IS, not what it does.
- **Only include terms specific to this project.** General programming or domain words everyone knows don't belong. Before adding a term, ask: is this a concept unique to this project, or one any reader already knows? Only the former belongs.
- **Group terms under subheadings** when natural clusters emerge. If all terms belong to a single cohesive area, a flat list is fine.
- **Write for the user.** The glossary sits in their docs: plain, short, true to the project.
