---
name: pr-creation
description: Create well-structured pull requests with clear descriptions and testing instructions
triggers:
  - create PR
  - open PR
  - submit PR
enabled_by_default: true
category: engineering
---

# PR Creation

You are creating a pull request. Your job is to produce a well-structured PR that clearly communicates what changed, why, and how to verify it.

---

## Before Creating the PR

### Pre-flight Checks

1. **Branch hygiene**: Confirm you're on a feature branch (never main/master)
2. **Diff review**: Review all changes that will be included (`git diff main...HEAD`)
3. **Commit history**: Ensure commits follow conventional commit format
4. **No secrets**: Verify no credentials, API keys, or tokens are in the diff
5. **No debug code**: Remove console.log, print statements, TODO hacks
6. **Tests pass**: Run the test suite if one exists

### Commit Cleanup

If the branch has messy commits, consider whether to squash or keep them:
- **Keep separate commits** when each represents a logical unit of work
- **Squash** when there are WIP commits, "fix typo" commits, or back-and-forth changes
- Always use conventional commit format for the final commits

---

## PR Structure

### Title
- Short (under 70 chars)
- Use conventional commit prefix: `feat:`, `fix:`, `docs:`, `refactor:`, `chore:`, etc.
- Describe the outcome, not the activity
- Good: `feat: add campaign research skill for Leo`
- Bad: `Updated some files and added stuff`

### Description Template

```markdown
## Summary

[1-3 sentences: What does this PR do and why?]

## Changes

- [Bulleted list of what changed]
- [Group by area if touching multiple systems]
- [Mention files added/removed/renamed]

## Context

[Link to issue, design doc, or conversation that motivated this]
[Any background needed to understand the change]

## Testing

- [ ] [How to verify this works]
- [ ] [Specific scenarios to test]
- [ ] [Edge cases to check]

## Screenshots

[If visual changes, include before/after screenshots]

## Notes for Reviewer

[Anything the reviewer should pay special attention to]
[Known limitations or follow-up work planned]
```

---

## Writing the Summary

The summary is the most important part. It should answer:
1. **What** changed? (the technical change)
2. **Why** did it change? (the motivation)
3. **How** does it affect users/systems? (the impact)

### Good Summaries
- "Add campaign research skill that guides Leo through iterative market research, competitor analysis, and concept development. This is the first marketing skill in the platform skills framework."
- "Fix race condition in message handler where concurrent Slack events could trigger duplicate campaign workflows. Adds a deduplication check using message timestamp."

### Bad Summaries
- "Various updates"
- "Fixed the thing"
- "Addresses feedback from last review"

---

## Change Categories

Tag the PR appropriately based on the type of changes:

### Feature (`feat:`)
- Describe the user-facing capability
- List any new configuration required
- Note any migrations or setup steps

### Bug Fix (`fix:`)
- Describe the bug (what was happening)
- Describe the root cause
- Describe the fix
- Include steps to reproduce if applicable

### Refactor (`refactor:`)
- Explain why the refactor is needed
- Confirm behavior is unchanged
- Note any risks

### Infrastructure (`chore:` / `ci:`)
- Describe the infrastructure change
- Note any deployment steps required
- Flag any breaking changes to workflows

---

## Labeling and Metadata

If the repository supports labels:
- Add size label (S/M/L/XL based on diff size)
- Add type label (feature, bug, refactor, docs)
- Add area label if applicable (marketing, infra, skills)
- Link to issues being addressed
- Assign reviewers

---

## Draft vs Ready

- **Draft**: Use when the PR is not ready for review but you want to share progress or get early feedback. Prefix title with `[WIP]` or use GitHub draft PR feature.
- **Ready**: Only mark ready for review when all pre-flight checks pass and the PR is complete.

---

## Principles

- **The PR description is documentation.** Future engineers will read it to understand why a change was made. Write for them.
- **Smaller is better.** PRs under 400 lines get reviewed faster and more thoroughly. Split large changes into a stack of smaller PRs when possible.
- **One concern per PR.** Don't mix a bug fix with a refactor with a feature. Each PR should have a single purpose.
- **Screenshots are worth 1000 words.** For any visual change, include before/after screenshots.
- **Link everything.** Issues, design docs, Slack conversations, related PRs. Context makes review faster.
