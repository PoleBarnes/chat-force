# Vault Lint

Health-check the project vault. Find and fix structural issues that degrade wiki quality over time.

## When to Use

- Periodically after several ingests (every 5-10 sources)
- When the mechanic flags vault hygiene issues
- When queries return incomplete or contradictory results
- On request from the user

## Process

1. **Read `vault/index.md`** — this is the catalog. Every wiki page should be listed here.

2. **Scan for contradictions** — Read entity and concept pages. Look for pages that make conflicting claims about the same thing. Flag with `status: contradiction` in frontmatter and add a `## Contradictions` section noting the conflict.

3. **Find stale claims** — Look for pages citing old sources when newer sources have been ingested that supersede them. Mark `status: stale` in frontmatter.

4. **Find orphan pages** — Pages that exist in the wiki but have no inbound `[[wikilinks]]` from other pages. Either add cross-references from related pages or flag for review.

5. **Find missing pages** — Scan all `[[wikilinks]]` across the wiki. If a link target doesn't have its own page, create a stub or flag it as a gap.

6. **Find missing cross-references** — Pages that discuss the same topic but don't link to each other. Add the missing links.

7. **Identify data gaps** — Based on the wiki's coverage, suggest questions that can't be answered and sources that might fill the gaps. Present these to the user.

8. **Update log** — Append to `vault/log.md`:
   ```
   ## [YYYY-MM-DD HH:MM] lint | health-check
   - Contradictions found: N
   - Stale pages: N
   - Orphan pages: N
   - Missing pages: N
   - Cross-references added: N
   - Data gaps identified: N
   ```

## Rules

- Never delete pages during lint — flag them, don't remove them
- Never modify `vault/raw/` — lint only touches wiki pages
- Present data gaps and contradictions to the user — don't resolve them silently
- Update `vault/index.md` if you create any new stub pages
