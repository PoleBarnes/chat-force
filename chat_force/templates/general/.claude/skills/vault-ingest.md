# Vault Ingest

Ingest external content into the project vault following the VAULT.md schema.

## When to Use

- You read or referenced an external URL, document, or data source
- You received raw content that should be preserved for future sessions
- The `research-spike` template requires vault summaries

## Process

1. **Write source summary** — Create `vault/summaries/sources/<slug>.md` with YAML frontmatter (type, status, created, sources, tags) and a structured summary of the content.

2. **Update entities/concepts** — If the content introduces new entities (people, products, companies) or concepts, create or update files in `vault/entities/` or `vault/concepts/` with cross-references.

3. **Update index** — Add an entry to `vault/index.md` cataloging the new summary.

4. **Append to log** — Add an entry to `vault/log.md` in the format:
   ```
   ## [YYYY-MM-DD HH:MM] ingest | source-slug
   - Added summary: vault/summaries/sources/<slug>.md
   - Updated entities: <list>
   - Updated concepts: <list>
   ```

5. **Cross-link** — Use `[[wikilinks]]` in summaries to reference related entities and concepts.

## Rules

- Never modify files in `vault/raw/` — that's for original unprocessed content
- Never skip the index or log update
- Never invent facts — summarize only what the source contains
- Flag contradictions with existing vault content rather than silently overwriting
