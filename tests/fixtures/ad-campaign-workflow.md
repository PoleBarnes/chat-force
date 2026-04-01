# Ad Campaign Workflow — Leo Operating Instructions

Reference: PoleBarnes/ad-campaign-agent for full agent implementations.

## Overview

An ad campaign has two phases: Research → Generate. Each phase produces a review deliverable. Nothing ships without Travis's approval.

## Phase 1: Research

**Input:** Product details, target market, any existing positioning
**Output:** 3-5 campaign concepts with validated sales hooks

### Steps

1. **Parse the brief** — Extract product, audience, positioning, constraints, goals
2. **Web research** (iterative, minimum 2 passes per stream):
   - Pain point discovery — search Reddit, forums, Quora for customer language
   - Competitor analysis — fetch competitor landing pages, analyze hooks/copy/CTAs
   - Customer psychology — find decision stories, objections, emotional triggers
   - Sales hook generation — combine findings into 8-12 raw hooks, refine to top 5
3. **Develop concepts** — For each top hook: name, friction it addresses, target segments, creative direction, confidence level (HIGH/MEDIUM/LOW tied to source quality)
4. **Present for review** — Progressive disclosure: recommendation first, then concept cards, then supporting research

### Research Rules
- Ground every finding in real research with source URLs
- Use customer language from forums/reviews, not marketing jargon
- Each concept must be distinct, not variations of the same idea
- Be honest about confidence levels and gaps

## Phase 2: Generate

**Input:** Approved concept from research phase
**Output:** Complete multi-channel campaign package

### Deliverables
- Ad copy variants (3+ per segment per platform): headline, body, CTA
- AI-generated images + compositions with logos/text overlays
- Email drip sequence (5 HTML emails): welcome → value → proof → urgency → final CTA
- SMS sequence (3 messages)
- Landing page (standalone HTML)
- Campaign flow diagrams (Mermaid)

### Steps

1. **Plan structure** — Map how the hook translates per segment, how all pieces connect (ad → landing page → drip → conversion)
2. **Generate copy** — Vary angles: pain, aspiration, social proof, urgency, curiosity. Respect platform character limits.
3. **Generate images** — Use Gemini (Nano Banana 2 / `gemini-3.1-flash-image-preview`). Save all prompts for surgical edits.
4. **Compose images** — Add logos, text overlays, create platform-specific sizes
5. **Build emails** — Complete HTML with inline CSS, mobile-responsive, A/B subject lines
6. **Build landing page** — hero → problem → solution → proof → objections → CTA
7. **Verify** — Check messaging consistency across all channels, visual quality, completeness

## Core Advertising Principles

These are non-negotiable (from shared/principles/core.md):

1. **Sell the feeling of the problem being solved** — not the product
2. **You cannot create desire, only channel it** — find existing desire through research
3. **Know the awareness level** before writing (Unaware → Most Aware)
4. **The headline is 80% of the ad** — invest disproportionate effort
5. **Enter the conversation already in the customer's mind**
6. **Be specific, never vague** — numbers, timeframes, concrete outcomes
7. **Lead with emotion, justify with logic**
8. **Every ad needs a clear USP**
9. **Research is non-negotiable**
10. **Match the message to market sophistication**

## Quality Filters

Before any output ships:
- Does it sell the feeling? Can the reader feel life after?
- Is it grounded in real desire confirmed by research?
- Would you stop scrolling for this headline?
- Is it specific? Numbers, timeframes, concrete outcomes?
- Is there a clear next step?
- Is it honest?

## ⚠️ Approval Gates

- Research concepts → Travis reviews before generation starts
- Generated campaign → Travis reviews before any deployment
- Nothing ships without explicit approval
