# OpenClaw Self-Hosted Devcontainer
# ---------------------------------
# Provides a complete environment for running OpenClaw gateway inside a
# devcontainer managed by the `devcontainer` CLI on macOS with OrbStack.
#
# Includes: Node 22, OpenClaw, Doppler CLI, headless Chromium, GitHub CLI.
# Runs as non-root user "vscode" (UID 1000) with passwordless sudo.

FROM ubuntu:24.04

ARG DEBIAN_FRONTEND=noninteractive
ARG TZ=UTC
ENV TZ="$TZ"

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# ── System packages ────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    wget \
    jq \
    zsh \
    tmux \
    openssh-client \
    ca-certificates \
    gnupg \
    sudo \
    nano \
    unzip \
    gettext-base \
    locales \
  && locale-gen en_US.UTF-8 \
  && apt-get clean && rm -rf /var/lib/apt/lists/*

ENV LANG=en_US.UTF-8 \
    LC_ALL=en_US.UTF-8

# ── Node.js 22 LTS (via NodeSource) ───────────────────────────────────────
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
  && apt-get install -y --no-install-recommends nodejs \
  && apt-get clean && rm -rf /var/lib/apt/lists/*

# ── OpenClaw (global install) ─────────────────────────────────────────────
RUN npm install -g openclaw@latest

# ── Doppler CLI ────────────────────────────────────────────────────────────
RUN curl -sLf --retry 3 --tlsv1.2 --proto "=https" \
      "https://cli.doppler.com/install.sh" | sh

# ── Headless Chromium + dependencies ──────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
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
  && apt-get clean && rm -rf /var/lib/apt/lists/*

ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true \
    PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium \
    CHROME_BIN=/usr/bin/chromium

# ── GitHub CLI ─────────────────────────────────────────────────────────────
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
      | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
  && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
  && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
      > /etc/apt/sources.list.d/github-cli.list \
  && apt-get update && apt-get install -y --no-install-recommends gh \
  && apt-get clean && rm -rf /var/lib/apt/lists/*

# ── Non-root user: vscode (UID 1000) ──────────────────────────────────────
RUN if ! getent group 1000 >/dev/null; then groupadd --gid 1000 vscode; fi \
  && if ! id -u 1000 >/dev/null 2>&1; then \
       useradd --uid 1000 --gid 1000 --shell /bin/zsh --create-home vscode; \
     else \
       usermod --login vscode --shell /bin/zsh --home /home/vscode --move-home $(id -nu 1000) 2>/dev/null || true; \
     fi \
  && echo "vscode ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers.d/vscode \
  && chmod 0440 /etc/sudoers.d/vscode

# ── Create directories expected by the container ──────────────────────────
RUN mkdir -p \
    /home/vscode/.openclaw/data \
    /home/vscode/.openclaw/workspace \
    /home/vscode/.openclaw/config \
    /home/vscode/.doppler \
    /home/vscode/.shell_history \
    /workspace \
  && chown -R vscode:vscode /home/vscode /workspace

# ── Copy scripts ──────────────────────────────────────────────────────────
COPY --chown=vscode:vscode post_install.sh /opt/post_install.sh
COPY --chown=vscode:vscode start-openclaw.sh /opt/start-openclaw.sh
RUN chmod +x /opt/post_install.sh /opt/start-openclaw.sh

# ── Environment ───────────────────────────────────────────────────────────
ENV DEVCONTAINER=true \
    SHELL=/bin/zsh \
    EDITOR=nano \
    VISUAL=nano

WORKDIR /workspace
USER vscode
