---
name: code-review
description: Analyze pull requests for correctness, security, performance, and readability
triggers:
  - review
  - code review
  - PR review
enabled_by_default: true
category: engineering
---

# Code Review

You are performing a code review. Your job is to provide actionable, specific feedback that makes the code better — not just "looks good" or vague suggestions.

---

## Review Methodology

### Step 1: Understand Context

Before reviewing any code:
- Read the PR description and linked issues
- Understand the purpose: what problem does this solve?
- Check the scope: is this a bug fix, feature, refactor, or config change?
- Identify the affected systems and potential blast radius

### Step 2: Correctness

This is the most important dimension. Does the code do what it claims to do?

- **Logic errors**: Off-by-one, incorrect conditionals, missing edge cases
- **State management**: Race conditions, stale state, missing cleanup
- **Error handling**: Unhandled exceptions, swallowed errors, missing retries
- **Data flow**: Are inputs validated? Are outputs correct in all cases?
- **Boundary conditions**: Empty inputs, null values, max values, concurrent access
- **Type safety**: Incorrect types, unsafe casts, missing null checks

### Step 3: Security

Check for vulnerabilities before they reach production.

- **Injection**: SQL injection, XSS, command injection, template injection
- **Authentication/Authorization**: Missing auth checks, privilege escalation
- **Secrets**: Hardcoded credentials, API keys, tokens in code or config
- **Input validation**: Unsanitized user input, missing bounds checking
- **Dependencies**: Known vulnerabilities in added/updated packages
- **Data exposure**: PII in logs, overly permissive API responses, debug endpoints
- **CSRF/CORS**: Missing protections on state-changing endpoints

### Step 4: Performance

Identify code that will be slow or resource-intensive.

- **Algorithmic complexity**: O(n^2) where O(n) is possible, unnecessary nested loops
- **Database**: N+1 queries, missing indexes, unbounded queries, missing pagination
- **Memory**: Large allocations, memory leaks, unbounded caches
- **Network**: Unnecessary API calls, missing batching, synchronous where async is possible
- **Concurrency**: Thread safety, deadlock potential, unnecessary serialization

### Step 5: Readability and Maintainability

Code is read far more often than it is written.

- **Naming**: Variables, functions, and classes have clear, descriptive names
- **Structure**: Functions are focused (single responsibility), files are organized
- **Comments**: Complex logic is explained (why, not what), no stale comments
- **Duplication**: Repeated code that should be extracted
- **Complexity**: Deeply nested conditionals, long functions, god objects
- **Conventions**: Follows the project's established patterns and style

### Step 6: Architecture

For larger changes, evaluate the design.

- **Separation of concerns**: Is business logic mixed with I/O or presentation?
- **API design**: Are interfaces clean, versioned, backward-compatible?
- **Dependencies**: Are new dependencies justified? Do they introduce risk?
- **Testability**: Can this code be tested in isolation?
- **Extensibility**: Will this design accommodate likely future changes?

---

## Anti-Patterns to Flag

These are common patterns that indicate deeper problems:

- **Catch-all exception handling**: `except Exception: pass` or `catch(e) {}`
- **Magic numbers/strings**: Hardcoded values without named constants
- **God functions**: Functions doing 5+ unrelated things
- **Premature optimization**: Complex code that optimizes for unlikely scenarios
- **Cargo cult code**: Copied patterns without understanding why
- **Boolean blindness**: `process(true, false, true)` instead of named parameters
- **Stringly typed**: Using strings where enums or types would be safer
- **Dead code**: Commented-out code, unreachable branches, unused imports
- **Implicit dependencies**: Hidden coupling through global state or environment

---

## Feedback Format

Structure feedback by severity:

### Critical (must fix before merge)
Issues that will cause bugs, security vulnerabilities, or data loss.

### Warning (should fix before merge)
Issues that will cause problems eventually — performance, maintainability, or reliability concerns.

### Suggestion (nice to have)
Improvements that would make the code better but aren't blocking.

### Positive (what's done well)
Always call out good patterns. Reinforcing good work is part of review.

### Feedback Template
```
**[CRITICAL/WARNING/SUGGESTION/POSITIVE]** [file:line]

[Description of the issue]

[Why it matters — the consequence if not addressed]

[Suggested fix — actual code, not just "fix this"]
```

---

## Principles

- **Be specific**: Point to exact lines. Show the fix, don't just describe the problem.
- **Explain why**: A reviewer who only says "change this" teaches nothing. Explain the principle.
- **Assume good intent**: The author made reasonable choices with the information they had.
- **Prioritize**: Not everything is equally important. Focus on what matters most.
- **Be constructive**: Every critique should come with a path forward.
- **Limit scope**: Review what's in the PR. Don't demand unrelated refactors.
- **Acknowledge trade-offs**: Sometimes "good enough" is the right call given constraints.

---

## Conventional Commits Check

If the PR includes commits, verify they follow conventional commit format:
- `feat:` — new feature
- `fix:` — bug fix
- `docs:` — documentation only
- `style:` — formatting, no logic change
- `refactor:` — code change that neither fixes a bug nor adds a feature
- `perf:` — performance improvement
- `test:` — adding or correcting tests
- `chore:` — build process, tooling, dependencies
- `ci:` — CI/CD changes

Flag commits that don't follow convention or have vague messages ("fix stuff", "updates").

---

## Review Summary Format

End every review with a summary:

```
## Review Summary

**Overall**: APPROVE / REQUEST_CHANGES / COMMENT

**Key Findings**:
- [Most important items, max 3-5]

**Risk Assessment**: LOW / MEDIUM / HIGH
[One sentence on the blast radius of this change]

**Testing**: [What should be tested before merge]
```
