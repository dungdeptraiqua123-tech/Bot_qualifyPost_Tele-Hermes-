# VPS Deploy Guide

This deploy path is for AlmaLinux 8.10.

The repo contains:

- `telegram-bot/`: worker bot that reads source channels, calls Hermes, rewrites, and publishes.
- `vendor/hermes-agent/`: vendored Hermes Agent source.
- `skill-md/`: review/rewrite skills used by the bot.
- `deploy/`: installer, env templates, and service helper.

## First Install

SSH into the VPS as `root`, then run:

```bash
dnf install -y git
mkdir -p /opt/hermes-ads
git clone https://github.com/dungdeptraiqua123-tech/Bot_qualifyPost_Tele-Hermes-.git /opt/hermes-ads/project
cd /opt/hermes-ads/project
bash deploy/install_almalinux.sh
```

Because the GitHub repo is private, GitHub may ask for:

- Username: your GitHub username
- Password: a GitHub personal access token, not your GitHub password

Do not paste real tokens into documentation or chat.

## Env Files

The installer creates two private files on the VPS:

```text
/opt/hermes-ads/hermes.env
/opt/hermes-ads/bot.env
```

`hermes.env` is for Hermes only. It contains `API_SERVER_KEY` and provider keys
such as `DEEPSEEK_API_KEY`.

`bot.env` is for the Telegram worker bot only. It contains `TELEGRAM_BOT_TOKEN`,
`ADMIN_USER_IDS`, and `HERMES_API_KEY`.

The installer generates one local API key and writes it to both:

```text
Hermes: API_SERVER_KEY
Bot:    HERMES_API_KEY
```

These two values must match.

## Services

The installer creates and enables:

```text
hermes-api.service
telegram-bot.service
```

Useful commands:

```bash
/opt/hermes-ads/project/deploy/manage.sh status
/opt/hermes-ads/project/deploy/manage.sh logs
/opt/hermes-ads/project/deploy/manage.sh logs-hermes
/opt/hermes-ads/project/deploy/manage.sh logs-bot
/opt/hermes-ads/project/deploy/manage.sh restart
/opt/hermes-ads/project/deploy/manage.sh test-hermes
```

Manual systemd commands:

```bash
systemctl restart hermes-api telegram-bot
systemctl status hermes-api telegram-bot
journalctl -u telegram-bot -f
journalctl -u hermes-api -f
```

## Update Code

After pushing new code to GitHub:

```bash
cd /opt/hermes-ads/project
deploy/manage.sh update
```

This runs:

- `git pull --ff-only`
- reinstall Hermes from `vendor/hermes-agent`
- reinstall bot requirements
- restart both services

## Telegram Setup Checklist

- Bot is admin in every source channel it must read.
- Bot is admin in every target channel it must publish to.
- Bot has permission to post messages/media in target channels.
- Your Telegram user ID is in `ADMIN_USER_IDS`.
- Source channels are managed with:

```text
/allow_add <source_channel_id>
/allow_remove <source_channel_id>
/allow_list
```

- Mapping is managed with:

```text
/map_add <source_channel_id> <target_channel_id>
/map_remove <source_channel_id> <target_channel_id>
/map_list
```
