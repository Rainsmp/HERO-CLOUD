# HERO CLOUD - Complete starter package

Discord VPS manager using discord.py, SQLite, LXD and SSHX.

## Install
1. Extract the ZIP on Ubuntu 22.04/24.04.
2. Run `lxd init` if LXD has not already been initialized. Keep the LXD API private.
3. Run `bash scripts/install.sh` as root.
4. Edit `/opt/hero-cloud/.env`: set `DISCORD_TOKEN`, comma-separated `OWNER_IDS`, and your Discord server `GUILD_ID`.
5. Enable/start: `systemctl enable --now hero-cloud`
6. Check: `systemctl status hero-cloud --no-pager`
7. Logs: `journalctl -u hero-cloud -f`

## Commands
Members: `/help`, `/deploy`, `/myvps`, `/sshx`, `/start`, `/stop`, `/ping`.
Owners: `/create`, `/delete-vps`, `/extend-vps`, `/set-expiry`, `/list-vps`, `/expiry-info`, `/owner-check`.

## Important
SSHX links are bearer secrets and are delivered only by DM. Never publish them. LXD control is root-equivalent; do not expose its API. This package is a fresh baseline, not a verified in-place repair of an existing database/project. Test one VPS first. `MAX_VPS` is only a count ceiling, not a promise that hardware can safely run that many containers. Container disk quotas depend on the LXD storage driver and root device configuration; verify quotas on your host before customer rollout.
