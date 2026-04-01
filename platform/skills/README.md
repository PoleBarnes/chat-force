# Platform Skills

Skills are markdown files that extend Leo's capabilities. They are loaded into OpenClaw's context when a trigger keyword matches the user's request.

## Skill Format

Each skill is a markdown file with YAML frontmatter followed by operating instructions:

```yaml
---
name: skill-name
description: One-line description
triggers:
  - keyword1
  - keyword2
enabled_by_default: true/false
category: marketing|engineering|operations|meta
---
```

The body contains detailed instructions that Leo follows as an operating procedure.

## Lifecycle

Skills follow the SOP evolution strategy:

1. **Skill** (markdown, cheap to iterate) -- start here
2. **Proven skill** (3+ successful runs with consistent results)
3. **LangGraph workflow** (rigid, verified, approval-gated) -- promote when proven

## Directory

| Skill | Category | Description |
|-------|----------|-------------|
| ad-campaign-research | marketing | Research phase for ad campaigns |
| ad-campaign-generate | marketing | Generation phase for ad campaigns |
| code-review | engineering | PR code review |
| pr-creation | engineering | Create well-structured PRs |
| research | operations | General web research methodology |
| morning-briefing | operations | Daily status briefing |
| sop-detection | meta | Detect repeating patterns and propose SOPs |

## Registration

Skills must also be registered in `platform/base-config.yaml` under the `skills` key to be available to workspaces.
