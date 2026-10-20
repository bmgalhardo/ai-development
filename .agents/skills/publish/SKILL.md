---
name: publish
description: "Publish the cycle's build (the game, and the docs page if the project has one) after the workers finished."
disable-model-invocation: true
---

Publish the latest cycle's build as the automatic final step after the
workers (`tools/work.sh`) prepare it, for the game the build issue's `Repo:` names. The host session selects the route
from the active app using the game's `AGENTS.md` (ChatGPT Sites or Claude Artifacts),
independent of whether Codex or Claude wrote the code. If the last issue
worker has the required native publishing tools, it may publish directly;
otherwise the host session runs this skill immediately when the worker
loop exits. Never wait for the user to type `/publish` or ask the user
anything.

1. **Check it's ready.** `python3 tools/next_issue.py ../<game> --status`: every issue is `done` or `blocked`, and the build issue is `done`. If not, say which issue is left and stop.
2. **Publish each output.** The game's publishing doc lists the outputs (the game, usually a docs page), the prepared files for each and their destinations. Publish each one using the selected publishing instructions, reusing its destination. A docs page is a view of the Markdown.
3. **Verify and report.** Verify success and return each output's link, what was built, every blocked issue with why, and the open questions from `review.md`. Keep it short. Local files alone do not count as publication; report any actual publishing blocker.
