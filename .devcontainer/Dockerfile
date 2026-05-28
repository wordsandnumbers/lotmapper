FROM mcr.microsoft.com/devcontainers/base:ubuntu-24.04

RUN apt-get update && apt-get install -y --no-install-recommends \
      jq \
      postgresql-client \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://github.com/digitalocean/doctl/releases/download/v1.104.0/doctl-1.104.0-linux-amd64.tar.gz \
      | tar -xz -C /usr/local/bin doctl

RUN mkdir -p /etc/claude-code
COPY managed-settings.json /etc/claude-code/managed-settings.json
