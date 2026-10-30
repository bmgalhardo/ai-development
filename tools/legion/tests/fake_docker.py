"""A fake `docker` for the runner's container tests, installed on PATH.

It records each call in the file FAKE_DOCKER_LOG names, with the variables it was asked to pass in.
`run` runs the session's command on the host (everything after `-w <folder> <image>`);
`ps` lists one leftover container, `image inspect` finds no image, and every other command succeeds.
"""

import json
import os
import pathlib
import sys

args = sys.argv[1:]
passed = {args[i + 1]: os.environ.get(args[i + 1]) for i, arg in enumerate(args) if arg == "-e"}
with pathlib.Path(os.environ["FAKE_DOCKER_LOG"]).open("a") as out:
    out.write(json.dumps({"args": args, "environment": passed}) + "\n")
if args[0] == "run":
    command = args[args.index("-w") + 3:]
    os.execvp(command[0], command)
if args[0] == "ps":
    print("leftover")
if args[:2] == ["image", "inspect"]:
    sys.exit(1)
