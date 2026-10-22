---
name: implement
description: "Implement one issue from the issue tracker, without the user."
disable-model-invocation: true
---

Implement one issue, without the user. The issue tracker should have been provided to you. You run in the workflow repo; the issue's `Repo:` line names the game's repo, and all its work happens there: read the game's `AGENTS.md` and context first, and run code, checks and every git command in that repo (`git -C <repo>`). Paths in the game's files are relative to its root. Never ask the user anything and never wait for input: a doubt becomes a note in the issue. Work only on your issue: never edit another issue's file.

1. **Pick the issue.** The one you were given; if none, `python3 tools/next_issue.py ../<game>` (the session's game's first ready issue). If none is ready, say so and stop. If an issue is `in progress` (a worker died on it), take that one and resume it. Read its uncommitted changes (`git -C <repo> diff`, `git -C <repo> status`) for anything to reuse, then discard them (`git -C <repo> reset --hard HEAD`, then `git -C <repo> clean -fd`, which keeps ignored files such as `.scratch/`). Keep the commits past its `Base:` and run the checks. If they pass, check those commits against the issue and continue from the first step not done (often the review, step 10). If they fail, reset to `Base:` (`git -C <repo> reset --hard <Base>`) and start again. Read the issue, then only the spec sections and mock parts it names (line ranges or element ids, with `sed -n` or `grep`), not whole files. Read further only to answer a question the issue leaves. State the issue's title.
2. **Claim it.** Set the status to `in progress` and write `**Base:** <the repo's HEAD sha>` under the Status line (keep an existing Base when restarting).
3. **Build from the issue, the spec and its mock.** The mock is the agreed design: match it. Where the mock and the general docs disagree (a font, a colour, a size), the mock wins, and the docs you write say what you built. Assets were made and agreed in the review: bring in the ones the issue names from `.scratch/<game>/exploration/cycle/assets/` (into `assets/`, their scripts into `tools/`); don't make or restyle an asset.
   - In the same commit as the code, write the doc text the issue's `Docs to write` gives, into the files it names. A new doc file goes into the docs index.
   - Never write ahead of the build, and never mark anything "(agreed, not built)". The domain doc names the exceptions.
4. **Use /tdd where it applies,** at the seams the spec agreed: logic test-first, look and feel checked with the captures.
5. **Run the checks.** "Typechecking" and "tests" mean the project's check command and single test files (the engineering doc). Run single test files regularly and the full suite once at the end; it must pass.
6. **Make the small choices yourself,** within the mock, the docs and the standing rules. Note each one under `## Comments` in the issue, so the review lists it.
7. **Don't decide what would change agreed design.** Only something the spec and the mock don't cover becomes a question. Take the safest reading, build it, and note it under `## Comments` as `Open question:`.
8. **If it can't go green,** revert your commits (`git -C <repo> revert --no-edit <Base>..HEAD`), set the status to `blocked`, write why under `## Comments`, and stop.
9. **Commit** your work in the issue's repo, on its current branch (stage files explicitly). Never commit in the workflow repo.
10. **Review once.** Run `/code-review <Base>` for this issue. Handle each finding once:
    - Fix spec gaps and broken rules (`AGENTS.md`, the coding standards).
    - Fix a smell only if it's cheap; otherwise write a `Review:` note saying why not.
    - Drop a finding that would change the mock's design, with a `Review:` note.
    - A finding never becomes a new open question.

    Re-run the checks and commit. Never run a second review.
11. **Close:** tick each acceptance box you met; for a box you didn't meet, write why under `## Comments`. Set the status to `done` and stop. Report the commits, the checks, your choices and open questions.
