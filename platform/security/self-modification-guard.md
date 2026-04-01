# Self-Modification Prevention Strategy

## Problem

An AI agent with write access to its own configuration could alter its own
constraints, escalate its permissions, or disable safety checks. This is a
day-one security requirement: the agent must never be able to modify the files
that define its own behavior.

## Defense Layers

### Layer 1: Prompt-Level Restriction (active now)

The OpenClaw system prompt includes an explicit instruction:

> You must never modify, overwrite, or delete any file under `/config` or any
> platform configuration file (exec-approvals.json, base-config.yaml, etc.).
> If you believe a configuration change is needed, write a mechanic request.

This is the first line of defense and is effective for well-aligned models.

### Layer 2: exec-approvals.json (active now)

The command execution allowlist in `platform/exec-approvals.json` contains a
`self_modification_prevention` section that declares protected paths:

```json
{
  "protected_paths": [
    "/config",
    "/config/*",
    "platform/exec-approvals.json",
    "platform/base-config.yaml"
  ]
}
```

The enforcement layer should reject any write operation targeting these paths.

### Layer 3: Mechanic Request Pattern (active now)

When the agent determines a config change is needed, it follows this flow:

1. Agent writes a structured request to `/workspace/mechanic-requests/`
2. Request includes: what to change, why, expected impact
3. A human (the "mechanic") reviews and applies (or rejects) the change
4. The decision is logged via the audit logger

This keeps the human in the loop for all configuration changes.

### Layer 4: Read-Only Filesystem Mount (production target)

In the production container deployment:

```yaml
# docker-compose.yml or OpenClaw container config
volumes:
  - ./platform/exec-approvals.json:/config/exec-approvals.json:ro
  - ./platform/base-config.yaml:/config/base-config.yaml:ro
```

The `:ro` flag makes these files read-only at the filesystem level. Even if
the agent somehow bypasses the prompt and allowlist restrictions, the OS kernel
will reject the write.

### Layer 5: Audit Trail (active now)

All command executions are logged. Any attempt to modify protected files
(successful or blocked) generates a `COMMAND_BLOCKED` or `CONFIG_CHANGE`
audit event. These events can trigger alerts.

## Escalation Path

If prompt-level restrictions prove insufficient (e.g., the model finds ways
to work around the instruction):

1. **Immediate**: Tighten exec-approvals.json to explicitly block write
   commands targeting config paths
2. **Short-term**: Deploy filesystem-level read-only mounts (Layer 4)
3. **Medium-term**: Add a kernel-level file access control (AppArmor/SELinux
   profile) that restricts the agent's container user
4. **Long-term**: Move to a capability-based security model where config
   modifications require a cryptographic approval token from the mechanic

## Monitoring

The following audit events should trigger alerts:

- `COMMAND_BLOCKED` where the command targets a protected path
- `CONFIG_CHANGE` events (should only come from mechanic actions)
- Any `exec-approvals.json` or `base-config.yaml` appearing in `git diff`
  output within agent-initiated commits
