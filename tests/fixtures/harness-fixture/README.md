# Test Fixture Harness

Minimal valid harness used by the chat-force test suite. Loaded via
`HarnessLoader.load()` by the `harness_fixture` pytest fixture in
`tests/conftest.py`.

Do not edit individual files here without also updating the tests that
depend on them. The fixture is intentionally minimal:

- `workspace.yaml` uses the slug `testbot` and references the fake env vars
  `TESTBOT_SLACK_BOT_TOKEN` and `TESTBOT_SLACK_APP_TOKEN`, which the
  session-scoped pytest fixture sets before any harness load.
- `identity/` files contain placeholder prose. Tests assert on the bot's
  display name (`TestBot`), never on identity file content.
- `eval/criteria.yaml` has a one-line narrative and an empty checks list.
- `skills/` and `mechanic-log/` start empty (`.gitkeep` only).
- `vault/` has the required directory skeleton; content files are stubs.

If you need a harness with richer content (real eval checks, realistic
identity), build it in your test's `tmp_path` rather than editing this
fixture.
