---
name: grill-me
description: Aggressively and methodically interview the customer to fill out their eval criteria, brand, mission, avatar, never-list, and any other identity fields that are thin or empty. Use this whenever the customer asks for work that the harness is not yet equipped to do well.
trigger: intake channel; thin or missing harness identity/eval fields; customer asks for a deliverable that requires context the vault does not yet contain
attribution: Adapted from Matt Pocock's "grill-me" skill (https://github.com/mattpocock/skills/blob/main/grill-me/SKILL.md)
---

# SKILL: Grill Me

## Purpose

Extract everything this customer needs the bot to know — brand, voice, mission, avatar, never-list, reference materials, eval criteria — through systematic interrogation, not a single-shot form. A thin harness produces thin work. The moment a customer asks for something the harness cannot do well, the bot grills them to fix the harness first.

## When To Use

Invoke this skill when ANY of the following is true:

1. The customer's first message in `#<slug>-intake` arrives and the harness identity/eval files are placeholders or empty
2. A customer asks for a deliverable (ad, landing page, campaign) and the relevant fields in `identity/brand.md`, `identity/avatar.md`, `identity/never-list.md`, or `eval/criteria.yaml` do not contain enough specificity to produce good output
3. A past session's mechanic-log flagged that some field was missing or contradicted reality
4. The customer themselves asks to "grill me" or "make sure you understand what I want"

## Core Rules

1. **Interview the customer relentlessly** about every aspect of their brand, business, and expectations until you reach shared understanding.

2. **Walk down each branch of the decision tree.** Start at the root (mission / what the business does), walk down to brand voice, then target audience, then specific deliverable expectations, then never-list, then success criteria. Resolve dependencies between decisions one at a time — don't ask about voice before you understand the business.

3. **Ask one question at a time.** Never bundle. One question, wait for answer, integrate, next question.

4. **For every question, provide your recommended answer** based on what you already know about the business from the harness (vault, past sessions, brand-assets, web presence). Make it easy for the customer to confirm or correct rather than invent from scratch.

5. **Explore the harness before asking.** If a question can be answered by reading `vault/`, `brand-assets/`, or past sessions in `summaries/`, read first and confirm with the customer rather than asking a blank question. "I found X on your website — is that still accurate?" beats "Tell me about your website."

6. **Grill to completion, not to exhaustion.** Stop when the harness has enough specificity to produce the deliverable the customer asked for. Not everything needs to be perfect on day one; fill in what's needed NOW, note what else to grill on NEXT time.

7. **Write as you go.** Every confirmed answer lands in the appropriate harness file (`identity/brand.md`, `identity/avatar.md`, `eval/criteria.yaml`, etc.) before moving to the next question. Do not hold state in the conversation; the harness is the memory.

8. **Log the grilling session.** After the grill completes, write a summary page to `vault/summaries/sessions/<date>-grill-me-<topic>.md` so the Mechanic Agent can later analyze what was asked, what was learned, and what gaps remain.

## The Standard Decision Tree

When grilling from a cold start (brand new harness), walk this tree in order. Each level depends on the level above.

### Level 1 — The Business

- What does this business do in one sentence?
- Who are the customers? (B2C, B2B, enterprise, consumer, age range, geography)
- What do they sell? (products, services, subscriptions, one-off, recurring)
- What's the price point / order value range?
- What market do they play in? Who are the competitors?
- What's their competitive advantage or unfair edge?
- How long have they been in business?

### Level 2 — The Mission

- Why does this business exist beyond making money?
- What transformation do they want their customers to experience?
- Three years from now, what does success look like?
- What would they NEVER do, even for the money?

### Level 3 — The Brand Voice

- Pick three adjectives that describe how this brand sounds.
- Pick three adjectives that describe how this brand absolutely does NOT sound.
- Do they use humor? What kind? (dry, warm, absurdist, no humor at all)
- Reading level / formality?
- Punctuation norms? (Oxford comma? Exclamation points? Emojis? Em dashes?)
- Vocabulary taboos? (words they never use — "solution", "synergy", "revolutionary")
- Give an example of copy that nails the voice. Give an example that misses.

### Level 4 — The Avatar / ICP

- Who is the ideal customer? (demographics, psychographics, role, motivations)
- What's their biggest frustration that this business solves?
- What do they already know? What do they NOT know?
- Where do they live online? (platforms, communities, content they consume)
- What have they already tried that didn't work?
- How sophisticated are they about the category?

### Level 5 — Brand Assets & References

- Logo files, color hex codes, fonts, image style
- Existing website, social media handles, past campaigns
- Three brands they admire and want to feel similar to
- Three brands they DON'T want to be mistaken for
- Compliance or legal requirements (disclosures, disclaimers, regulated industries)

### Level 6 — Success Criteria (Eval)

- What does a "good" deliverable look like for this customer?
- What are the must-haves? (hard gates — if any is missing, it fails)
- What are the nice-to-haves? (quality signals but not blockers)
- What's the approval process? Who signs off?
- What happens if something ships that's off-brand? Recoverable, or is it a trust-breaking event?

### Level 7 — Deliverable-Specific

When the grill is triggered by a specific ask (e.g., "we need five LinkedIn posts"), dig into the specific deliverable:

- Channel and format (LinkedIn post vs article vs carousel)
- Audience on that channel (often differs from the overall ICP)
- Goal (awareness, leads, engagement, sales, authority)
- Timeline and cadence
- References (posts they've liked, posts they've hated)
- Constraints (length, format, required CTAs, compliance text)
- Approval gate

## Output Format

For every question the customer answers, write the confirmed value into the appropriate harness file using this pattern:

```markdown
## <field name>

<confirmed answer>

<!-- last confirmed: 2026-04-05, source: grill-me session with Anna -->
```

At the end of the grill session, produce a session summary at `vault/summaries/sessions/YYYY-MM-DD-grill-<topic>.md` with:

- Who was grilled (human name + Slack user ID)
- What topic triggered the grill
- Which harness files were updated and what changed
- What questions the customer couldn't answer yet (for next time)
- What contradictions came up between what the customer said and what the harness / vault / brand-assets already contained

## Anti-Patterns

Things NOT to do when grilling:

- **Don't bundle questions.** "Tell me about your brand voice and target audience" is two questions. Split them.
- **Don't ask blank questions.** If you can find the answer in `brand-assets/urls.md`, confirm it instead of asking.
- **Don't accept vague answers.** "Professional and friendly" is not a brand voice — push for three specific adjectives, a taboo list, and an example. Grill until the answer is operational.
- **Don't try to grill everything in one session.** If you're past 30 questions, the customer is tired. Stop, summarize, schedule another session.
- **Don't skip writing.** If you confirm an answer but don't write it to the harness, the next session will ask the same question. The harness is the memory.
- **Don't grill on trivia.** Grill on things that will change what the bot produces. "What's your favorite color?" is trivia unless it's a brand color.

## Escalation

If the customer refuses to answer a question, or the answers contradict each other, or the customer is visibly frustrated, STOP and:

1. Note the issue in the session summary
2. Post a brief message in `#<slug>-mechanic-log` describing what information is still missing
3. Let Travis (the human mechanic) handle the follow-up out of band

Do not try to paper over missing context with assumptions. Thin harness → thin work → broken customer trust.

## Remember

The grill exists because every deliverable the bot produces without sufficient context is a future apology. Front-load the pain of asking so the back-end pain of rework doesn't happen.
