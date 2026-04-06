# Ticket Operations

Rules for working with tickets across platforms (Linear, Jira). Use these as your reference when fetching, creating, updating, or commenting on tickets.

---

## Normalized Field Mapping

Every ticket has these canonical fields regardless of platform:

| Field | Type | Description |
|-------|------|-------------|
| `title` | string | Short summary of the work |
| `description` | markdown | Full description of the work |
| `acceptance_criteria` | list | Verifiable criteria for PM review |
| `status` | label | Current state (see State Machine below) |
| `priority` | enum | `urgent`, `high`, `medium`, `low` |
| `assignee` | string | Who is responsible |
| `labels` | list | Tags for categorization and state tracking |
| `branch` | string | Associated git branch |
| `history` | comments | Activity log (comments on the ticket) |

---

## Platform Translation

### Linear

| Canonical Field | Linear Field | Notes |
|----------------|-------------|-------|
| `title` | Issue title | Direct mapping |
| `description` | Issue description | Markdown. Append `## Acceptance Criteria` section. |
| `acceptance_criteria` | In description | Under `## Acceptance Criteria` heading as checklist |
| `status` | Labels | Use `cf:*` labels, NOT Linear workflow states |
| `priority` | Priority field | 1=urgent, 2=high, 3=medium, 4=low |
| `assignee` | Assignee | Linear user reference |
| `labels` | Labels | Linear labels |
| `branch` | Branch link | Issue metadata / Git integration |
| `history` | Comments | Markdown comments on the issue |

### Jira

| Canonical Field | Jira Field | Notes |
|----------------|-----------|-------|
| `title` | Summary | Direct mapping |
| `description` | Description | ADF or markdown depending on Jira version. Append `## Acceptance Criteria` section. |
| `acceptance_criteria` | In description | Under `## Acceptance Criteria` heading as checklist |
| `status` | Labels | Use `cf:*` labels, NOT Jira workflow states |
| `priority` | Priority field | Maps to Jira priority levels |
| `assignee` | Assignee | Jira user reference |
| `labels` | Labels | Jira labels |
| `branch` | Development panel | Branch link in development integration |
| `history` | Comments | Markdown comments on the issue |

**Why labels for status instead of native workflow states?** Platform workflow states are not portable — they differ per project, per team, per Jira/Linear configuration. Labels are universal. The `cf:*` prefix namespaces our state labels so they don't collide with other labels.

---

## Label-Driven State Machine

Track ticket state via labels, not platform-native workflow states.

```
created → in_progress → pm_review → done
               ↑            |
               └────────────┘  (PM rejection → back to in_progress)
```

### Labels

| Label | Meaning |
|-------|---------|
| `cf:created` | Ticket created, not yet started |
| `cf:in_progress` | Execution swarm is working |
| `cf:pm_review` | PM verification phase |
| `cf:done` | All criteria passed, human approved |

### State Change Rules

When changing state:
1. Remove the old `cf:*` label
2. Add the new `cf:*` label
3. Add a comment noting the state change with timestamp

Valid transitions:
- `cf:created` → `cf:in_progress` (execution starts)
- `cf:in_progress` → `cf:pm_review` (swarm completes, hand off to PM)
- `cf:pm_review` → `cf:done` (PM passes, human approves)
- `cf:pm_review` → `cf:in_progress` (PM rejects, loop back to swarm)

No other transitions are valid. Never skip states. Never go backwards except `pm_review → in_progress`.

---

## Operations

### `fetch_ticket(id)`
Pull a ticket by ID and return normalized fields.
- Linear: Use `get_issue` MCP tool with the issue ID
- Jira: Use `get_issue` MCP tool with the issue key (e.g., `PROJ-42`)
- Parse description to extract `## Acceptance Criteria` section into the `acceptance_criteria` field
- Read `cf:*` labels to determine `status`

### `create_ticket(fields)`
Create a ticket from normalized fields.
- Build description by combining `description` + `## Acceptance Criteria` section
- Set priority via platform priority field
- Add `cf:created` label
- Link branch if provided

### `add_comment(id, body)`
Add a markdown comment to the ticket history.
- Use the Comment Format defined below
- Linear: Use `save_comment` MCP tool
- Jira: Use `add_comment` MCP tool

### `add_attachment(id, file)`
Attach a file to the ticket.
- Linear: Use `create_attachment` MCP tool
- Jira: Use `add_attachment` MCP tool

### `change_state(id, new_state)`
Update the ticket state via labels.
1. Fetch current labels
2. Remove any existing `cf:*` label
3. Add the new `cf:<new_state>` label
4. Add a comment: `**State changed:** cf:<old> → cf:<new> at YYYY-MM-DD HH:MM UTC`
5. Validate the transition is legal (see State Change Rules above)

### `assign(id, user)`
Assign the ticket to a user.
- Linear: Set assignee field
- Jira: Set assignee field

### `link_branch(id, branch)`
Associate a git branch with the ticket.
- Linear: Use branch link in issue metadata
- Jira: Branch appears in development panel automatically if commit messages reference the issue key

---

## Comment Format

All machine-written comments on tickets follow this format:

```markdown
## [Phase] — Attempt N

**Timestamp:** YYYY-MM-DD HH:MM UTC
**Branch:** ticket/PROJ-42
**Commit:** abc1234

### Summary
Brief description of what happened in this phase.

### Artifacts
- path/to/file1.md
- path/to/file2.html

### Result
PASS | FAIL — specific details about what passed or failed
```

### Phase Values
- `Execution` — the swarm phase produced artifacts
- `PM Review` — the PM verified acceptance criteria
- `Mechanic` — the mechanic analyzed and proposed improvements

### Rules for Comments
---

## Linear MCP Setup

The project includes a `.mcp.json` file that configures the Linear MCP server. To activate it:

1. Replace `REPLACE_ME_LINEAR_API_KEY` in `.mcp.json` with your Linear API key
2. Get your API key from Linear: Settings → API → Personal API keys
3. Claude Code CLI will automatically detect the `.mcp.json` and connect to Linear

### Available Linear MCP Tools

Once configured, you have access to these tools for ticket operations:

| Tool | Maps to Operation |
|------|------------------|
| `get_issue` | `fetch_ticket(id)` |
| `save_issue` | `create_ticket(fields)` / `change_state()` |
| `save_comment` | `add_comment(id, body)` |
| `create_attachment` | `add_attachment(id, file)` |
| `list_issues` | Search/filter tickets |
| `list_issue_labels` | Read available labels |
| `list_issue_statuses` | Read platform states (for reference only — use labels) |

### Important Notes

- Always use `cf:*` labels for state tracking, not Linear's native workflow states
- When creating tickets, add the `cf:created` label
- When fetching tickets, parse the description to extract the `## Acceptance Criteria` section
- Comments should follow the Comment Format defined above

---

## Rules for Comments
- Always include the timestamp in UTC
- Always include the branch and commit hash
- List all artifacts produced or inspected
- Be specific in the Result — cite which criteria passed or failed
- Keep the Summary under 3 sentences
