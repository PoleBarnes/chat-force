# OpenClaw Self-Hosted Gateway
# Based on node:22-slim for minimal footprint.
# Installs OpenClaw globally via npm and runs as a non-root user.
# Config templates are substituted at startup via entrypoint.sh.

FROM node:22-slim

# Install system dependencies needed by OpenClaw (browser, git, etc.)
# gettext-base provides envsubst for config template substitution.
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    gettext-base \
    chromium \
    fonts-liberation \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdrm2 \
    libgbm1 \
    libnss3 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    xdg-utils \
  && rm -rf /var/lib/apt/lists/*

# Tell Puppeteer/Chromium where the browser binary lives
ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true \
    PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium

# Install OpenClaw globally
RUN npm install -g openclaw@latest

# Create a non-root user to run the gateway
RUN groupadd --gid 1001 openclaw \
  && useradd --uid 1001 --gid openclaw --shell /bin/bash --create-home openclaw

# Create the directory structure OpenClaw expects
RUN mkdir -p /home/openclaw/.openclaw/data \
             /home/openclaw/.openclaw/workspace \
             /home/openclaw/.openclaw/config \
             /templates \
  && chown -R openclaw:openclaw /home/openclaw /templates

# Copy the entrypoint script
COPY --chmod=755 entrypoint.sh /usr/local/bin/entrypoint.sh

# Drop to non-root user
USER openclaw
WORKDIR /home/openclaw

# Gateway default port
EXPOSE 3001

# entrypoint.sh substitutes env vars into config templates, then
# starts the OpenClaw gateway.
CMD ["entrypoint.sh"]
