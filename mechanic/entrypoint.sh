#!/bin/bash
set -euo pipefail

: "${TASK_DESCRIPTION:?TASK_DESCRIPTION env var is required}"
: "${ANTHROPIC_AUTH_TOKEN:?ANTHROPIC_AUTH_TOKEN env var is required}"

export ANTHROPIC_API_KEY="${ANTHROPIC_AUTH_TOKEN}"

echo "[Mechanic] Evaluating changeset for task: ${TASK_DESCRIPTION}"

CHANGESET_FILE="/changeset/changeset.json"
if [ ! -f "$CHANGESET_FILE" ]; then
  echo "[Mechanic] ERROR: No changeset file at $CHANGESET_FILE"
  echo '{"verdict":"reject","confidence":0.0,"summary":"No changeset file found","rejection_reason":"Changeset file missing"}' > /output/verdict.json
  exit 0
fi

# Build evaluation prompt — instruct the Mechanic to return verdict as JSON
# in its response text (not write to a file, since --local mode has no file tools)
MESSAGE="Evaluate this changeset. The original task was:

${TASK_DESCRIPTION}

Here is the full changeset bundle (JSON):

$(cat "$CHANGESET_FILE")

Evaluate the changeset according to your AGENTS.md instructions. Then output your verdict as a JSON code block in your response. Use this exact format:

\`\`\`json
{
  \"verdict\": \"approve\" or \"reject\",
  \"confidence\": 0.0 to 1.0,
  \"summary\": \"one-paragraph summary\",
  \"evaluation\": {
    \"meaningful\": { \"pass\": true/false, \"notes\": \"...\" },
    \"correct\":    { \"pass\": true/false, \"notes\": \"...\" },
    \"safe\":       { \"pass\": true/false, \"notes\": \"...\" },
    \"minimal\":    { \"pass\": true/false, \"notes\": \"...\" },
    \"reproducible\": { \"pass\": true/false, \"notes\": \"...\" }
  },
  \"pr_title\": \"short title\",
  \"pr_body\": \"PR description\",
  \"files_to_include\": [\"list of paths\"],
  \"files_to_exclude\": [\"list of paths\"],
  \"rejection_reason\": \"if rejected\"
}
\`\`\`

IMPORTANT: Output the verdict JSON in a code block in your response. Do NOT try to write it to a file."

openclaw agent \
  --local \
  --agent main \
  --message "$MESSAGE" \
  --json \
  > /tmp/mechanic-output.json 2>&1 || true

echo "[Mechanic] Agent finished. Extracting verdict from response..."

# Extract the verdict JSON from the agent's text response.
# The --json flag wraps the response in {"payloads":[{"text":"..."}]}.
# The verdict is inside a ```json ... ``` code block in the text.
python3 -c "
import json, re, sys

try:
    with open('/tmp/mechanic-output.json') as f:
        raw = f.read()

    # The openclaw --json output may have non-JSON prefix lines (log lines).
    # Find the first line starting with '{' that looks like JSON.
    json_start = raw.find('{\"payloads\"')
    if json_start == -1:
        json_start = raw.find('{')
    if json_start == -1:
        raise ValueError('No JSON found in mechanic output')

    data = json.loads(raw[json_start:])

    # Collect all text from payloads
    full_text = ''
    for payload in data.get('payloads', []):
        if 'text' in payload:
            full_text += payload['text'] + '\n'

    # Extract JSON from code block
    match = re.search(r'\`\`\`json\s*\n(.*?)\n\s*\`\`\`', full_text, re.DOTALL)
    if not match:
        # Try without code fence — look for raw JSON object with verdict key
        match = re.search(r'(\{[^{}]*\"verdict\"[^{}]*\})', full_text, re.DOTALL)
    if not match:
        raise ValueError('No verdict JSON found in agent response')

    verdict = json.loads(match.group(1))

    # Validate required field
    if 'verdict' not in verdict:
        raise ValueError('Verdict missing \"verdict\" field')

    with open('/output/verdict.json', 'w') as f:
        json.dump(verdict, f, indent=2)

    print(f'[Mechanic] Verdict extracted: {verdict[\"verdict\"]}')

except Exception as e:
    print(f'[Mechanic] Failed to extract verdict: {e}', file=sys.stderr)
    fallback = {
        'verdict': 'reject',
        'confidence': 0.0,
        'summary': f'Mechanic failed to produce parseable verdict: {e}',
        'rejection_reason': str(e)
    }
    with open('/output/verdict.json', 'w') as f:
        json.dump(fallback, f, indent=2)
"
