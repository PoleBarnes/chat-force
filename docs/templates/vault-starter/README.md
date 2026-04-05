# Vault Starter Template

Copy this directory into a new customer harness as `harness-<slug>/vault/` to initialize their knowledge base.

## What you get

```
vault/
├── VAULT.md          The schema — tells the LLM how to maintain this vault
├── index.md          The catalog — empty, ready for first entries
├── log.md            The operation log — append-only
├── raw/              Raw sources (immutable) — all empty subdirectories
│   ├── brand-guides/
│   ├── past-campaigns/
│   ├── research/
│   ├── competitors/
│   ├── customer-interviews/
│   ├── product/
│   ├── slack-captures/
│   ├── web-clips/
│   └── assets/
├── summaries/
│   ├── sources/      One file per ingested source
│   └── sessions/     One file per factory-floor session
├── entities/
│   ├── competitors/
│   ├── products/
│   ├── personas/
│   ├── campaigns/
│   ├── people/
│   └── platforms/
├── concepts/         Flat directory of domain concept pages
└── decisions/        Flat directory of decision records
```

## How to use it

1. **Copy into a harness.**
   ```
   cp -r docs/templates/vault-starter ../harness-<slug>/vault
   ```

2. **Customize `VAULT.md`** if this customer has unique knowledge-base needs. In most cases the default schema works — don't fork it unless you have a reason.

3. **Start ingesting.** Drop files into `raw/<category>/` as they come in:
   - Brand guides and style docs → `raw/brand-guides/`
   - Past creative and campaign reports → `raw/past-campaigns/`
   - Competitor research → `raw/competitors/`
   - Product specs → `raw/product/`
   - Customer interview transcripts → `raw/customer-interviews/`
   - Articles, blog posts → `raw/web-clips/`
   - Images, PDFs, screenshots referenced by other files → `raw/assets/`

4. **Let the bot ingest.** When the engine detects a new file in `raw/` (or when explicitly told), the worker runs an ingest operation per `VAULT.md`. This writes a summary page, updates entity pages, cross-links, and updates the index.

5. **Review the index periodically.** Walk `index.md` → pick a page → read it → confirm accuracy. You're the editor-in-chief; the LLM is the writer.

## Design reference

This vault structure is adapted from **Andrej Karpathy's LLM Wiki pattern** (gist published April 2026). The core pattern: raw sources are immutable inputs, the LLM builds and maintains the interlinked wiki on top of them, and a schema file (`VAULT.md`) tells the LLM how to do the bookkeeping.

Karpathy's key insight: *"The tedious part of maintaining a knowledge base is not the reading or the thinking — it's the bookkeeping. LLMs don't get bored, don't forget cross-references, can touch 15 files in one pass."*

Chat-force adaptations:
- **Per-customer isolation.** Each harness has its own vault. No cross-customer knowledge transfer without explicit human action.
- **Mechanic loop integration.** A separate LLM (the Mechanic Agent) lints the vault and proposes fixes to the `#mechanic-log` channel for human approval — the bot doesn't self-modify without oversight.
- **Session-as-source.** Every factory-floor session automatically becomes a summary page, turning ephemeral work into permanent organizational memory.
- **Obsidian-compatible.** Wikilinks (`[[page]]`) and YAML frontmatter work in Obsidian, so humans can browse visually when they want.

## Anti-goals

- **No embeddings or RAG at the start.** At 100–1000 pages, read-the-whole-index is fast and accurate. Embeddings add complexity with unclear ROI below that threshold.
- **No auto-install from raw.** Every fix to the LLM-written layer goes through `#mechanic-log` for human approval, same as skills and eval updates.
- **No shared knowledge across customers.** Even if two customers sell similar products, their vaults stay separate. Knowledge transfer is a manual operation by the human mechanic.
- **No human authoring in the wiki layer.** Humans drop sources into `raw/` and correct LLM mistakes. They don't author summary/entity/concept pages from scratch — that's the LLM's job.
