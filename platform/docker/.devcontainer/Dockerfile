# OpenClaw Devcontainer — thin layer over the official image
# ---------------------------------------------------------
# Adds only the Doppler CLI for runtime secret injection.
# Everything else comes from the upstream OpenClaw image.

FROM ghcr.io/openclaw/openclaw:latest

USER root

# ── Doppler CLI ────────────────────────────────────────────────────────────
RUN apt-get update \
  && apt-get install -y --no-install-recommends curl gettext-base \
  && curl -sLf --retry 3 --tlsv1.2 --proto "=https" \
       "https://cli.doppler.com/install.sh" | sh \
  && apt-get clean && rm -rf /var/lib/apt/lists/*

# ── Copy scripts ──────────────────────────────────────────────────────────
COPY --chown=node:node post_install.sh /opt/post_install.sh
COPY --chown=node:node start-openclaw.sh /opt/start-openclaw.sh
RUN chmod +x /opt/post_install.sh /opt/start-openclaw.sh

USER node
