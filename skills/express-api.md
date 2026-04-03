# Express REST API Skill

## Overview
Pattern for building RESTful CRUD APIs with Express.js, SQLite (better-sqlite3), input validation, and integration tests.

## Stack
- **Runtime:** Node.js + Express 5
- **Database:** SQLite via better-sqlite3 (WAL mode for concurrency)
- **Testing:** Jest + Supertest (integration tests against real endpoints)

## Project Structure
```
api/
├── migrations/        # Sequential .sql files (001_create_*.sql)
├── src/
│   ├── db.js          # Database init + migration runner
│   ├── app.js         # Express app factory (accepts dbPath, testable)
│   └── server.js      # Production entrypoint
├── tests/
│   └── *.test.js      # Integration tests
└── package.json
```

## Key Patterns

### App Factory
Export a `createApp(dbPath)` function that accepts `:memory:` for tests and a real path for production. Attach `app._db` for cleanup in tests.

### Migration System
- SQL files in `migrations/` sorted alphabetically (prefix with `001_`, `002_`, etc.)
- `_migrations` table tracks what's been applied
- Migrations run in a transaction — atomic apply

### Input Validation
- Validate on POST (all required fields) and PUT (partial — only validate fields present)
- Return 422 with `{ errors: [...] }` array for validation failures
- Trim string inputs, reject empty/whitespace-only strings

### Status Codes
| Action | Success | Not Found | Validation Error | Bad Request |
|--------|---------|-----------|-----------------|-------------|
| GET list | 200 | — | — | — |
| POST create | 201 | — | 422 | — |
| PUT update | 200 | 404 | 422 | 400 (bad id) |
| DELETE | 204 | 404 | — | 400 (bad id) |

### Route Ordering
Define specific routes (e.g., `/tasks/stats`) **before** parameterized routes (`/tasks/:id`) to avoid conflicts.

### Concurrency
- `PRAGMA journal_mode = WAL` enables concurrent reads during writes
- better-sqlite3 is synchronous — no race conditions within a single process

## Testing Strategy
- Fresh in-memory DB per test (`beforeEach` / `afterEach`)
- Test happy paths, missing fields, invalid types, edge cases (whitespace, long strings, case sensitivity)
- Test 404s for nonexistent resources, double-delete, bad ID formats
- Test concurrent requests with `Promise.all`
- Aim for 25+ test cases covering every endpoint and edge case

## Commands
```bash
npm start              # Run server
npm test               # Run all tests
npm install --include=dev  # Install with dev dependencies
```
