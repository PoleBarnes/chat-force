/**
 * afterTurn hook — notifies the pipeline orchestrator.
 * Posts minimal metadata: container ID, timestamp, session info.
 * Fire-and-forget: does not block the next turn.
 */

interface AfterTurnPayload {
  sessionId: string;
  turnNumber: number;
}

export default async function handler(payload: AfterTurnPayload): Promise<void> {
  const webhookUrl = process.env.ORCHESTRATOR_WEBHOOK_URL;
  if (!webhookUrl) {
    console.warn("[notify-orchestrator] ORCHESTRATOR_WEBHOOK_URL not set, skipping");
    return;
  }

  const data = {
    container_id: process.env.HOSTNAME || "unknown",
    session_id: payload.sessionId,
    turn_number: payload.turnNumber,
    timestamp: new Date().toISOString(),
    event: "after_turn",
  };

  try {
    await fetch(`${webhookUrl}/hooks/after-turn`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
      signal: AbortSignal.timeout(5000),
    });
  } catch (err) {
    console.warn(`[notify-orchestrator] Failed to notify: ${err}`);
  }
}
