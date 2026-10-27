---
name: new-project
description: "Set up a project repo beside this one so the workflow runs on it, or adopt an existing repo by adding what it lacks."
disable-model-invocation: true
---

Set up a project repo to the contract in `.agents/context/project-setup.md`. Read it first: it says what each file is for and who reads it. The project is `../<project>/`, an independent git repo that never names or links to this one.

1. **Find out what exists.** If `../<project>/` exists, this is an adoption: read its README, build files, tests and docs, and run `python3 tools/project/check_contract.py ../<project>` to see what's missing. Never overwrite or move an existing file; add only what's missing, and fill it from what the repo already says.
2. **Ask in one round.** Number the questions, give your recommended answer to each, and wait. Skip what an existing repo already answers.
   - The project's folder name, and in a sentence what it is.
   - Its stack and toolchain (language, versions, package manager).
   - The check command every issue runs, and slow checks for the build, if any.
   - Its evidence: how a build shows what changed (screenshots, an example run's output, timings).
   - Its outputs to deploy, if any (a docs site, an app, none), and their folders.
   - Its coding standards: write a short `CODING_STANDARDS.md` now from the stack's usual idioms, or none.
3. **Create the files.** `git init` a new repo. Write each file short, in plain sentences, true only of this project:
   - `AGENTS.md`: what it is, its standing rules (none yet is fine), and pointers to `docs/README.md` and each `.agents/context/` file. It says its cycles are kept outside the repo, without naming where. Then `ln -s AGENTS.md CLAUDE.md`.
   - `.agents/context/engineering.md`: the toolchain, the check command, slow checks, the code map (what exists so far), tests and seams, evidence, and how to prepare each output.
   - `.agents/context/domain.md`: the glossary is `docs/terms.md` (in the `domain-modeling` format) and decisions go in `decisions.md`.
   - `.agents/context/decisions.md`: the heading and today's entry, "project set up".
   - `.agents/context/status.md`: nothing built yet; next is the first review.
   - `.agents/context/publishing.md`, only with outputs: a table with one row per output, `| <output> | \`<folder>/\` |`.
   - `docs/README.md` (what's where), `docs/review.md` ("No build yet."), `docs/terms.md` (an empty `## Terms`).
   - `mkdocs.yml`, only for a docs site, as the contract describes; the check command builds it.
   - `CODING_STANDARDS.md`, if chosen; `.gitignore` for the build folder and the toolchain's caches.
4. **Check.** Run the check command once; it must pass on the empty project (a placeholder test is fine). Run `python3 tools/project/check_contract.py ../<project>` until it reports no errors, and resolve or report each warning.
5. **Commit** in the project's repo: `git -C ../<project> add -A` and one commit, "Set up the project". Create `.scratch/<project>/` here. Commit nothing in this repo.
6. **Hand off.** Report what was created, the check command's result, and the warnings left. The first cycle starts with a brainstorming review (`workflow.md`, step 1), in a new session.
