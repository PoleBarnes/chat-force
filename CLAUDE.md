# Project Rules

## Bug Fix Regression Tests (Mandatory)

Every bug fix MUST include a corresponding regression test in `tests/test_pipeline.py` before the fix is considered complete. The test must:

1. Reproduce the exact failure scenario that was found
2. Fail without the fix applied (conceptually — verify the test targets the right code path)
3. Pass with the fix applied
4. Be named descriptively: `test_<component>_<bug_description>`

No bug fix PR or commit is complete without its regression test. This is non-negotiable.

## Testing

- Run tests with: `uv run --python 3.13 --with docker,"slack_sdk>=3.41.0","slack_bolt>=1.27.0",pytest pytest tests/test_pipeline.py`
- All tests must pass before committing
- CI runs on every push (GitHub Actions)

## Architecture

- Act as orchestrator — delegate work to specialized agents
- Root cause all issues — no hacks, no shortcuts
- Use Codex CLI for code reviews alongside Claude agents
- Every code change gets a full team review (architect + Codex) before shipping
