# VAULT.md — The Schema

> **You (the LLM) are reading this because you're working inside a customer harness vault.** This file tells you how to maintain it. Read it before you ingest, query, or lint.
>
> This file is the **Layer 3 schema** from Karpathy's LLM Wiki pattern — the config that tells you what this vault is, what it should look like, and how you operate on it.

---

## What This Vault Is

A customer-specific knowledge base that compounds over every session. It is this customer's proprietary intelligence. The more work the bot does for this customer, the smarter this vault gets. No other customer's bot ever sees what's here.

The vault is NOT a document dump. It is a **curated, interlinked, LLM-maintained wiki** modeled on Andrej Karpathy's LLM Wiki pattern (published 2026-04-04). Every page has a purpose. Every cross-reference is intentional. Orphaned pages get cleaned up during lint passes.

## Three Layers

### Layer 1 — Raw (`vault/raw/`)

Immutable source material. You read from it, never modify it.

```
raw/
├── brand-guides/           Brand books, style guides, tone-of-voice docs
├── past-campaigns/         Prior creative, briefs, reports, screenshots
├── research/               Market research, surveys, analyst reports
├── competitors/            Competitor materials, teardowns, comparisons
├── customer-interviews/    Transcripts, call notes, feedback
├── product/                Product specs, feature docs, pricing sheets
├── slack-captures/         Exported Slack threads worth preserving
├── web-clips/              Articles, blog posts scraped from the web
└── assets/                 Images, PDFs, video, audio referenced elsewhere
```

Files here are added by:
- Humans dropping attachments into `#brand-assets` channel (engine ingests them)
- The bot scraping URLs mentioned in conversations
- Explicit uploads via workspace admin flows

**Never rewrite raw files.** If a source is wrong, annotate the correction in a summary or concept page — keep the original for provenance.

### Layer 2 — Wiki (`vault/` excluding `raw/`)

LLM-generated, LLM-maintained. Every file here was written by you or a previous session's worker. Humans may edit for corrections; they should not be expected to author pages from scratch.

```
vault/
├── index.md                Catalog — every page with a one-line summary, by category
├── log.md                  Append-only log — every ingest, query, lint, session
├── summaries/
│   ├── sources/            One file per raw source — key claims, entities, citations
│   └── sessions/           One file per factory floor session — what was built, what was learned
├── entities/
│   ├── competitors/        One file per competitor
│   ├── products/           One file per product/SKU we sell
│   ├── personas/           One file per customer avatar/ICP
│   ├── campaigns/          One file per past or active campaign
│   ├── people/             Internal team, external contacts
│   └── platforms/          Meta, Google, LinkedIn, mailing providers, etc.
├── concepts/               Domain concepts — brand voice, messaging pillars,
│                           category insights, regulatory constraints
└── decisions/              Decision log — "we tried X, result was Y, lesson is Z"
```

### Layer 3 — Schema (this file)

Tells you (the LLM) how to do the work. This file and the customer's `identity/`, `eval/`, and `skills/` directories together form the full context you work against.

---

## Core Operations

### Ingest

Triggered when a new source lands in `raw/` OR when the bot is explicitly told to ingest something.

**Steps:**
1. **Read the source fully.** Text files: read. PDFs: extract text. Images: describe them. Videos/audio: transcribe if tooling allows, otherwise note and defer.
2. **Write a summary page** to `summaries/sources/<slug>.md` using the source template (see below). Include provenance: source filename, date, who added it.
3. **Update affected entity pages.** If the source mentions a competitor we already have, update that competitor's entity page with new facts. If it mentions a NEW competitor, create `entities/competitors/<slug>.md`.
4. **Update affected concept pages.** New messaging pillar? Update `concepts/messaging-pillars.md`. New category insight? New page.
5. **Cross-link.** Every entity reference becomes `[[entities/competitors/acme]]` or `[Acme Corp](../entities/competitors/acme.md)`. Every concept reference becomes a link.
6. **Update `index.md`.** Add the new pages to their category with one-line summaries.
7. **Append to `log.md`** with format `## [YYYY-MM-DD HH:MM] ingest | <source slug>` followed by bullet points of what changed.
8. **Check for contradictions.** If the new source contradicts an existing page, ADD the contradiction note to that page — don't silently overwrite. Flag it for the Mechanic Agent to surface in `#mechanic-log`.

One ingest can touch 10–20 files. That's normal.

### Query

Triggered when the bot needs context — during prototyping, during deliverable production, or when the human asks a direct question in Slack.

**Steps:**
1. **Start with `index.md`** to find candidate pages.
2. **Read relevant pages in full.** Don't chunk or embed — at our scale (hundreds of pages), read-the-whole-page is fine and produces better answers.
3. **Follow cross-references.** If a page links to `[[entities/competitors/acme]]`, read that too.
4. **Synthesize with citations.** Every claim in your answer should link back to the source page: `(see [[summaries/sources/acme-2026-q1-report]])`.
5. **If the answer is novel and worth preserving, file it back.** Create a new page in `concepts/` or `decisions/` and update `index.md`. Good answers become future context.
6. **Append to `log.md`** with format `## [YYYY-MM-DD HH:MM] query | <one-line question>`.

