# The publish server

Outputs are published to a publish server, the same route for Claude and
Codex. A server is optional: without one, nothing is published and the
user reads the review in the project's repo and the mocks in `.scratch/`.

The server is any web server that accepts WebDAV `PUT`, `DELETE` and
`MOVE` and serves the same files back. Its URL is `PUBLISH_URL`, set in
the environment or in this repo's `.env` (not in git):

```
PUBLISH_URL=https://<your server>
```

It keeps only the latest build of each output. Everything it serves can
be rebuilt from the project's repo and this repo's `.scratch/`.

```
/                    the menu of projects
/<project>/             the project's menu: each output, then Mocks
/<project>/<output>/    e.g. app/, docs/        /<project>/mocks/
```

Publish with:

```bash
python3 tools/publish/publish.py ../<project>          # the build's outputs
python3 tools/publish/publish.py ../<project> mocks    # the review's mocks
```

- The worker loop runs the first when the build is done; the review runs
  the second. Each changes only what it names on the server.
- The build's outputs and their prepared folders come from the project's
  `.agents/context/publishing.md`: every row naming an output and its
  folder. A project without that doc has none.
- The docs carry the current review (`docs/review.md`).
- The mocks are the current cycle's `mocks/` (`.scratch/<project>/<cycle>/`),
  newest first.
- With nothing to publish it says so and never contacts the server.
- Without `PUBLISH_URL`, the worker loop skips publishing; the script
  stops with a message.
- A build output the project no longer has is removed from the server.
- It uploads each output to a staging folder and then moves it into
  place, so the previous build stays up until the new one is complete.
- It rebuilds both menus and prints each link. Return those links.
- Prepare each output first (the project's engineering doc says how). The
  script stops if an output's `index.html` is missing.
- A failed upload stops the script with the HTTP error. Report it as the
  blocker; local files alone are not a publication.
