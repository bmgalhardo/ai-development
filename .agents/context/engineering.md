# Engineering defaults

What every session here does, whatever the project. A project's
`.agents/context/engineering.md` adds its own stack and wins where the two
differ. This machine's own tools and gotchas (paths, a display, what's
installed) are in `.agents/context/machine.local.md`, not in git: read it
if it exists.

## Python tooling

- Use uv. A project's `tools/` may be a uv project: `uv sync --project
  tools` once, then `uv run --project tools python tools/<script>.py`.
- If a venv's Python fails to start ("No module named 'encodings'", after a
  Python upgrade), run `uv sync --project tools` again.

## Shell

- Run a long command (a check, a test suite) in its own Bash call, with a
  `timeout` above its run time, up to 600000. With Bash's default 2-minute
  timeout, it is moved to the background and its output goes to a file.
- Don't chain an edit with a long command.
- Don't wait with `sleep`: a chained `sleep` is blocked. Use
  `run_in_background` only for a run longer than 10 minutes.
- Never `git stash` or check out another commit in the project's tree.
  To compare against an older commit, use a worktree (below).
- `pkill -f <pattern>` kills the shell itself if the pattern appears in
  the command line.
- Stop what you started before you finish: a display server, a local web
  server, a watcher. A headless session doesn't exit while one runs, and
  the worker loop waits for it.

## Keeping the context small

Everything a tool returns stays in the session's context, and every later
turn re-reads it.

- Read what you need: `grep -n` for the function, then `sed -n` its
  lines, not a whole file or a long range.
- Keep a long command's output short: write it to a file, then read its
  tail or its failures (`| tail -n 30`, `grep -n FAIL`).

## Worktrees

The Agent tool's `isolation: "worktree"` fails (`.claude` is a symlink).
Use `git -C ../<project> worktree add <scratchpad>/wt-<slug> -b <branch>`.
It has no ignored folders (such as `artifacts/`): link the project's in
and don't commit the link. Issues stay in this repo's `.scratch/<project>/`.
Merge the branch and `git worktree remove` it when done.

## Screenshots and display

- **Images:** the system Python has no PIL. Convert or read an image with
  `uv run --with pillow python …`.
- **No display** (no `DISPLAY`, `/tmp/.X11-unix` empty): run a private
  Xvfb without root. `apt-get download xvfb libunwind8 libxfont2
  libfontenc1 xkb-data x11-xkb-utils xserver-common libxkbfile1`, `dpkg -x`
  each into a scratch `root/`, then start it inside `unshare -r -m`,
  bind-mounting a copy of `/usr/bin` with `xkbcomp` added over `/usr/bin`
  (Xvfb only looks for `/usr/bin/xkbcomp`), with
  `LD_LIBRARY_PATH=root/usr/lib/x86_64-linux-gnu` and `Xvfb :<n> -screen 0
  1280x1024x24 +extension GLX -xkbdir root/usr/share/X11/xkb`. Then
  `DISPLAY=:<n>`. Mesa's software GL is enough for OpenGL captures. Start
  it in the background; background commands are killed at their time
  limit, so start it again if it's gone, and stop it before you finish.
- **Web pages without a browser:** screenshot a page in Playwright's
  headless Chromium: `uv venv ~/.cache/pw-venv`, `uv pip install -p
  ~/.cache/pw-venv/bin/python playwright`, then
  `~/.cache/pw-venv/bin/python -m playwright install
  chromium-headless-shell`.
