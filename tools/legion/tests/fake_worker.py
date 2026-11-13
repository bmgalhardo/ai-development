"""A fake provider CLI for the runner's tests, installed as `claude` and `codex` on PATH.

It records each call in `calls.jsonl` in the workflow root (its working folder),
and acts on the issue named in the prompt as TEST_SCENARIO says.
"""

import json
import os
import pathlib
import re
import sys
import time

provider = pathlib.Path(sys.argv[0]).name
root = pathlib.Path.cwd()
with (root / "calls.jsonl").open("a") as out:
    out.write(json.dumps({"provider": provider, "args": sys.argv[1:]}) + "\n")
prompt = sys.argv[-1]
issue = root / re.search(r"(\S+/issues/\S+?\.md)", prompt)[1]
scenario = os.environ.get("TEST_SCENARIO", "quota")
project = root / "project"


def set_status(old, new):
    issue.write_text(issue.read_text().replace(f"Status:** {old}", f"Status:** {new}"))


def report(text):
    if provider == "codex":
        print(json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": text}}))
    else:
        print(json.dumps({"type": "result", "result": text}))


def fail(text, **claude_fields):
    """A failed session, in the provider's own log format."""
    if provider == "codex":
        print(json.dumps({"type": "error", "message": text}))
        print(json.dumps({"type": "turn.failed", "error": {"message": text}}))
    else:
        print(json.dumps({"type": "result", "is_error": True, "result": text, **claude_fields}))
    sys.exit(1)


def leave_unfinished_work():
    set_status("open", "in progress")
    (project / "code.txt").write_text("unfinished tracked work\n")
    (project / "new.txt").write_text("unfinished untracked work\n")


if scenario in ("review", "review_quota"):
    if "axis only" in prompt:
        if scenario == "review_quota" and provider == "codex":
            fail("usage_limit_reached")
        report(f"## {re.search(r'the (\w+) axis', prompt)[1]}\nNo findings by {provider}.")
    elif "Fix session" in prompt:
        assert all((root / review).exists() for review in re.findall(r"(\S+/reviews/\S+?\.md)", prompt))
        set_status("in review", "done")
    else:
        set_status("open", "in review")
    sys.exit(0)
if scenario == "blocked":
    set_status("open", "blocked")
    issue.write_text(issue.read_text() + "\n## Comments\n\nNeeds the user: pick the boss's enrage time\n")
    sys.exit(0)
if scenario == "hang":
    if provider == "claude":
        set_status("open", "done")
    time.sleep(30)
if scenario == "auth_both" or (scenario == "auth" and provider == "claude"):
    leave_unfinished_work()
    fail("Failed to authenticate: OAuth session expired and could not be refreshed")
if scenario == "failure":
    print("Implementation check failed")
    sys.exit(1)
if provider == "claude" or scenario == "both_quota":
    leave_unfinished_work()
    fail("You've hit your session limit · resets 11pm (UTC)", api_error="usage_limit_reached", api_error_status=429,
         usage={"input_tokens": 100, "cache_read_input_tokens": 500})
assert (project / "new.txt").read_text() == "unfinished untracked work\n"
assert (project / "code.txt").read_text() == "unfinished tracked work\n"
set_status("in progress", "done")
print(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 25, "output_tokens": 5}}))
