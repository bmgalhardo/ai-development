---
name: implement
description: "Implement one issue from the issue tracker, without the user."
disable-model-invocation: true
---

Implement one issue, without the user. The issue tracker should have been provided to you. You run in the workflow repo; the issue's `Repo:` line names the project's repo, and all its work happens there: read the project's `AGENTS.md` and context first, and this repo's `.agents/context/engineering.md`, and run code, checks and every git command in that repo (`git -C <repo>`). Paths in the project's files are relative to its root. Never ask the user anything and never wait for input: a doubt becomes a note in the issue. Work only on your issue: never edit another issue's file.

1. **Pick the issue.** The one you were given; if none, `tools/legion.sh next ../<project>` (the session's project's first ready issue). If none is ready, say so and stop. If an issue is `in review`, it is implemented: follow the Fix session below, with its reviews in the cycle's `reviews/` (run `/code-review <Base>` first if they are missing). If an issue is `in progress`, resume it. Read its `## Progress`, commits past `Base:`, staged and unstaged diffs, and untracked files. Keep unfinished work and commits even when checks fail; diagnose and repair them. Never reset to `Base:` or clean the repo to restart an interrupted attempt. Keep the existing `Base:` for the final review. Read the issue, then only the spec sections and mock parts it names (line ranges or element ids, with `sed -n` or `grep`), not whole files. Read further only to answer a question the issue leaves. State the issue's title.
2. **Claim it.** Set the status to `in progress` and write `**Base:** <the repo's HEAD sha>` under the Status line (keep an existing Base when restarting).
   - Read the cycle's `debt.md` if it exists, focusing on entries for the modules this issue touches. A small behaviour-preserving prefactor may go in its own commit before the feature. Leave wider refactors open for refinement; do not expand the issue's scope to clear the register.
3. **Build from the issue, the spec and its mock.** The mock is the agreed design: match it. Where the mock and the general docs disagree (a font, a colour, a size), the mock wins, and the docs you write say what you built. Assets were made and agreed in the review: bring in the ones the issue names from the cycle's `assets/` (into `assets/`, their scripts into `tools/`); don't make or restyle an asset. Copy the direction pages the issue names from the cycle's `direction/` into `docs/direction/` and its nav.
   - In the same commit as the code, write the doc text the issue's `Docs to write` gives, into the files it names. A new doc file goes into the docs index.
   - Never write ahead of the build, and never mark anything "(agreed, not built)". The domain doc names the exceptions.
4. **Use /tdd where it applies,** at the seams the spec agreed: logic test-first, look and feel checked with the project's evidence (for a UI, its screenshots).
5. **Run the checks.** "Typechecking" and "tests" mean the project's check command and single test files (the engineering doc). Run single test files regularly and the full suite once at the end; it must pass.
6. **Make the small choices yourself,** within the mock, the docs and the standing rules. Note each one under `## Comments` in the issue, so the review lists it.
7. **Don't decide what would change agreed design.** Only something the spec and the mock don't cover becomes a question. Take the safest reading, build it, and note it under `## Comments` as `Open question:`.
8. **If interrupted by quota or authentication,** leave the issue `in progress` and preserve all work. Update `## Progress` if possible. Do not revert or mark it blocked for an infrastructure interruption.
   **If the issue's `Stop if` condition is met,** finish to green what you built, commit it and keep it. Set the status to `blocked`, write under `## Comments` what met the condition and its evidence, and stop. Don't work around the condition.
   **If implementation cannot go green after diagnosis,** revert your commits (`git -C <repo> revert --no-edit <Base>..HEAD`), set the status to `blocked`, write why under `## Comments`, and stop.
9. **Commit** your work in the issue's repo, on its current branch (stage files explicitly). Never commit in the workflow repo.
   - **Review handoff:** when told separate review sessions follow, stop here. Update `## Progress` with the commit and checks, set the status to `in review`, and report the commits, the checks, your choices and open questions. Skip steps 10 and 11.
10. **Review once.** Run `/code-review <Base>` for this issue. Handle each finding once:
    - Fix spec gaps and broken rules (`AGENTS.md`, the coding standards).
    - Fix a smell only if it's cheap; otherwise write a `Review:` note saying why not and add an open entry to the cycle's `debt.md`. Name the affected files, the suggested change, the source issue, and the disposition (`open`, `assigned: <issue>`, `resolved: <commit>`, or `accepted: <reason>`). Reuse an existing entry for the same finding.
    - Record newly oversized scripts and significant growth of already oversized scripts in `debt.md`. The standards' approximate sizes are warnings, not automatic refactor requirements.
    - Mark entries resolved only when the change is implemented and checked.
    - Drop a finding that would change the mock's design, with a `Review:` note.
    - A finding never becomes a new open question.

    Re-run the checks and commit. Do not review those fixes again.
11. **Close:** tick each acceptance box you met. Mark each `debt.md` entry assigned to this issue that the issue's commits resolved `resolved`, with its commit. If every box is ticked, set the status to `done`. Otherwise set it to `blocked`, and write one `Needs the user:` line under `## Comments` for each unmet box, saying what it needs. Stop and report the commits, the checks, your choices and open questions.

## Fix session

When given an issue `in review` with its saved reviews, other sessions implemented and reviewed it.
You handle the findings and close it. Do not run `/code-review` again.

1. Read the project's `AGENTS.md` and context, this repo's `.agents/context/engineering.md`, the issue, its `## Progress` and `## Comments`, and both reviews. Keep the status `in review` and keep `Base:`.
2. Read the code, spec sections and mock parts only as a finding needs them.
3. Handle each finding with step 10's rules. Fix only what the findings call for; don't extend the implementation.
4. If a fix can't go green, revert that fix, record the finding in `debt.md` with a `Review:` note, and go on. Never revert the implementer's commits.
5. Re-run the checks, commit, then close the issue with step 11. Report what you fixed and what you deferred.

If interrupted, leave the issue `in review` and record the findings handled so far in `## Progress`.

## Recovery progress

Update `## Progress` in your issue after the implementation commit, when the review returns, and after review fixes.
Record the completed step, commit SHA, checks and their result, saved review findings, and remaining work.
Record which commit a completed review examined.
On restart, reuse that review only if the implementation has not changed since that commit, apart from its recorded review fixes.
Preserve completed findings if another review is needed for changed implementation.
Keep this section short and current; keep historical explanations in Comments.
Edit `## Progress` in place with the Edit tool. Never append a second `## Progress`.
