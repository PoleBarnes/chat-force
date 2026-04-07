# VAULT.md -- The Schema

> You (the LLM) are reading this because you're working inside a project vault. This file tells you how to maintain it. Read it before you ingest, query, or update.

---

## What This Vault Is

A project-specific knowledge base that compounds over every session. The more work you do, the smarter this vault gets.

The vault is NOT a document dump. It is a **curated, interlinked, LLM-maintained wiki**. Every page has a purpose. Every cross-reference is intentional. Orphaned pages get cleaned up during lint passes.

## Structure

```
vault/
├── VAULT.md            This file -- the schema
├── index.md            Catalog of every page, one-line summary each
├── log.md              Append-only activity log
├── raw/                Immutable source material (never modify)
├── summaries/
│   ├── sources/        One file per raw source
│   └── sessions/       One file per session
├── entities/           One file per named thing (competitors, products, personas, etc.)
├── concepts/           Domain concepts, insights, patterns
└── decisions/          Decision log -- "we tried X, result was Y, lesson is Z"
```

## Core Operations

### Ingest (new source material)

1. Read the source fully.
2. Write a summary to `summaries/sources/<slug>.md`.
3. Update affected entity and concept pages (create new ones if needed).
4. Cross-link: every entity/concept reference becomes a link.
5. Update `index.md` with new pages.
6. Append to `log.md`.
7. If the source contradicts an existing page, keep both and flag -- never silently overwrite.

### Query (looking something up)

1. Start with `index.md` to find relevant pages.
2. Read candidate pages in full. Follow cross-references.
3. Synthesize with citations: `(see [[summaries/sources/slug]])`.
4. **File valuable answers back into the wiki.** Comparisons, analyses, connections you discovered — these are worth keeping. Create a new page in the appropriate directory (concepts, entities, or decisions). Don't let good synthesis disappear into chat history.
5. Append to `log.md`.

### Lint (periodic health check)

Run periodically to keep the wiki healthy as it grows:

1. **Contradictions** — scan for pages that make conflicting claims. Flag with `status: contradiction` frontmatter.
2. **Stale claims** — look for pages citing old sources when newer sources supersede them.
3. **Orphan pages** — find pages with no inbound links from other wiki pages.
4. **Missing pages** — find concepts or entities mentioned in wikilinks that don't have their own page yet.
5. **Missing cross-references** — find pages that discuss the same topic but don't link to each other.
6. **Data gaps** — identify questions the wiki can't answer that could be filled with a new source.
7. Update affected pages and append to `log.md`.

## File Conventions

Every wiki page starts with YAML frontmatter:

```yaml
---
type: entity | concept | summary | decision
status: draft | reviewed | stale | archived
created: YYYY-MM-DD
updated: YYYY-MM-DD
sources: []
tags: []
---
```

- `#` H1 for the page title (once)
- `##` H2 for sections
- `[[wikilinks]]` for internal references
- Slugs are lowercase, hyphenated: `acme-corp`, `brand-voice`

## Log Entry Format

```markdown
## [YYYY-MM-DD HH:MM] ingest | source-slug
- Added: entities/competitors/acme.md (new)
- Updated: index.md

## [YYYY-MM-DD HH:MM] query | "what is our pricing strategy?"
- Read: entities/products/main-product.md
- Synthesized answer; no new pages created.
```

## Rules

- **Never modify `raw/`.** Annotate in summary pages instead.
- **Never skip the index update.** An unindexed page is invisible.
- **Never skip the log entry.** The log is how reviewers understand what happened.
- **Never invent facts.** If the vault doesn't have it, say so.
- **Never silently overwrite.** Contradictions get flagged, not buried.
