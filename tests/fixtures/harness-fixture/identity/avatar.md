# Avatar

TestBot's avatar is the chat-force test suite itself. Its "ICP" is any
pytest invocation that loads this fixture harness.

## Demographics

- Runs inside a Python process under `uv run --python 3.13`
- Reads this file via `HarnessLoader.load()`
- Discards it immediately after assertions complete

## Motivations

- Green tests
- Fast tests
- No flakes

## Frustrations

- Missing fixture files
- Harness validation errors that don't name the offending path
- Real customer content leaking into the engine repo
