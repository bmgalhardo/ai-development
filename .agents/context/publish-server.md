# The publish server

Every output is published to the publish server,
https://projects.bgalhardo.internal: the same route for Claude and Codex.
It is on the LAN and the VPN only, and it has no auth. It keeps only the
latest build of each output. Everything it serves can be rebuilt from the
project's repo and this repo's `.scratch/`.

```
/                    the menu of projects
/<project>/             the project's menu: Game, Docs, Mocks
/<project>/game/        /<project>/docs/        /<project>/mocks/
```

Publish with:

```bash
python3 tools/publish/publish.py ../<project>          # the build's outputs
python3 tools/publish/publish.py ../<project> mocks    # the review's mocks
```

- The worker loop runs the first when the build is done; the review runs
  the second. Each changes only what it names on the server.
- The build's outputs and their prepared folders come from the project's
  `.agents/context/publishing.md` (the `game` and `docs` rows). A project
  without that doc has none.
- The docs carry the current review (`docs/review.md`).
- The mocks are the current cycle's `mocks/` (`.scratch/<project>/<cycle>/`),
  newest first.
- With nothing to publish it says so and never contacts the server.
- A build output the project no longer has is removed from the server.
- It uploads each output to a staging folder and then moves it into
  place, so the previous build stays up until the new one is complete.
- It rebuilds both menus and prints each link. Return those links.
- Prepare each output first (the project's engineering doc says how). The
  script stops if an output's `index.html` is missing.
- A failed upload stops the script with the HTTP error. Report it as the
  blocker; local files alone are not a publication.

The server is a WebDAV nginx in the homelab's k8s cluster (`publish` in the
`system` namespace). `PUBLISH_URL` points the script at another server.
