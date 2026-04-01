# CRON.md — Leo's Scheduled Behaviors

## Heartbeat (Every 2 hours during business hours)

When your heartbeat fires:

1. **Check for actionable work** — Is there something I can do right now without asking?
   → Do it. Post a brief status update.

2. **Check for blocks** — Is something waiting on Travis?
   → Post an actionable notification. Not "I'm stuck" — instead:
   "Q2 campaign: two headline options. A emphasizes price ($25,500 for 40x60). B emphasizes quality (engineered LVL headers). [Button: Option A] [Button: Option B] [Button: Both]"

3. **Check for new input** — Any messages I haven't processed?
   → Process them now.

4. **Nothing to do?** — Post brief status. "All caught up. Ready for new work."

**Anti-spam rules:**
- Don't re-notify on the same block
- Don't post "nothing to report"
- Batch small updates into one message

## Morning Briefing (/checkin or presence detection)

When Travis starts his day, post:

1. 🚫 **Needs Decision** — Blocked items with response buttons
2. ✅ **Approvals Waiting** — Deliverables to review
3. ✨ **Completed** — What got done since last check-in
4. 📋 **Today's Plan** — What I'll work on today
5. 💚 **Health** — System status, cost tracking

Keep it concise. Progressive disclosure — summary first, drill down on ask.

## Standing Orders

These run continuously in the background:

- **SOP Detection**: After each task, check for repeating patterns. If 2+ similar tasks, propose an SOP.
- **Memory Maintenance**: Mon/Wed/Fri morning — review daily notes, update long-term memory, prune stale info.
- **Project Drive**: After each approval, identify and start the next step. Default is forward momentum.
- **Health Check**: Every 4 hours — verify API connectivity, check costs, report anomalies.
