# Dev Container

A reproducible Linux environment for working on this project with Claude Code. Claude Code runs inside the container with [auto mode](https://code.claude.com/docs/en/permission-modes#eliminate-prompts-with-auto-mode) enabled by default, so it can edit files, run the app stack, and execute routine commands without per-action permission prompts — while a classifier still blocks risky operations (curl-pipe-bash, force pushes, prod-touching deploys, etc.).

Your editor (VS Code) runs on the host. The container holds the terminal, build tools, the Docker socket, and Claude itself. Repo files appear on both sides via a bind mount.

---

## First-time setup

**Prerequisites**

- Docker Desktop running on your Mac
- VS Code with the [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)

**Open the project in a container**

1. Open this repo in VS Code.
2. Command Palette (`Cmd+Shift+P`) → **Dev Containers: Reopen in Container**.
3. First build takes a few minutes (downloads the Ubuntu base image, installs Node 20, Python 3.11, `gh`, `doctl`, and the Claude Code CLI).

Subsequent rebuilds are much faster thanks to layer caching.

---

## Sign in to Claude

In the container's integrated terminal:

```bash
claude
```

Follow the browser auth prompt. If the localhost callback never returns (sometimes VS Code's port forwarding misroutes it), copy the code shown in the browser and paste it at the `Paste code here if prompted` prompt in the terminal.

Auth is stored in your host `~/.claude` directory, which is bind-mounted into the container. Sign-in, project memory, and conversation history are shared between host and container Claude sessions — no migration needed and no repeated sign-in after rebuilds.

---

## Auto mode opt-in

The first time auto mode would activate, Claude shows a one-time consent prompt. Accept it. After that, the status bar shows `auto` and routine work proceeds without prompts.

See the [auto mode docs](https://code.claude.com/docs/en/permission-modes#eliminate-prompts-with-auto-mode) for the exact list of what the classifier blocks vs. allows. Short version: working-directory edits and lockfile-declared installs are auto-approved; curl-pipe-bash, mass deletes, prod deploys, and force-pushes are blocked.

---

## Running the app stack

From inside the dev container, `docker compose` commands work exactly the same as on the host:

```bash
docker compose up -d           # bring up db, rabbitmq, backend, worker, frontend
docker compose logs -f backend
docker compose exec backend pytest
```

This works because the container mounts the host's Docker socket (via the `docker-outside-of-docker` feature) and mirrors the workspace path so bind mounts like `./model` and `./debug` resolve identically inside and outside the container. The app's containers run as **siblings** of the dev container, visible in `docker ps` on the host.

---

## Daily workflow tips

- Use `Shift+Tab` to cycle permission modes mid-session. Drop to `default` or `acceptEdits` when doing something sensitive (large refactors, prod-touching scripts, anything you want to eyeball before it runs).
- Project-scoped allow rules in [`.claude/settings.json`](../.claude/settings.json) still apply inside the container.
- Host-side Claude sessions (outside the container) are unaffected — they use the host's allowlist and prompt normally.

---

## Troubleshooting

**"Browser callback never returns" during `claude` sign-in**
Copy the code shown in the browser and paste it at the terminal prompt. VS Code's port forwarding sometimes drops the localhost callback.

**`docker compose up` fails with "bind source path does not exist"**
The workspace-path mirroring didn't apply. Check that `pwd` inside the container matches your host path (e.g. `/Users/justin/git/parking-lot-app`). If not, rebuild the container — the `workspaceMount` setting in `devcontainer.json` should kick in on rebuild.

**Auto mode says "unavailable"**
Run `/model` and confirm you're on Opus 4.6+ or Sonnet 4.6. Older models don't support auto mode.

**`ssh` to the production droplet doesn't work**
VS Code Dev Containers should forward your host's SSH agent automatically when `SSH_AUTH_SOCK` is set. If not, check that your host's `ssh-agent` is running and has your key loaded (`ssh-add -l`).

---

## Rebuilding / resetting

- **Rebuild the container** (after changing `Dockerfile` or `devcontainer.json`): Command Palette → **Dev Containers: Rebuild Container**.
- **Wipe Claude auth and start fresh**: on the host, `rm -rf ~/.claude/auth` and run `claude` to re-authenticate. This affects both host and container sessions since they share `~/.claude`.
