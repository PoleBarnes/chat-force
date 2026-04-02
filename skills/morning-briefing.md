---
name: morning-briefing
description: Daily status briefing — blocked items, approvals, overnight work, upcoming tasks, system health
triggers:
  - /checkin
  - morning briefing
  - status
enabled_by_default: true
category: operations
---

# Morning Briefing

You are preparing Travis's morning briefing. Your job is to give a clear, concise picture of where things stand so Travis can make decisions and unblock work quickly.

**Respect Travis's time.** Lead with what needs his attention. Use progressive disclosure — headline first, details on request.

---

## Briefing Structure

### 1. Decisions Needed (Blockers)

Items that are blocked waiting for Travis's input. These get top billing.

Format:
```
### Decisions Needed

**[Item]**: [One sentence describing the decision needed]
- Context: [Minimal context to make the decision]
- Options: [A, B, or C — with your recommendation]
- Blocked since: [date/time]
```

If there are no blockers, say so explicitly: "No blockers. All work is proceeding."

### 2. Approvals Waiting

Items completed and ready for Travis's review/approval.

Format:
```
### Approvals Waiting

- **[Item]**: [What's ready for review] — [link if applicable]
```

This includes:
- Campaign concepts ready for review
- PRs ready for merge
- Deployed changes ready for verification
- SOPs proposed for formalization
- Any output that needs sign-off before next step

### 3. Completed Since Last Briefing

Work finished since the last check-in.

Format:
```
### Completed

- [Task]: [One sentence summary of what was done]
```

Keep this concise. Travis doesn't need to re-read the work — just know it's done. Provide links to detailed results if he wants to dig in.

### 4. In Progress

Work currently underway.

Format:
```
### In Progress

- [Task]: [Status — percentage or phase] — ETA: [estimate]
```

Flag anything at risk of missing its estimate.

### 5. Upcoming

Work planned for the next cycle.

Format:
```
### Upcoming

- [Task]: [Brief description] — Priority: [HIGH/MEDIUM/LOW]
```

### 6. System Health

Quick status of platform systems.

Format:
```
### System Health

- OpenClaw: [OK / DEGRADED / DOWN]
- Slack integration: [OK / DEGRADED / DOWN]
- Doppler secrets: [OK / DEGRADED / DOWN]
- LangGraph: [OK / DEGRADED / DOWN / NOT DEPLOYED]
- Daily token spend: [$X.XX of $50.00 limit]
- Errors (24h): [count — brief if any]
```

---

## Information Sources

To compile the briefing, check:

1. **Task queue / issue tracker**: Open issues, their status, any that are blocked
2. **Git log**: Recent commits on active branches
3. **Approval queue**: Items awaiting Travis's review (exec-approvals.json)
4. **System logs**: Errors, warnings, or anomalies in the last 24 hours
5. **Token/cost tracking**: Daily spend against limits
6. **Calendar**: Any scheduled events, deadlines, or milestones

---

## Tone and Format

- **Concise**: The entire briefing should be scannable in under 60 seconds
- **Actionable**: Every item either needs a decision, acknowledgment, or is informational
- **Honest**: If something is behind schedule or at risk, say so plainly
- **Structured**: Always use the same format so Travis knows where to look
- **No fluff**: Skip greetings, pleasantries, and filler. Get straight to the information.

---

## Example Briefing

```
## Morning Briefing — 2026-04-01

### Decisions Needed
**Campaign concept selection**: 3 concepts ready for BlackTie April campaign.
- Recommend: "Built to Last" (HIGH confidence, strongest research backing)
- See full review: [link]
- Blocked since: yesterday 4pm

### Approvals Waiting
- **PR #12**: Add skills framework to platform — ready for review
- **SOP proposal**: Campaign research workflow — draft for your feedback

### Completed
- Skills framework: 7 skills created and registered in base-config
- Gateway CLI test: Leo successfully processes research brief

### In Progress
- LangGraph local setup: configuring in devcontainer — ETA: today
- Email template system: building HTML templates — ETA: tomorrow

### Upcoming
- Campaign generation test with BlackTie fixture — Priority: HIGH
- Standing order enforcement (cron/heartbeat) — Priority: MEDIUM

### System Health
- OpenClaw: OK
- Slack: OK
- Doppler: OK
- LangGraph: NOT DEPLOYED
- Daily spend: $3.42 of $50.00
- Errors (24h): 0
```

---

## Cadence

- **Default**: One briefing per day, first thing
- **On-demand**: Travis can request a briefing at any time with `/checkin` or "status"
- **Abbreviated**: If nothing changed since last briefing, say "No changes since last briefing" and list only any new blockers
