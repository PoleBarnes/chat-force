# Project Rules

## Test-Driven Development (Mandatory)

**Write the test FIRST, then fix the code.** This applies to all bug fixes and new features.

For bug fixes:
1. Write a test in `tests/test_pipeline.py` that reproduces the exact failure
2. Run the test — confirm it FAILS (proves the test catches the bug)
3. Fix the code
4. Run the test — confirm it PASSES
5. Name the test descriptively: `test_<component>_<bug_description>`

For new features:
1. Write tests that define the expected behavior
2. Run them — confirm they fail (feature doesn't exist yet)
3. Implement the feature
4. Run them — confirm they pass

No code change is complete without its test. This is non-negotiable.

## Testing

- Run tests with: `uv run --python 3.13 --with docker,"slack_sdk>=3.41.0","slack_bolt>=1.27.0",pytest pytest tests/test_pipeline.py`
- All tests must pass before committing
- CI runs on every push (GitHub Actions)

## Architecture

- Act as orchestrator — delegate work to specialized agents
- Root cause all issues — no hacks, no shortcuts
- Use Codex CLI for code reviews alongside Claude agents
- Every code change gets a full team review (architect + Codex) before shipping
