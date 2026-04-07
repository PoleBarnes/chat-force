# Vault Ingest

Ingest external content into the project vault following the VAULT.md schema.

## When to Use

- You read or referenced an external URL, document, or data source
- You received raw content that should be preserved for future sessions
- The `research-spike` template requires vault summaries

## Process

1. **Read the source fully.** Don't skim — read the entire source before writing anything.

2. **Discuss key takeaways with the user.** Before writing to the vault, present the 3-5 most important things from the source. Let the user guide what to emphasize. This is the human's chance to shape what gets filed.

3. **Write source summary** — Create `vault/summaries/sources/<slug>.md` with YAML frontmatter:
   ```yaml
   ---
   type: summary
   status: draft
   created: YYYY-MM-DD
   updated: YYYY-MM-DD
   sources: [raw/<filename> or URL]
   tags: []
   ---
   ```
   Include a structured summary emphasizing what the user cared about.

4. **Update entities/concepts** — If the content introduces new entities (people, products, companies) or concepts, create or update files in `vault/entities/` or `vault/concepts/`. A single source might touch 10-15 wiki pages — that's normal.

5. **Cross-link** — Every entity/concept reference becomes a `[[wikilink]]`. Follow existing cross-reference patterns in the wiki.

6. **Update index** — Add entries to `vault/index.md` for every new page created.

7. **Append to log** — Add an entry to `vault/log.md`:
   ```
   ## [YYYY-MM-DD HH:MM] ingest | source-slug
   - Added summary: vault/summaries/sources/<slug>.md
   - Created entities: <list>
   - Updated entities: <list>
   - Created concepts: <list>
   - Updated concepts: <list>
   ```

## Rules

- Never modify files in `vault/raw/` — that's for original unprocessed content
- Never skip the index or log update — an unindexed page is invisible
- Never invent facts — summarize only what the source contains
- Flag contradictions with existing vault content rather than silently overwriting
- Ingest one source at a time — don't batch unless the user asks
