# Templates

Reusable starting points for creating new customer harnesses. Copy into a new harness repo and customize.

## `slack-manifest.json`

A Slack App Manifest template for a chat-force customer bot, modeled exactly on Leo's proven manifest.

### What it is

A Slack App Manifest is a single JSON (or YAML) document that defines a Slack App's configuration: display name, icon, bot user, OAuth scopes, event subscriptions, socket mode settings, interactivity. Slack supports creating and updating apps from a manifest via:

- **Web UI:** https://api.slack.com/apps → "Create New App" → "From an app manifest" (for new apps), or an existing app → Features → App Manifest (for updates).
- **API:** `apps.manifest.create`, `apps.manifest.update`, `apps.manifest.validate`, `apps.manifest.delete`.

Manifests are the authoritative source of truth for a Slack App's configuration. Keeping the manifest in the customer harness repo means:

- The bot's config is version-controlled alongside the customer's identity, brand, skills, and mechanic log.
- Re-creating the bot from scratch (disaster recovery, new workspace, etc.) is one paste away.
- Updates to scopes, events, or descriptions happen in the repo first, then sync to Slack — same flow as any other config change in the harness.

### Where it lives

Every customer harness repo stores its manifest at the repository root:

```
harness-<slug>/
└── slack-manifest.json   ← REQUIRED
```

This file is the definitive Slack App config for that customer's bot. When Slack drifts from the repo (e.g., someone changes a scope in the UI), the repo is the truth — push a manifest update to bring Slack back in line.

### How to use it when onboarding a new customer

1. **Copy the template into the new harness repo.**
   ```
   cp docs/templates/slack-manifest.json ../harness-<slug>/slack-manifest.json
   ```

2. **Edit every `REPLACE_ME_*` field.** Three things to change:
   - `display_information.name` — e.g., `"BlackTie"`
   - `display_information.description` — one-line pitch, max 140 chars
   - `display_information.long_description` — multi-paragraph, customer-facing copy. Use `\n\n` for paragraph breaks and `\r\n` inside paragraphs to match Slack's rendering (Leo's manifest demonstrates the pattern).
   - `display_information.background_color` — brand hex color, e.g., `"#0a0a0a"`
   - `features.bot_user.display_name` — must match `display_information.name`.

3. **Adjust scopes and events if this bot needs anything beyond the chat-force default set.** The template's scope and event list is what Leo uses and what `pipeline/slack_listener.py` expects — don't remove anything from this list or the listener will break.

4. **Create the Slack App.**
   - Go to https://api.slack.com/apps?new_app=1
   - Choose "From an app manifest"
   - Select the **Travis Hendrickson** workspace (all chat-force bots live in this one workspace, one bot per customer)
   - Paste the JSON
   - Review the config summary Slack shows you
   - Click "Create"
   - Click "Install to Workspace" and authorize

5. **Copy the tokens into Doppler.**
   - From the app's Basic Information page: copy the **App-Level Token** (starts with `xapp-`). If none exists, generate one with scope `connections:write`.
   - From OAuth & Permissions: copy the **Bot User OAuth Token** (starts with `xoxb-`).
   - Set both in Doppler under the variable names declared in the harness's `workspace.yaml`:
     ```
     doppler secrets set <SLUG>_SLACK_BOT_TOKEN="xoxb-..." --project chat-force --config <slug>
     doppler secrets set <SLUG>_SLACK_APP_TOKEN="xapp-..." --project chat-force --config <slug>
     ```

6. **Upload the avatar** (if one exists in the harness at `assets/avatar.png`).
   - Slack App → Display Information → App Icon → Upload.
   - This is manual — Slack's manifest API doesn't accept image uploads.

7. **Start the systemd unit** that runs this bot's listener. (S1.2+ implementation.)

### How to update an existing manifest

1. Edit `slack-manifest.json` in the harness repo.
2. Commit and push.
3. Go to the app at https://api.slack.com/apps → select the customer's app → **Features → App Manifest**.
4. Paste the updated JSON and save.
5. If scopes changed, Slack will prompt you to re-install the app to the workspace (this re-authorizes with new scopes).

### Schema reference

Full field reference: https://docs.slack.dev/reference/app-manifest/

Most important sections:

| Section | Purpose |
|---------|---------|
| `_metadata` | Manifest schema version. Chat-force uses version 1. |
| `display_information` | How the bot appears in Slack — name, descriptions, brand color. |
| `features.bot_user` | Bot's display name and online presence. |
| `oauth_config.scopes.bot` | Permissions. Chat-force's default set is the template list — don't shrink it. |
| `settings.event_subscriptions.bot_events` | Which events the bot receives. Chat-force listens to assistant threads, DMs, channels, groups, and mentions. |
| `settings.interactivity.is_enabled` | Must be `true` for feedback buttons. |
| `settings.socket_mode_enabled` | Must be `true`. Chat-force uses Socket Mode — no HTTP endpoint. |
| `settings.token_rotation_enabled` | Keep `false` until we're at 5+ bots and need rotation discipline. |

### Why JSON, not YAML

Both formats are supported by Slack. We use JSON because:
1. Slack's UI exports in JSON by default — round-tripping is cleaner.
2. Leo's existing manifest is JSON; consistency across harnesses.
3. No ambiguity around comments (JSON has none — documentation lives in this README).

If a future harness needs YAML for some reason, Slack accepts both — convert with `yq`.
