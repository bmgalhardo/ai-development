---
name: publish
description: "Publish the cycle's build (its outputs, such as the game and the docs page with its review) to the games server by hand, when the worker loop's own publication failed or was skipped."
disable-model-invocation: true
---

Publish the latest cycle's build by hand, for the project the build issue's `Repo:` names. The worker loop publishes it on its own when the build is done; use this when that failed, was skipped (`WORK_PUBLISH=0`), or after a fix. Claude and Codex publish the same way (`.agents/context/games-server.md`).

1. **Check it's ready.** `python3 tools/workers/next_issue.py ../<project> --status`: the build issue is `done`. If not, say which issues are left and stop.
2. **Publish.** `python3 tools/publish/publish.py ../<project>`. It uploads each output the project's publishing doc lists; a project without one has nothing to publish. If it stops on a missing output, prepare it (the project's engineering doc) and run it again.
3. **Report.** Return the links it printed, what was built, every blocked issue with why, and the open questions from the project's `docs/review.md`. Keep it short. Report any upload error as the blocker; local files alone are not a publication.
