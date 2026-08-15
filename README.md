# RejoinLaterBot

> Leave now. Rejoin later.

RejoinLaterBot is a privacy-first, [open-source Telegram bot](https://github.com/rejoinlaterbot/RejoinLaterBot)
that schedules a way back to a group without becoming a group archive, membership
tracker, or bookmark manager. It supports Python 3.12+, aiogram 3, PostgreSQL,
SQLAlchemy async, and long polling.

## Open source and commercial use

The source code is licensed under the [Apache License 2.0](LICENSE). Commercial use,
modification, distribution, and self-hosting are permitted, subject to the license
terms. The license does not grant rights to use project trademarks beyond describing
the origin of the software.

The [Terms of Service](TERMS.md), [Acceptable Use Policy](ACCEPTABLE_USE.md), and
[Privacy Policy](PRIVACY.md) govern the official hosted `@RejoinLaterBot` service.
They do not replace or restrict the Apache-2.0 license for independently hosted copies.

## One private group-selection flow

```text
open /add in private chat
      ↓
choose a group with Telegram's private chat picker
      ↓
bot checks membership, administrator status, and Invite Users
      ↓
private invitation when all checks pass
or public link when the group is public
      ↓
choose the return time and leave the group yourself
```

When all three access checks pass, the bot uses Managed Return and rechecks the same
conditions at delivery time. If a check fails but the selected group has a public
username, the bot offers Public Reminder instead. Immediately before delivery it
resolves the encrypted username and compares the current Telegram chat ID with the
encrypted original ID. A username match alone is never sufficient. A private group
with failed access checks cannot be scheduled until its administrator adds the bot as
an administrator with `Invite Users`.

## Privacy comparison

| Mode | Temporarily stored | Never stored |
|---|---|---|
| Private invitation | encrypted user ID, encrypted chat ID, return state | group name, public address, profile data, messages |
| Private invitation with public fallback | encrypted user ID, encrypted chat ID, encrypted public address, return state | group name, profile data, messages |
| Public group link | encrypted user ID, encrypted chat ID, encrypted public address, return state | group name, profile data, messages |

All ID lookups use HMAC-SHA-256 blind indexes. Pending records are hard-deleted after
an observable Managed rejoin or after crash-safe public-link delivery. Hidden returns
are not queried by `/status` and do not create a count side channel. See
[PRIVACY.md](PRIVACY.md).

## Local development

1. Install Python 3.12 and PostgreSQL.
2. Copy `.env.example` to `.env` and fill all values. Generate independent 32-byte
   URL-safe Base64 keys with the command shown in that file.
3. Install and check the project:

   ```bash
   python -m venv .venv
   . .venv/bin/activate
   pip install -e '.[dev]'
   alembic upgrade head
   ruff check .
   ruff format --check .
   mypy
   pytest
   rejoinlaterbot
   ```

The polling transport is composed in `app.py`; repositories and delivery services do
not depend on polling, so a later webhook adapter does not change business rules.

## Production deployment

Use [ADMIN_SETUP.md](ADMIN_SETUP.md) for Telegram permissions and
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for a Hetzner/Docker Compose procedure.
PostgreSQL has no published host port, the application runs as a non-root user, and
secrets are mounted read-only from `/etc/rejoinlater/secrets`.

## Telegram platform limitation

Telegram's ordinary Bot API does not provide ephemeral group messages. Managed Return
therefore starts with `/add` in private chat and uses Telegram's native chat picker to
select a group. The request asks only for the selected ID and available public username;
it includes neither `bot_is_member` nor bot administrator-right criteria, so selecting
a group does not ask Telegram to add or promote the bot. Every selection is checked
privately. No command or bot response is posted in the group, and the bot still does
not request `Delete Messages`.

## License

[Apache License 2.0](LICENSE). Commercial use is permitted subject to the license
conditions.