### Lint

Triggered by the Mechanic Agent (not the worker) on a schedule or after N sessions.

**Steps:**
1. **Walk `index.md` against the filesystem.** Find orphan pages (in index but missing on disk) and unindexed pages (on disk but missing from index). Fix both.
2. **Find stale claims.** A page says "our latest campaign is Q1" but we've since added Q2 and Q3 campaign pages. Update or deprecate.
3. **Find contradictions.** Two pages claim different things about the same entity. Flag and resolve — usually by citing the newer source.
4. **Find orphans.** Pages that nothing links to. Either wire them in or archive them.
5. **Find gaps.** Categories with obvious holes (e.g., three competitors mentioned in sources but only two have entity pages).
6. **Propose additions.** Questions that came up in recent sessions and weren't answered from the vault → those become research tasks or new pages.
7. **Write a lint report** to `mechanic-log/<date>-vault-lint.md` in the harness root (not inside the vault). Human mechanic reviews and approves fixes.
8. **Append to `log.md`** with format `## [YYYY-MM-DD HH:MM] lint | <N issues found, N fixed, N deferred>`.

---

## File Conventions

### Every page starts with YAML frontmatter:

```yaml
---
type: entity | concept | summary | decision | overview
category: competitors | products | personas | ...  (for entity pages)
status: draft | reviewed | stale | archived
created: 2026-04-05
updated: 2026-04-05
sources: ["summaries/sources/acme-q1-report", "..."]  # pages this derives from
tags: [brand, pricing, q1-2026]
---
```

Frontmatter lets future tooling (Dataview-style queries, vault health scripts) pull pages by type/status/tag without re-parsing prose.

### Page bodies use:

- `#` H1 for the page title (once)
- `##` H2 for sections
- `[[wikilinks]]` for internal references — Obsidian-compatible
- Relative markdown links `[text](../entities/x.md)` as a fallback
- Source citations at the end of factual claims — `(per [[summaries/sources/acme-q1]])`
- A **Last Updated** line near the bottom referencing the most recent ingest/session that touched it

### Log entry format:

```markdown
## [2026-04-05 14:30] ingest | acme-competitor-teardown.pdf
- Added: entities/competitors/acme.md (new)
- Updated: concepts/messaging-pillars.md (added differentiation section)
- Updated: index.md
- Flagged: pricing contradiction with existing note in entities/competitors/acme.md (Mechanic to resolve)

## [2026-04-05 15:10] query | "what angles did we try last summer for the pool-bot?"
- Read: summaries/sessions/2026-07-14-pool-summer-campaign.md
- Read: entities/campaigns/summer-2025-pool.md
- Synthesized answer; no new pages created.

## [2026-04-05 23:00] lint | 47 pages checked, 3 issues found, 2 auto-fixed, 1 flagged
- Auto-fixed: 2 orphan pages re-linked from index.md
- Flagged: concepts/regulatory.md cites a 2024 FTC doc that has been superseded
```

### Naming:

- Slugs are lowercase, hyphenated: `acme-corp`, `q1-2026-instagram-campaign`, `brand-voice`
- Files end in `.md`
- Directories for entities/categories are plural: `competitors/`, `products/`
- Concept and decision files live flat (no subdirectories) unless the category has 20+ pages

---

## What You (the LLM) Must Not Do

- **Don't re-ingest.** Before writing a new summary, grep the vault. If it's already there, update instead of duplicating.
- **Don't silently overwrite.** If a source contradicts an existing page, keep both and flag — never delete facts.
- **Don't skip the index update.** An unindexed page is invisible next time.
- **Don't skip the log entry.** The log is how the Mechanic Agent and the human reviewer understand what happened.
- **Don't edit `raw/`.** Ever. Append annotations in summary pages instead.
- **Don't create orphans.** Every page must be linked from at least one other page (index counts).
- **Don't invent facts.** If the vault doesn't have it, say so. Never fabricate to fill a gap.

---

## Scale Notes

This vault is designed for roughly **100–1000 pages** per customer before scaling considerations kick in. At that scale, read-the-whole-index is fast enough, cross-references stay manageable, and embeddings/RAG are unnecessary.

If a customer's vault grows past 1000 pages, revisit: consider BM25 search, hierarchical index files, or archiving cold categories.

---

## Historical Reference

This vault structure is an adaptation of Andrej Karpathy's LLM Wiki pattern (gist published April 2026, commit 442a6bf). Karpathy's version is single-user / personal knowledge. Our adaptation adds:

1. **Per-customer isolation.** Each harness has its own vault. No cross-customer knowledge transfer without explicit human action.
2. **The Mechanic loop.** A second LLM (the Mechanic Agent) lints the vault and proposes fixes, rather than relying on the worker to self-maintain.
3. **Integration with the mechanic-log.** Vault maintenance issues flow into the same fix proposal channel as code/skill improvements.
4. **Session-as-source.** Every factory floor session becomes a summary page, turning work output into permanent organizational memory.
