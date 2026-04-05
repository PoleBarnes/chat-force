# The Factory Blueprint
## Self-Improving Marketing Agent — Architecture & System Prompt

---

## Part 1: What You're Building (The Distilled Vision)

You are not building an AI agent. You are building a **tuning harness** that wraps frontier intelligence (Claude Opus via Claude Code SDK) and systematically removes mistakes until it reliably produces marketing assets for a specific business.

**Core principle:** The intelligence already exists. You're just stopping it from screwing up.

**The loop:** Customer uses bot → bot produces output → output gets evaluated (mechanically + human) → mistakes become fixes → fixes get installed in the harness → bot never makes that mistake again.

**The business model:** You sell the harness as a Slack-based service. The customer sees a bot that gets their brand and improves over time. Behind the scenes, you're on the factory floor running jobs, catching failures, and installing fixes. Every client makes you better at running the next client.

---

## Part 2: Slack Workspace Architecture

### One Workspace Per Client

```
WORKSPACE: [Client Name] Factory
│
├── #client-intake (PUBLIC — customer sees this only)
│   └── Bot handles: campaign requests, brand Q&A, deliverable reviews
│   └── Customer provides: feedback, approvals, brand assets, goals
│   └── Rule: NOTHING leaves this channel without passing the eval
│
├── #factory-floor (PRIVATE — you + agents)
│   └── Where actual work happens
│   └── You prototype with agents here
│   └── Research, asset creation, iteration, drafts
│   └── Interactive back-and-forth with Claude Code
│
├── #mechanic-log (PRIVATE — improvement tracking)
│   └── Every mistake gets logged here
│   └── Every fix gets documented: what broke, why, what changed
│   └── Skills get proposed, reviewed, and installed
│   └── This is your compounding asset
│
└── #brand-assets (PRIVATE — knowledge base)
    └── Brand colors, logos, tone of voice, mission
    └── Avatar/ICP definitions
    └── Campaign history and results
    └── Reference materials, URLs, competitor info
```

---

## Part 3: The System Prompt (Starter — Will Be Iterated)

Use this as the base system prompt for your Slack bot agent. Adapt per client.

```
You are a marketing campaign agent operating inside a business harness.

## YOUR IDENTITY
- You work for [CLIENT BUSINESS NAME]
- You produce marketing assets: ad copy, campaign briefs, landing pages, social content, email sequences
- You do NOT freestyle. Every output must align with the brand guide and eval criteria below.

## BRAND CONTEXT
[FILLED DURING INTAKE]
- Business name:
- What they sell:
- Who they sell to (avatar/ICP):
- Market position / competitive advantage:
- Brand voice (tone, style, vocabulary):
- Brand colors (hex codes):
- Mission statement:
- What they NEVER want to say or do:
- Reference URLs (website, socials, competitors):

## INTAKE PROTOCOL
When a user requests a new campaign or marketing asset:

1. CONFIRM THE GOAL — What business outcome are we trying to achieve? (leads, awareness, sales, retention)
2. CONFIRM THE CHANNEL — Where will this run? (Instagram, Facebook, Google, email, landing page, multi-channel)
3. CONFIRM THE AUDIENCE — Who specifically are we targeting within the ICP?
4. CONFIRM THE TIMELINE — When does this need to be live?
5. CONFIRM REFERENCE MATERIAL — Are there existing assets, past campaigns, or inspiration to reference?
6. CONFIRM CONSTRAINTS — Budget, compliance requirements, things to avoid?

Do NOT proceed to production until all six are answered. If the user tries to skip, push back politely but firmly: "I want to make sure this campaign hits the mark. Can you help me with [missing item]?"

## PRODUCTION PROTOCOL
When producing any marketing asset:

1. Draft internally first — do not present first draft to customer
2. Self-evaluate against the EVAL CRITERIA below
3. Fix anything that fails eval
4. Present to customer with a brief explanation of what you produced and why
5. Collect feedback (thumbs up, thumbs down, specific notes)
6. Iterate based on feedback
7. When approved, mark as READY FOR DEPLOY

## EVAL CRITERIA (Mechanical Checks)
Every output MUST pass ALL of the following before being presented:

- [ ] On brand — colors, tone, vocabulary match brand guide
- [ ] On message — aligns with mission and market position
- [ ] On target — speaks to the defined avatar/ICP
- [ ] No hallucinated claims — every product/service claim is verified against brand assets
- [ ] No broken links or placeholder text
- [ ] Correct grammar, spelling, punctuation
- [ ] Includes required legal/compliance elements if applicable
- [ ] Appropriate for the specified channel (correct dimensions, format, length)
- [ ] Call to action is clear and actionable
- [ ] Does not contain anything on the NEVER list

## MISTAKE PROTOCOL
When something goes wrong (customer reports an issue, you catch an error, output fails eval):

1. Log the mistake: what happened, what was expected, what actually occurred
2. Identify root cause: was it missing context? Wrong assumption? Skill gap? Tool failure?
3. Propose a fix: what specific change to the harness would prevent this in the future?
4. Flag for human review: post to #mechanic-log with the format:

   MISTAKE: [description]
   ROOT CAUSE: [analysis]
   PROPOSED FIX: [specific change]
   SEVERITY: [low/medium/high]

Do NOT install fixes yourself. The mechanic (human) approves all changes.

## WHAT YOU DO NOT DO
- You do not deploy anything without human approval
- You do not change your own eval criteria
- You do not skip intake steps
- You do not present work that hasn't passed eval
- You do not make promises about timelines without checking with the team
- You do not access systems or APIs without explicit authorization
```

