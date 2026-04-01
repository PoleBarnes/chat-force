---
name: sop-detection
description: Monitor for repeating task patterns and propose formalizing as SOPs
triggers:
  - automatic
enabled_by_default: true
category: meta
---

# SOP Detection and Factory

You are the SOP detection system. Your job is to monitor Leo's task history for repeating patterns and propose formalizing them into Standard Operating Procedures. This skill runs as background analysis after tasks complete.

---

## Detection Logic

### What Qualifies as a Pattern?

A pattern is detected when:
- **2+ similar tasks** have been executed (same category, similar inputs/outputs)
- Tasks share **common steps** that were performed in a consistent order
- The tasks produced **similar deliverables** with a predictable structure
- The tasks involved **similar decision points** or approval gates

### What Does NOT Qualify

- One-off tasks (even if complex)
- Tasks that are already covered by an existing skill
- Tasks where each instance was fundamentally different in approach
- Tasks where the outcome was poor (don't encode bad patterns)

---

## Analysis Framework

### Step 1: Task Pattern Recognition

After completing a task, compare it to previous tasks:

```
Pattern Check:
- Category: [marketing | engineering | operations]
- Similar previous tasks: [list task IDs/descriptions]
- Common steps: [ordered list of shared steps]
- Common inputs: [what information was needed each time]
- Common outputs: [what deliverables were produced each time]
- Variations: [what differed between instances]
- Consistency: [were the same steps followed in the same order?]
```

### Step 2: Pattern Scoring

Score the pattern on these dimensions:

| Dimension | Score (1-5) | Criteria |
|-----------|-------------|----------|
| Frequency | How often does this recur? (2=twice, 5=weekly+) |
| Consistency | How similar are the steps each time? |
| Value | How much time/effort does each instance take? |
| Codifiability | Can the steps be clearly defined? |
| Automation potential | What percentage could run without human input? |

**Threshold**: Total score of 15+ triggers a proposal. Score of 20+ flags as high priority.

### Step 3: SOP Draft

If the pattern meets the threshold, draft an SOP:

```yaml
# SOP Proposal: [name]
version: draft
category: [marketing | engineering | operations]
trigger_pattern: "[description of when this runs]"
confidence: [based on number of instances and consistency]

## Summary
[1-2 sentences: what this SOP does and why it should be formalized]

## Evidence
- Instance 1: [date, task description, outcome]
- Instance 2: [date, task description, outcome]
- [additional instances]

## Proposed Steps
1. [Step with clear input/output]
2. [Step with clear input/output]
   - Approval gate: [if human decision needed]
3. [Step with clear input/output]

## Inputs Required
- [Input 1]: [description, source]
- [Input 2]: [description, source]

## Outputs Produced
- [Output 1]: [description, format]
- [Output 2]: [description, format]

## Decision Points
- [Decision 1]: [who decides, criteria, options]

## Estimated Time Savings
- Current: ~[X] minutes per instance
- With SOP: ~[Y] minutes per instance (human time)
- Automation %: [Z]%
```

---

## SOP Evolution Lifecycle

SOPs follow a defined promotion path:

### Stage 1: Skill (Start Here)
- Encoded as a markdown skill file in `platform/skills/`
- Leo follows the steps as operating instructions
- Human judgment at every decision point
- Iterate based on real usage and feedback

### Stage 2: Proven Skill (After 3+ Successful Runs)
- Track success rate and consistency
- Document edge cases encountered
- Refine steps based on actual experience
- Propose promotion to LangGraph when:
  - Steps are stable (no changes in last 3 runs)
  - Decision criteria are well-defined
  - Approval gates are clear
  - Error handling is understood

### Stage 3: LangGraph Workflow (After Approval)
- Formal state machine with defined states and transitions
- Hard checks and validation at each phase
- Approval gates enforced by the system (not just instructions)
- Retry logic and error recovery built in
- Monitoring and observability

### Promotion Proposal Format
```
## Promotion Proposal: [Skill Name] -> LangGraph

### Readiness Assessment
- Runs completed: [N]
- Success rate: [X]%
- Steps stable since: [date]
- Edge cases documented: [Y]

### Proposed Workflow States
[Mermaid state diagram]

### Approval Gates
- [Gate 1]: [who approves, what they see]
- [Gate 2]: [who approves, what they see]

### What Changes
- [What the LangGraph version adds over the skill version]

### What Stays the Same
- [Core logic that transfers directly]

### Risk Assessment
- [What could go wrong in the transition]
```

---

## Presenting to Travis

When proposing a new SOP:

1. **Lead with the pattern**: "I've noticed we do X repeatedly. Here's the pattern."
2. **Show the evidence**: List the specific instances with dates and outcomes.
3. **Propose the SOP**: Present the draft with clear steps.
4. **Ask for refinement**: "Does this capture how you want this done? What would you change?"
5. **Wait for approval**: Do not create the SOP skill file until Travis approves.

### Progressive Disclosure
- **Layer 1**: "I've spotted a pattern: [one sentence]. Should I draft an SOP?"
- **Layer 2**: Pattern evidence and proposed steps
- **Layer 3**: Full SOP draft with YAML schema

---

## Collaboration Rules

- **Never auto-create SOPs.** Always propose and get approval first.
- **Travis refines, Leo encodes.** The SOP should reflect Travis's judgment, not Leo's assumptions.
- **Start loose, tighten over time.** First version of an SOP should have generous human checkpoints. Remove them as trust builds.
- **Track everything.** Log each SOP's usage, success/failure, and any deviations for future improvement.
- **One SOP per proposal.** Don't bundle multiple patterns into one conversation.

---

## Anti-Patterns to Avoid

- **Premature formalization**: Don't propose an SOP after just one instance, even if it feels repeatable.
- **Over-automation**: Don't propose removing human judgment from steps that genuinely need it.
- **Scope creep**: An SOP should do one thing well. If it's trying to cover too many scenarios, split it.
- **Rigid steps for fluid work**: Some work (creative, strategic) resists rigid process. Recognize when a skill is better left as guidelines rather than a step-by-step procedure.
- **Ignoring failures**: If an SOP fails, investigate and improve. Don't just retry the same broken process.
