---
name: publish
description: "Publish the cycle's build (the game, the docs page with its review, and the mocks) to the games server after the workers finished."
disable-model-invocation: true
---

Publish the latest cycle's build as the automatic final step after the
workers (`tools/work.sh`) prepare it, for the game the build issue's `Repo:` names. Claude and Codex publish the same way (`.agents/context/games-server.md`). Never wait for the user to type `/publish` or ask the user
anything.

1. **Check it's ready.** `python3 tools/workers/next_issue.py ../<game> --status`: every issue is `done` or `blocked`, and the build issue is `done`. If not, say which issue is left and stop.
2. **Publish.** `python3 tools/publish/publish.py ../<game>`. It uploads each output the game's publishing doc lists, and the mocks. If it stops on a missing output, prepare it (the game's engineering doc) and run it again.
3. **Report.** Return the links it printed, what was built, every blocked issue with why, and the open questions from the game's `docs/review.md`. Keep it short. Report any upload error as the blocker; local files alone are not a publication.