---

## Part 4: First Week Action Plan

### Day 1-2: Set Up the Workspace
- [ ] Create Slack workspace: "Mailbox Money Factory"
- [ ] Create four channels: #client-intake, #factory-floor, #mechanic-log, #brand-assets
- [ ] Set channel permissions (client only sees #client-intake)
- [ ] Install Claude Code bot into workspace

### Day 3-4: Do the Intake Yourself
- [ ] Run through the intake protocol AS IF you were the client
- [ ] Scrape Mailbox Money's website, socials, existing materials
- [ ] Build out the brand context section of the system prompt
- [ ] Populate #brand-assets with everything you find
- [ ] Identify what's missing — what do you need from the actual client?

### Day 5-6: Run Three Test Jobs
Pick three realistic tasks the client would ask for:
1. "Create three Instagram ad variants for [current offer]"
2. "Write a 5-email welcome sequence for new leads"
3. "Build a one-page landing page for [specific campaign]"

Run each through the full loop:
- Intake (fill in the six fields yourself)
- Production (work with agent on factory floor)
- Eval (run through the checklist)
- Fix (log any failures to #mechanic-log)
- Re-run (confirm fixes hold)

### Day 7: Review and Prepare for Client
- [ ] Review #mechanic-log — how many fixes were needed? What patterns?
- [ ] Update system prompt with any new eval criteria discovered
- [ ] Prepare a demo: show the client 1-2 polished outputs
- [ ] Create the client intake checklist based on what you learned was missing
- [ ] Invite client to #client-intake channel

---

## Part 5: The Mechanic Log Format

Every entry in #mechanic-log should follow this structure:

```
---
DATE: [date]
JOB: [what was being produced]
MISTAKE: [what went wrong]
ROOT CAUSE: [why it went wrong]
FIX TYPE: [skill file | eval check | prompt update | tool config | process change]
FIX DETAIL: [exactly what was changed]
VERIFIED: [yes/no — did you re-run and confirm the fix holds?]
---
```

Over time this log becomes your most valuable asset. It's the accumulated intelligence of every mistake you've caught and fixed. When you onboard a new client, you start with all these fixes already installed.

---

## Part 6: Skill File Template

When a fix is complex enough to become a reusable skill:

```
# SKILL: [skill name]
# VERSION: 1.0
# CREATED: [date]
# SOURCE: [which client/job revealed the need]

## PURPOSE
[One sentence: what does this skill enable the agent to do correctly?]

## WHEN TO USE
[Under what conditions should the agent invoke this skill?]

## INSTRUCTIONS
[Step-by-step instructions the agent follows]

## QUALITY CHECKS
[Specific things to verify when this skill is used]

## KNOWN ISSUES
[Edge cases or failure modes discovered during testing]
```

---

## Part 7: Competitive Positioning

### What the big players are doing
- **Salesforce Slackbot**: 30 new AI features, reusable AI skills, MCP integration. Enterprise-focused, expensive, generic. No bespoke tuning.
- **Jasper AI**: 100+ marketing agents, content pipelines. A tool you log into, not a tuned agent in your Slack.
- **Kana ($15M seed)**: Flexible marketing agents, "build with" model. Closest competitor but VC-funded platform play.
- **Uplane (YC)**: Replaces agencies with AI. Self-improving but no human mechanic in the loop.

### Your differentiator
Nobody is selling the mechanic. You are the person on the factory floor tuning the intelligence to the specific business. The longer a client stays, the better their agent gets, and the harder it is to leave. You sell compounding improvement, not a tool.

### Your moat
- Per-client tuning compounds over time (switching cost)
- Cross-client skill transfer through the mechanic (you) learning patterns
- The mechanic log is a proprietary knowledge base of marketing agent failure modes and fixes
- Slack distribution eliminates adoption friction

---

## Part 8: What to Prove This Month

**The one thing that validates everything:** Run a job through the harness. Watch it fail. Fix it. Run it again. Confirm the fix holds.

If you can do that, your entire thesis works. Everything else is just doing it more times.
