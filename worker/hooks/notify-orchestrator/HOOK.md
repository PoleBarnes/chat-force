# notify-orchestrator

OpenClaw afterTurn hook that notifies the pipeline orchestrator after each turn.

## Trigger
afterTurn

## Behavior
POSTs minimal metadata to the orchestrator webhook endpoint.
Does not block execution — fire and forget.
