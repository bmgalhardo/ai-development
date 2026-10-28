# Setting up a project repo

What a project provides so the cycle in `workflow.md` runs on it: the
contract between the workflow and the project. Each project is an
independent git repo beside this one (`../<project>/`): no symlinks to
this repo and no mention of it. A session here works on a project once the
user names it (`AGENTS.md`).

`/new-project` sets a repo up, or adopts an existing one;
`python3 tools/project/check_contract.py ../<project>` checks it. The
workflow names each item below and the project says how. Only what is
true of the project goes in its files: the machine's tools and how to
publish are the workflow's (`engineering.md`, `machine.local.md`, `publish-server.md`).

## Required

- **What it is:** `AGENTS.md`, with `CLAUDE.md` as a symlink to it. What
  the project is, its standing rules, and pointers to its docs and
  `.agents/context/` files. Its cycles are kept outside the repo; it says
  so without naming where. Short: mostly navigation pointers. Every
  session reads it first.
- **Domain:** `.agents/context/domain.md` says where the domain model
  lives (the docs, the glossary) and where decisions go.
  `.agents/context/decisions.md` is the iteration log of what the user
  asked for, liked and rejected, newest first.
  `.agents/context/status.md` says what's built, agreed and next. Read by
  grilling, the spec and every issue.
- **Engineering:** `.agents/context/engineering.md`, with these parts:
  - **Check command:** the fast check every issue runs and must pass.
  - **Code map, tests and seams:** where the code is, the test suites, and
    the seams tests drive. Read by the spec, implementation and `/tdd`.
  - **Evidence:** how a build shows what changed: for an app, screenshots
    copied to `docs/img/`; for a library, an example run's output or
    timings. The build gathers it into the review.
  - Its toolchain and gotchas.
- **Review page:** `docs/review.md`, the current build's review, written
  by the build issue and read by the next review. `docs/README.md` says
  what's where in `docs/`.

## Optional

- **Slow checks:** in the engineering doc, checks too slow for every
  issue (an export, a long simulation). The build runs them.
- **Outputs:** `.agents/context/publishing.md` lists what the project
  deploys and their prepared folders, as a table whose rows start
  `| <output> | \`<folder>/\``: any name, such as `app`, `docs` or
  `examples`, each served at `<project>/<output>/`. The engineering doc
  says how to prepare each. The build prepares them and the worker loop
  publishes them. Without this doc nothing of the project is deployed.
  The review's mocks are published from outside the project; don't list
  them.
- **Docs site:** `mkdocs.yml` builds `docs/` with MkDocs and the Material
  theme into a prepared folder (the `docs` output). It names the site,
  sets `site_dir`, lists every doc in `nav` with `review.md` second, and
  turns on `validation` (omitted files, links, anchors) as warnings. The
  check command builds it with `uvx --from mkdocs==1.6.1 --with
  mkdocs-material==9.7.7 mkdocs build --strict`, so a broken link or a doc
  missing from the nav fails the check.
- **Direction:** `docs/direction/` holds what a review agrees beyond a
  cycle, brought in by an issue from the cycle's `direction/`: references, research, a visual style and type (direction, not built;
  `README.md` first, images in `img/`).
- **Coding standards:** `CODING_STANDARDS.md`, how the project's code is
  written, with its stack's idioms. Read by the code review; without it the
  review keeps to its generic smell baseline and says so.
- **Build folder:** a project that builds keeps its prepared files in an
  ignored folder (for example `artifacts/`, in `.gitignore`).
